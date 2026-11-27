"""Run the eval set through the real ingest and search code on Postgres.

The run uses one fixed org (``EVAL_ORG_ID``). It refuses to start when that org
already holds knowledge documents, so evaluation data never mixes with other
rows. It removes the documents it stored, and the org when it created it, in a
``finally`` block. No database transaction is open during an embedding call:
the service and search layers commit before each network call.
"""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field, replace
from typing import Any

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from testlyn_api.knowledge import search, service
from testlyn_api.knowledge.embeddings import Embedder
from testlyn_api.knowledge.evaluation import metrics
from testlyn_api.knowledge.evaluation.dataset import EvalSet, Query
from testlyn_api.knowledge.evaluation.judge import (
    DEFAULT_CONCURRENCY as DEFAULT_JUDGE_CONCURRENCY,
    Agreement,
    JudgedPassage,
    JudgeModel,
    judge_agreement,
    judge_passages,
    judged_precision,
)
from testlyn_api.models.knowledge import KnowledgeChunk, KnowledgeDocument
from testlyn_api.models.org import Organization

EVAL_ORG_ID = uuid.uuid5(uuid.NAMESPACE_URL, "testlyn:knowledge-evaluation-org")
EVAL_ORG_SLUG = "knowledge-evaluation"
MODES = ("hybrid", "vector", "keyword")
# (result id, corpus doc id, chunk text, chunk char_start), best first.
Ranked = tuple[str, str, str, int]
TOP_K = 5
# Same limits as the service defaults (KNOWLEDGE_MAX_DOCUMENT_CHARS, KNOWLEDGE_MAX_CHUNKS).
INGEST_MAX_CHARS = 500_000
INGEST_MAX_CHUNKS = 2000
INGEST_DEADLINE_S = 120.0
SEARCH_DEADLINE_S = 10.0


class EvaluationRefused(RuntimeError):
    """The eval org already holds knowledge documents."""


@dataclass(frozen=True)
class QueryResult:
    query_id: str
    kind: str
    ranking: tuple[str, ...]  # "<doc_id>@<char_start>", best first
    metrics: dict[str, float]
    judged_precision: float | None = None
    judge_errors: int = 0


@dataclass(frozen=True)
class JudgeSummary:
    judged_precision: float  # mean over queries of the judged share of top_k passages
    judge_errors: int
    agreement: Agreement  # judge vs span gold, retrieved passages only


@dataclass(frozen=True)
class ModeReport:
    mode: str
    overall: dict[str, float]
    by_kind: dict[str, dict[str, float]]
    queries: tuple[QueryResult, ...]
    judge: JudgeSummary | None = None


@dataclass(frozen=True)
class EvalReport:
    embedder: str
    documents: int
    queries: int
    top_k: int
    modes: dict[str, ModeReport] = field(default_factory=dict)

    def overall(self, mode: str) -> dict[str, float]:
        return self.modes[mode].overall

    def as_dict(self) -> dict[str, Any]:
        return {
            "embedder": self.embedder,
            "documents": self.documents,
            "queries": self.queries,
            "top_k": self.top_k,
            "modes": {
                name: {
                    "overall": mode.overall,
                    "by_kind": mode.by_kind,
                    "judge": _judge_dict(mode.judge),
                    "queries": [
                        {
                            "id": q.query_id,
                            "kind": q.kind,
                            "ranking": list(q.ranking),
                            "metrics": q.metrics,
                            "judged_precision": q.judged_precision,
                            "judge_errors": q.judge_errors,
                        }
                        for q in mode.queries
                    ],
                }
                for name, mode in self.modes.items()
            },
        }


def _judge_dict(summary: JudgeSummary | None) -> dict[str, Any] | None:
    if summary is None:
        return None
    return {
        "judged_precision": summary.judged_precision,
        "judge_errors": summary.judge_errors,
        "agreement": asdict(summary.agreement),
    }


def gold_ids(query: Query) -> frozenset[str]:
    return frozenset(str(i) for i in range(len(query.relevant)))


def gold_matches(query: Query, doc_id: str, text: str) -> frozenset[str]:
    """Gold entries this chunk satisfies: same document and span inside the text."""
    return frozenset(
        str(i)
        for i, rel in enumerate(query.relevant)
        if rel.document == doc_id and rel.answer_span in text
    )


