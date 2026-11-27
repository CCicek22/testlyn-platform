"""Retrieval evaluation gate on real Postgres with the deterministic embedder.

Run with: TEST_POSTGRES_URL=postgresql+asyncpg://... uv run pytest -m postgres
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from testlyn_api.knowledge.embeddings import EmbeddingError, HashingEmbedder
from testlyn_api.knowledge.evaluation.dataset import EvalSet, load_eval_set
from testlyn_api.knowledge.evaluation.runner import (
    EVAL_ORG_ID,
    EvaluationRefused,
    run_evaluation,
)
from testlyn_api.models.knowledge import KnowledgeDocument
from testlyn_api.models.org import Organization

pytestmark = pytest.mark.postgres

ROOT = Path(__file__).resolve().parents[2] / "evals" / "knowledge"
MODES = ("hybrid", "vector", "keyword")


def _dataset() -> EvalSet:
    return load_eval_set(ROOT / "corpus", ROOT / "queries.jsonl")


async def _doc_count(engine: AsyncEngine) -> int:
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        result = await s.execute(
            select(func.count())
            .select_from(KnowledgeDocument)
            .where(KnowledgeDocument.org_id == EVAL_ORG_ID)
        )
        return int(result.scalar_one())


async def test_gate_on_checked_in_set(engine: AsyncEngine, migrated: None) -> None:
    report = await run_evaluation(
        engine, dataset=_dataset(), embedder=HashingEmbedder()
    )
    overall = {m: report.overall(m) for m in MODES}
    by_kind = {m: report.modes[m].by_kind for m in MODES}
    # Measured 2026-11-27 (hashing embedder, top_k 5, 48 queries): hybrid hit@5
    # 0.542, hybrid ndcg@5 0.421, hybrid keyword-kind hit@5 0.688, hybrid
    # mixed-kind hit@5 0.750. Each threshold sits 0.04 to 0.06 below its value.
    assert overall["hybrid"]["hit@5"] >= 0.50
    assert overall["hybrid"]["ndcg@5"] >= 0.38
    assert by_kind["hybrid"]["keyword"]["hit@5"] >= 0.65
    assert by_kind["hybrid"]["mixed"]["hit@5"] >= 0.70
    # Measured: hybrid 0.542, best single leg (vector) 0.479.
    best_single = max(overall["vector"]["hit@5"], overall["keyword"]["hit@5"])
    assert overall["hybrid"]["hit@5"] >= best_single - 0.05


async def test_two_runs_give_identical_metrics(
    engine: AsyncEngine, migrated: None
) -> None:
    dataset = _dataset()
    first = await run_evaluation(engine, dataset=dataset, embedder=HashingEmbedder())
    second = await run_evaluation(engine, dataset=dataset, embedder=HashingEmbedder())
    assert first.as_dict() == second.as_dict()


async def test_failed_run_removes_everything_it_created(
    engine: AsyncEngine, migrated: None
) -> None:
    dataset = _dataset()
    query_texts = {q.query for q in dataset.queries}

    class FailingQueries(HashingEmbedder):
        async def embed(self, texts: list[str]) -> list[list[float]]:
            if any(t in query_texts for t in texts):
                raise EmbeddingError("simulated outage")
            return await super().embed(texts)

    with pytest.raises(EmbeddingError):
        await run_evaluation(engine, dataset=dataset, embedder=FailingQueries())
    assert await _doc_count(engine) == 0
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        org = await s.get(Organization, EVAL_ORG_ID)
    assert org is None


async def test_refuses_when_eval_org_has_documents(
    engine: AsyncEngine, migrated: None
) -> None:
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        s.add(
            Organization(
                id=EVAL_ORG_ID,
                name="Eval",
                slug=f"e-{uuid.uuid4().hex[:8]}",
                plan="free",
            )
        )
        await s.flush()
        s.add(
            KnowledgeDocument(
                org_id=EVAL_ORG_ID,
                title="existing",
                source="upload",
                content_sha256=uuid.uuid4().hex + uuid.uuid4().hex,
                status="ready",
                chunk_count=0,
            )
        )
        await s.commit()
    with pytest.raises(EvaluationRefused):
        await run_evaluation(engine, dataset=_dataset(), embedder=HashingEmbedder())
    assert await _doc_count(engine) == 1


async def test_existing_empty_eval_org_is_kept(
    engine: AsyncEngine, migrated: None
) -> None:
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        s.add(
            Organization(
                id=EVAL_ORG_ID,
                name="Eval",
                slug=f"e-{uuid.uuid4().hex[:8]}",
                plan="free",
            )
        )
        await s.commit()
    await run_evaluation(engine, dataset=_dataset(), embedder=HashingEmbedder())
    async with factory() as s:
        assert await s.get(Organization, EVAL_ORG_ID) is not None
    assert await _doc_count(engine) == 0
