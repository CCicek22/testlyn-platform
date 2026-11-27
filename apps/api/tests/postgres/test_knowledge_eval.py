"""Retrieval evaluation gate on real Postgres with the deterministic embedder.

Run with: TEST_POSTGRES_URL=postgresql+asyncpg://... uv run pytest -m postgres
"""

from __future__ import annotations

import json
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


class _AlwaysRelevantJudge:
    async def complete(self, prompt: str) -> str:
        return '{"relevant": true, "score": 5, "reason": "fixed reply"}'


class _ProseJudge:
    async def complete(self, prompt: str) -> str:
        return "Sure! This passage is relevant."


async def test_judge_wiring_counts_every_retrieved_passage(
    engine: AsyncEngine, migrated: None
) -> None:
    report = await run_evaluation(
        engine,
        dataset=_dataset(),
        embedder=HashingEmbedder(),
        modes=("hybrid",),
        judge=_AlwaysRelevantJudge(),
    )
    mode = report.modes["hybrid"]
    assert mode.judge is not None
    retrieved = sum(len(q.ranking) for q in mode.queries)
    assert mode.judge.agreement.n == retrieved
    assert mode.judge.judge_errors == 0
    assert all(q.judged_precision in (0.0, 1.0) for q in mode.queries)
    assert "judge" in report.as_dict()["modes"]["hybrid"]


async def test_unparseable_judge_replies_are_recorded_not_passed(
    engine: AsyncEngine, migrated: None
) -> None:
    report = await run_evaluation(
        engine,
        dataset=_dataset(),
        embedder=HashingEmbedder(),
        modes=("hybrid",),
        judge=_ProseJudge(),
    )
    mode = report.modes["hybrid"]
    assert mode.judge is not None
    retrieved = sum(len(q.ranking) for q in mode.queries)
    assert mode.judge.judge_errors == retrieved
    assert mode.judge.judged_precision == 0.0
    assert mode.judge.agreement.n == 0
    assert mode.judge.agreement.kappa is None


def test_cli_prints_table_and_writes_json(
    migrated: None,
    postgres_url: str,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from testlyn_api.knowledge.evaluation.__main__ import main

    out_path = tmp_path / "report.json"
    code = main(["--database-url", postgres_url, "--json-out", str(out_path)])
    assert code == 0
    printed = capsys.readouterr().out
    assert "| hybrid | overall | 48 |" in printed
    assert json.loads(out_path.read_text(encoding="utf-8"))["queries"] == 48


class _CountingJudge:
    def __init__(self) -> None:
        self.calls = 0

    async def complete(self, prompt: str) -> str:
        self.calls += 1
        return '{"relevant": true, "score": 3, "reason": "counted"}'


async def test_each_query_chunk_pair_is_judged_once_per_run(
    engine: AsyncEngine, migrated: None
) -> None:
    judge = _CountingJudge()
    report = await run_evaluation(
        engine, dataset=_dataset(), embedder=HashingEmbedder(), judge=judge
    )
    pairs = {
        (q.query_id, item)
        for mode in report.modes.values()
        for q in mode.queries
        for item in q.ranking
    }
    assert judge.calls == len(pairs)