def score_query(query: Query, ranked: list[Ranked], top_k: int) -> QueryResult:
    """Score one ranked list. Each entry is (result id, doc id, chunk text, char start)."""
    matches = {rid: gold_matches(query, doc, text) for rid, doc, text, _ in ranked}
    ids = [rid for rid, _, _, _ in ranked]
    gold = gold_ids(query)
    values = {
        f"hit@{top_k}": metrics.hit_at_k(ids, matches, gold, top_k),
        f"recall@{top_k}": metrics.recall_at_k(ids, matches, gold, top_k),
        "mrr": metrics.mrr(ids, matches, gold),
        f"ndcg@{top_k}": metrics.ndcg_at_k(ids, matches, gold, top_k),
    }
    return QueryResult(
        query_id=query.id,
        kind=query.kind,
        ranking=tuple(f"{doc}@{start}" for _, doc, _, start in ranked),
        metrics=values,
    )


def aggregate(results: list[QueryResult]) -> dict[str, float]:
    if not results:
        return {}
    names = results[0].metrics.keys()
    return {
        name: sum(r.metrics[name] for r in results) / len(results) for name in names
    }


async def _count_eval_documents(engine: AsyncEngine) -> int:
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        result = await session.execute(
            select(func.count())
            .select_from(KnowledgeDocument)
            .where(KnowledgeDocument.org_id == EVAL_ORG_ID)
        )
        return int(result.scalar_one())


async def _ensure_org(engine: AsyncEngine) -> bool:
    """Create the eval org if missing. Returns True when this call created it."""
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        if await session.get(Organization, EVAL_ORG_ID) is not None:
            return False
        session.add(
            Organization(
                id=EVAL_ORG_ID,
                name="Knowledge evaluation",
                slug=EVAL_ORG_SLUG,
                plan="free",
            )
        )
        await session.commit()
    return True


async def _cleanup(engine: AsyncEngine, *, remove_org: bool) -> None:
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        # Chunks go with their documents (ON DELETE CASCADE).
        await session.execute(
            delete(KnowledgeDocument).where(KnowledgeDocument.org_id == EVAL_ORG_ID)
        )
        if remove_org:
            await session.execute(
                delete(Organization).where(Organization.id == EVAL_ORG_ID)
            )
        await session.commit()


def chunk_key(doc_id: str, ordinal: int) -> uuid.UUID:
    """Stable chunk id for the eval run.

    Search breaks exact score ties by chunk id. Random uuid4 ids would reorder
    tied chunks on every ingest, so the harness re-keys each chunk to this id.
    """
    return uuid.uuid5(EVAL_ORG_ID, f"{doc_id}:{ordinal}")


async def _ingest(
    engine: AsyncEngine, dataset: EvalSet, embedder: Embedder
) -> dict[uuid.UUID, str]:
    """Store every document. Returns document uuid -> corpus doc id."""
    factory = async_sessionmaker(engine, expire_on_commit=False)
    names: dict[uuid.UUID, str] = {}
    for doc in dataset.documents:
        async with factory() as session:
            stored, _created = await service.ingest_document(
                session,
                org_id=EVAL_ORG_ID,
                project_id=None,
                title=doc.title,
                source="upload",
                text=doc.text,
                created_by=None,
                embedder=embedder,
                max_chars=INGEST_MAX_CHARS,
                max_chunks=INGEST_MAX_CHUNKS,
                embed_deadline_s=INGEST_DEADLINE_S,
            )
            rows = await session.execute(
                select(KnowledgeChunk.id, KnowledgeChunk.ordinal).where(
                    KnowledgeChunk.document_id == stored.id
                )
            )
            for old_id, ordinal in rows.all():
                await session.execute(
                    update(KnowledgeChunk)
                    .where(KnowledgeChunk.id == old_id)
                    .values(id=chunk_key(doc.doc_id, ordinal))
                )
            await session.commit()
        names[stored.id] = doc.doc_id
    return names


