"""Retrieval evaluation gate on real Postgres with the deterministic embedder.

Run with: TEST_POSTGRES_URL=postgresql+asyncpg://... uv run pytest -m postgres
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from testlyn_api.knowledge import service
from testlyn_api.knowledge.embeddings import EmbeddingError, HashingEmbedder
from testlyn_api.knowledge.evaluation.dataset import EvalSet, load_eval_set
from testlyn_api.knowledge.evaluation import runner
from testlyn_api.knowledge.evaluation.runner import (
    EVAL_LOCK_KEY,
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
    # Measured on 2026-11-27 with the hashing embedder, top_k 5, 48 queries:
    # hybrid overall hit@5 29/48, overall nDCG@5 0.486, keyword kind 12/16,
    # mixed kind 14/16, vector overall hit@5 25/48. Kind rows have 16 queries,
    # so each threshold allows one query of slack (one query = 1/16 = 0.0625).
    # Overall rows allow two queries of slack (2/48, about 0.042).
    assert overall["hybrid"]["hit@5"] >= 27 / 48  # 29 measured
    assert overall["hybrid"]["ndcg@5"] >= 0.44  # 0.486 measured
    assert by_kind["hybrid"]["keyword"]["hit@5"] >= 11 / 16  # 12 measured
    assert by_kind["hybrid"]["mixed"]["hit@5"] >= 13 / 16  # 14 measured
    # Hybrid may not trail its best single leg (vector 25/48) by more than 0.05.
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


async def _seed_document(engine: AsyncEngine, org_id: uuid.UUID, title: str) -> None:
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        if await s.get(Organization, org_id) is None:
            s.add(
                Organization(
                    id=org_id,
                    name=f"org {title}",
                    slug=f"s-{uuid.uuid4().hex[:10]}",
                    plan="free",
                )
            )
            await s.flush()
        s.add(
            KnowledgeDocument(
                org_id=org_id,
                title=title,
                source="upload",
                content_sha256=uuid.uuid4().hex + uuid.uuid4().hex,
                status="ready",
                chunk_count=0,
            )
        )
        await s.commit()


async def test_second_run_is_refused_while_first_holds_the_lock(
    engine: AsyncEngine, migrated: None
) -> None:
    async with engine.connect() as holder:
        got = await holder.scalar(select(func.pg_try_advisory_lock(EVAL_LOCK_KEY)))
        assert got is True
        await _seed_document(engine, EVAL_ORG_ID, "first run's row")
        with pytest.raises(EvaluationRefused, match="already running"):
            await run_evaluation(engine, dataset=_dataset(), embedder=HashingEmbedder())
        assert await _doc_count(engine) == 1
        await holder.scalar(select(func.pg_advisory_unlock(EVAL_LOCK_KEY)))
    # Cleanup of the seeded row, which this test created.
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        await s.execute(
            delete(KnowledgeDocument).where(KnowledgeDocument.org_id == EVAL_ORG_ID)
        )
        await s.commit()


async def test_lock_is_released_after_a_run(engine: AsyncEngine, migrated: None) -> None:
    await run_evaluation(engine, dataset=_dataset(), embedder=HashingEmbedder())
    async with engine.connect() as probe:
        got = await probe.scalar(select(func.pg_try_advisory_lock(EVAL_LOCK_KEY)))
        assert got is True
        await probe.scalar(select(func.pg_advisory_unlock(EVAL_LOCK_KEY)))


async def test_run_refuses_when_a_document_is_not_newly_created(
    engine: AsyncEngine, migrated: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_ingest = service.ingest_document

    async def existing(*args: Any, **kwargs: Any) -> Any:
        stored, _created = await real_ingest(*args, **kwargs)
        return stored, False

    monkeypatch.setattr(runner.service, "ingest_document", existing)
    with pytest.raises(EvaluationRefused, match="already exists"):
        await run_evaluation(engine, dataset=_dataset(), embedder=HashingEmbedder())
    assert await _doc_count(engine) == 0


async def test_other_org_rows_are_unchanged_by_a_run(
    engine: AsyncEngine, migrated: None
) -> None:
    other = uuid.uuid4()
    await _seed_document(engine, other, "customer document")
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def snapshot() -> list[tuple[str, str, int]]:
        async with factory() as s:
            rows = await s.execute(
                select(
                    KnowledgeDocument.id,
                    KnowledgeDocument.title,
                    KnowledgeDocument.chunk_count,
                ).where(KnowledgeDocument.org_id == other)
            )
            return sorted((str(i), t, c) for i, t, c in rows.all())

    before = await snapshot()
    await run_evaluation(engine, dataset=_dataset(), embedder=HashingEmbedder())
    assert await snapshot() == before
    assert len(before) == 1
