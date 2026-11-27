"""Knowledge search: candidate legs, reciprocal rank fusion, optional rerank.

Inside ``run_search`` no database transaction is open during a network call.
The query is embedded and the reranker is called only after the session has
been committed, so a pooled connection is never held while waiting on them.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

import structlog
from sqlalchemy import Text, cast, column, func, literal, or_, select
from sqlalchemy.dialects.postgresql import REGCONFIG, TSQUERY, TSVECTOR
from sqlalchemy.ext.asyncio import AsyncSession

from testlyn_api.knowledge.embeddings import Embedder, EmbeddingError
from testlyn_api.knowledge.rerank import Reranker
from testlyn_api.models.knowledge import KnowledgeChunk, KnowledgeDocument

log = structlog.get_logger(__name__)

RRF_K = 60
MIN_CANDIDATES = 20
MAX_CANDIDATES = 100
SEARCH_LANGUAGE = "english"
HNSW_MIN_EF_SEARCH = 40
HNSW_MAX_EF_SEARCH = 1000

SearchMode = Literal["hybrid", "vector", "keyword"]

# Generated column from migration 0015 (to_tsvector over heading and text).
# Kept out of the ORM mapping; referenced by name only.
_TEXT_TSV = column("text_tsv", TSVECTOR)


@dataclass(frozen=True)
class FusedHit:
    chunk_id: uuid.UUID
    score: float
    vector_rank: int | None
    keyword_rank: int | None


@dataclass(frozen=True)
class Hit:
    """One chunk returned by a candidate leg, in leg order."""

    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_title: str
    source: str
    heading: str | None
    text: str
    char_start: int
    char_end: int


@dataclass(frozen=True)
class SearchResult:
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_title: str
    source: str
    heading: str | None
    text: str
    char_start: int
    char_end: int
    score: float
    vector_rank: int | None
    keyword_rank: int | None


@dataclass(frozen=True)
class SearchOutcome:
    results: list[SearchResult]
    reranked: bool


def candidate_limit(top_k: int) -> int:
    """Rows each leg fetches before fusion."""
    return min(max(top_k * 4, MIN_CANDIDATES), MAX_CANDIDATES)


def rrf_fuse(
    vector_ids: Sequence[uuid.UUID],
    keyword_ids: Sequence[uuid.UUID],
    *,
    k: int = RRF_K,
) -> list[FusedHit]:
    """Fuse two ranked id lists: score = sum over legs of 1 / (k + rank).

    Ranks are 1-based positions in each leg after dropping repeats (the first
    occurrence counts). Output is sorted by score, highest first, then by
    chunk id, so equal scores always come out in the same order.
    """
    ranks: dict[uuid.UUID, list[int | None]] = {}
    for leg_index, leg in enumerate((vector_ids, keyword_ids)):
        seen: set[uuid.UUID] = set()
        position = 0
        for chunk_id in leg:
            if chunk_id in seen:
                continue
            seen.add(chunk_id)
            position += 1
            ranks.setdefault(chunk_id, [None, None])[leg_index] = position

    fused: list[FusedHit] = []
    for chunk_id, (vector_rank, keyword_rank) in ranks.items():
        score = 0.0
        if vector_rank is not None:
            score += 1 / (k + vector_rank)
        if keyword_rank is not None:
            score += 1 / (k + keyword_rank)
        fused.append(
            FusedHit(
                chunk_id=chunk_id,
                score=score,
                vector_rank=vector_rank,
                keyword_rank=keyword_rank,
            )
        )
    fused.sort(key=lambda hit: (-hit.score, hit.chunk_id))
    return fused


def _base_select(org_id: uuid.UUID, project_id: uuid.UUID | None):  # type: ignore[no-untyped-def]
    stmt = (
        select(
            KnowledgeChunk.id.label("chunk_id"),
            KnowledgeChunk.document_id.label("document_id"),
            KnowledgeDocument.title.label("document_title"),
            KnowledgeDocument.source.label("source"),
            KnowledgeChunk.heading.label("heading"),
            KnowledgeChunk.text.label("text"),
            KnowledgeChunk.char_start.label("char_start"),
            KnowledgeChunk.char_end.label("char_end"),
        )
        .join(
            KnowledgeDocument,
            (KnowledgeDocument.id == KnowledgeChunk.document_id)
            & (KnowledgeDocument.org_id == KnowledgeChunk.org_id),
        )
        .where(KnowledgeChunk.org_id == org_id)
    )
    if project_id is not None:
        # Org-wide documents (no project) apply to every project.
        stmt = stmt.where(
            or_(
                KnowledgeDocument.project_id == project_id,
                KnowledgeDocument.project_id.is_(None),
            )
        )
    return stmt


async def _fetch_hits(session: AsyncSession, stmt) -> list[Hit]:  # type: ignore[no-untyped-def]
    result = await session.execute(stmt)
    return [Hit(**row._mapping) for row in result]


def build_vector_statement(
    *,
    org_id: uuid.UUID,
    project_id: uuid.UUID | None,
    model_name: str,
    query_vector: list[float],
    limit: int,
):  # type: ignore[no-untyped-def]
    """ORDER BY cosine distance so the HNSW index serves the query.

    Chunk id breaks distance ties. The planner keeps the index scan and adds an
    incremental sort, so equal-distance chunks come back in the same order on
    every run.
    """
    distance = KnowledgeChunk.embedding.cosine_distance(query_vector)
    return (
        _base_select(org_id, project_id)
        .where(KnowledgeChunk.embedding_model == model_name)
        .order_by(distance, KnowledgeChunk.id)
        .limit(limit)
    )


async def vector_candidates(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    project_id: uuid.UUID | None,
    model_name: str,
    query_vector: list[float],
    limit: int,
) -> list[Hit]:
    """Nearest chunks by cosine distance, same embedding model only.

    The WHERE clause runs after the HNSW index yields candidates, so a plain
    scan can return fewer than ``limit`` rows when other orgs' chunks are
    closer. pgvector 0.8 iterative scans keep reading the index until enough
    rows survive the filter (bounded by ``hnsw.max_scan_tuples``). The settings
    are transaction-local and apply to the query that follows in this call.
    """
    await session.execute(
        select(func.set_config("hnsw.iterative_scan", "strict_order", True))
    )
    ef_search = min(max(2 * limit, HNSW_MIN_EF_SEARCH), HNSW_MAX_EF_SEARCH)
    await session.execute(
        select(func.set_config("hnsw.ef_search", str(ef_search), True))
    )
    stmt = build_vector_statement(
        org_id=org_id,
        project_id=project_id,
        model_name=model_name,
        query_vector=query_vector,
        limit=limit,
    )
    return await _fetch_hits(session, stmt)


def keyword_tsquery(query: str):  # type: ignore[no-untyped-def]
    """Any-term tsquery: plainto_tsquery ANDs the words, so AND becomes OR.

    plainto_tsquery emits quoted lexemes joined only by " & " (no spaces inside a
    lexeme), so the replace touches separators only.
    """
    language = cast(literal(SEARCH_LANGUAGE), REGCONFIG)
    anded = cast(func.plainto_tsquery(language, query), Text)
    return cast(func.replace(anded, " & ", " | "), TSQUERY)


def keyword_match(query: str):  # type: ignore[no-untyped-def]
    """WHERE clause that the GIN index on text_tsv can serve."""
    return _TEXT_TSV.op("@@")(keyword_tsquery(query))


def build_keyword_statement(
    *,
    org_id: uuid.UUID,
    project_id: uuid.UUID | None,
    query: str,
    limit: int,
):  # type: ignore[no-untyped-def]
    """Full-text statement. The language is a bound parameter, not SQL text."""
    tsquery = keyword_tsquery(query)
    return (
        _base_select(org_id, project_id)
        .where(keyword_match(query))
        .order_by(func.ts_rank_cd(_TEXT_TSV, tsquery).desc(), KnowledgeChunk.id)
        .limit(limit)
    )


async def keyword_candidates(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    project_id: uuid.UUID | None,
    query: str,
    limit: int,
) -> list[Hit]:
    """Any-term full-text matches ranked by ts_rank_cd. Query text never raises."""
    stmt = build_keyword_statement(
        org_id=org_id, project_id=project_id, query=query, limit=limit
    )
    return await _fetch_hits(session, stmt)


async def _embed_query(
    embedder: Embedder, query: str, deadline_s: float | None
) -> list[float]:
    try:
        async with asyncio.timeout(deadline_s):
            vectors = await embedder.embed([query])
    except TimeoutError as exc:
        raise EmbeddingError("embedding deadline exceeded") from exc
    return vectors[0]


async def _rerank(
    reranker: Reranker,
    query: str,
    documents: list[str],
    top_n: int,
    deadline_s: float | None,
) -> list[tuple[int, float]] | None:
    """Reranked (index, score) pairs, or None to keep the fused order."""
    # Reranking is optional, so any failure keeps the fused order. CancelledError
    # is a BaseException and still propagates. Only the type name is logged.
    try:
        async with asyncio.timeout(deadline_s):
            return await reranker.rerank(query, documents, top_n=top_n)
    except Exception as exc:
        log.warning("knowledge.rerank_fallback", reason=type(exc).__name__)
        return None


async def run_search(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    project_id: uuid.UUID | None,
    query: str,
    mode: SearchMode,
    top_k: int,
    embedder: Embedder,
    reranker: Reranker | None,
    embed_deadline_s: float | None,
    rerank_deadline_s: float | None,
) -> SearchOutcome:
    """Run the requested legs, fuse them, and optionally rerank.

    Raises ``EmbeddingError`` when the query embedding fails or exceeds
    ``embed_deadline_s``. A reranker failure never raises: the fused order is
    returned with ``reranked=False``.
    """
    limit = candidate_limit(top_k)

    # End the read transaction left by the permission checks before any
    # network call (embedding, reranking).
    await session.commit()
    query_vector = None
    if mode != "keyword":
        query_vector = await _embed_query(embedder, query, embed_deadline_s)

    vector_hits: list[Hit] = []
    if query_vector is not None:
        vector_hits = await vector_candidates(
            session,
            org_id=org_id,
            project_id=project_id,
            model_name=embedder.model_name,
            query_vector=query_vector,
            limit=limit,
        )
    keyword_hits: list[Hit] = []
    if mode != "vector":
        keyword_hits = await keyword_candidates(
            session,
            org_id=org_id,
            project_id=project_id,
            query=query,
            limit=limit,
        )
    await session.commit()

    by_id: dict[uuid.UUID, Hit] = {}
    for hit in (*vector_hits, *keyword_hits):
        by_id.setdefault(hit.chunk_id, hit)
    fused = rrf_fuse(
        [hit.chunk_id for hit in vector_hits],
        [hit.chunk_id for hit in keyword_hits],
    )
    pool = fused[:limit]

    chosen: list[tuple[FusedHit, float]] = [(hit, hit.score) for hit in fused[:top_k]]
    reranked = False
    if reranker is not None and pool:
        order = await _rerank(
            reranker,
            query,
            [by_id[hit.chunk_id].text for hit in pool],
            top_k,
            rerank_deadline_s,
        )
        if order is not None:
            reranked = True
            ordered = sorted(order, key=lambda pair: (-pair[1], pair[0]))
            chosen = [(pool[index], score) for index, score in ordered[:top_k]]

    results = []
    for fused_hit, score in chosen:
        hit = by_id[fused_hit.chunk_id]
        results.append(
            SearchResult(
                chunk_id=hit.chunk_id,
                document_id=hit.document_id,
                document_title=hit.document_title,
                source=hit.source,
                heading=hit.heading,
                text=hit.text,
                char_start=hit.char_start,
                char_end=hit.char_end,
                score=score,
                vector_rank=fused_hit.vector_rank,
                keyword_rank=fused_hit.keyword_rank,
            )
        )
    return SearchOutcome(results=results, reranked=reranked)