async def _judge_cached(
    judge: JudgeModel,
    query: Query,
    hits: list[Any],
    cache: dict[tuple[str, str], JudgedPassage],
    concurrency: int,
) -> list[JudgedPassage]:
    """Judge each (query, chunk) pair once per run, whatever the mode."""
    missing = [hit for hit in hits if (query.id, str(hit.chunk_id)) not in cache]
    if missing:
        fresh = await judge_passages(
            judge,
            query.query,
            [hit.text for hit in missing],
            concurrency=concurrency,
        )
        for hit, judged in zip(missing, fresh, strict=True):
            cache[(query.id, str(hit.chunk_id))] = judged
    return [
        replace(cache[(query.id, str(hit.chunk_id))], index=i)
        for i, hit in enumerate(hits)
    ]


async def _search_mode(
    engine: AsyncEngine,
    dataset: EvalSet,
    names: dict[uuid.UUID, str],
    embedder: Embedder,
    mode: str,
    top_k: int,
    judge: JudgeModel | None,
    judge_concurrency: int,
    cache: dict[tuple[str, str], JudgedPassage],
) -> ModeReport:
    factory = async_sessionmaker(engine, expire_on_commit=False)
    results: list[QueryResult] = []
    gold: list[bool] = []
    judge_verdicts: list[bool | None] = []
    for query in dataset.queries:
        async with factory() as session:
            outcome = await search.run_search(
                session,
                org_id=EVAL_ORG_ID,
                project_id=None,
                query=query.query,
                mode=mode,  # type: ignore[arg-type]
                top_k=top_k,
                embedder=embedder,
                reranker=None,
                embed_deadline_s=SEARCH_DEADLINE_S,
                rerank_deadline_s=None,
            )
        ranked: list[Ranked] = [
            (str(hit.chunk_id), names[hit.document_id], hit.text, hit.char_start)
            for hit in outcome.results
        ]
        result = score_query(query, ranked, top_k)
        if judge is not None:
            # Outside the session: the judge is a network call.
            judged = await _judge_cached(
                judge, query, outcome.results, cache, judge_concurrency
            )
            verdicts = [
                None if j.verdict is None else j.verdict.relevant for j in judged
            ]
            gold.extend(
                bool(gold_matches(query, names[hit.document_id], hit.text))
                for hit in outcome.results
            )
            judge_verdicts.extend(verdicts)
            result = replace(
                result,
                judged_precision=judged_precision(judged),
                judge_errors=sum(1 for j in judged if j.verdict is None),
            )
        results.append(result)
    by_kind = {
        kind: aggregate([r for r in results if r.kind == kind])
        for kind in sorted({q.kind for q in dataset.queries})
    }
    summary = None
    if judge is not None:
        summary = JudgeSummary(
            judged_precision=sum(r.judged_precision or 0.0 for r in results)
            / len(results),
            judge_errors=sum(r.judge_errors for r in results),
            agreement=judge_agreement(gold, judge_verdicts),
        )
    return ModeReport(
        mode=mode,
        overall=aggregate(results),
        by_kind=by_kind,
        queries=tuple(results),
        judge=summary,
    )


async def run_evaluation(
    engine: AsyncEngine,
    *,
    dataset: EvalSet,
    embedder: Embedder,
    top_k: int = TOP_K,
    modes: tuple[str, ...] = MODES,
    judge: JudgeModel | None = None,
    judge_concurrency: int = DEFAULT_JUDGE_CONCURRENCY,
) -> EvalReport:
    if await _count_eval_documents(engine):
        raise EvaluationRefused(
            "the knowledge evaluation org already has documents; "
            "run against an empty database or remove them first"
        )
    created_org = await _ensure_org(engine)
    cache: dict[tuple[str, str], JudgedPassage] = {}
    try:
        names = await _ingest(engine, dataset, embedder)
        mode_reports = {
            mode: await _search_mode(
                engine,
                dataset,
                names,
                embedder,
                mode,
                top_k,
                judge,
                judge_concurrency,
                cache,
            )
            for mode in modes
        }
    finally:
        await _cleanup(engine, remove_org=created_org)
    return EvalReport(
        embedder=embedder.model_name,
        documents=len(dataset.documents),
        queries=len(dataset.queries),
        top_k=top_k,
        modes=mode_reports,
    )
