"""Knowledge search legs and run_search against real Postgres + pgvector.

Run with: TEST_POSTGRES_URL=postgresql+asyncpg://... uv run pytest -m postgres
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Sequence

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from testlyn_api.knowledge import search, service
from testlyn_api.knowledge.embeddings import HashingEmbedder
from testlyn_api.models.knowledge import (
    KNOWLEDGE_EMBEDDING_DIM,
    KnowledgeChunk,
    KnowledgeDocument,
)
from testlyn_api.models.org import Organization
from testlyn_api.models.project import Project

pytestmark = pytest.mark.postgres

DIM = KNOWLEDGE_EMBEDDING_DIM
MODEL = HashingEmbedder().model_name
ODD_QUERIES = [
    '"unbalanced',
    "&|!():*",
    "the and of a",
    "'); DROP TABLE knowledge_chunks; --",
    "!!!",
    "a & b | !c <-> d :* (e)",
    "x" * 1000,
]


class _FixedEmbedder:
    """Returns one fixed vector for every input; stands in for the query embedder."""

    model_name = MODEL
    dim = DIM

    def __init__(self, vector: list[float]) -> None:
        self._vector = vector

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._vector for _ in texts]


def _e(axis: int, scale: float = 1.0) -> list[float]:
    vec = [0.0] * DIM
    vec[axis] = scale
    return vec


async def _org(session: AsyncSession) -> uuid.UUID:
    org = Organization(
        name="Search Org", slug=f"s-{uuid.uuid4().hex[:12]}", plan="free"
    )
    session.add(org)
    await session.flush()
    return org.id


async def _project(session: AsyncSession, org_id: uuid.UUID, name: str) -> uuid.UUID:
    project = Project(org_id=org_id, name=name, slug=f"p-{uuid.uuid4().hex[:12]}")
    session.add(project)
    await session.flush()
    return project.id


async def _ingest(
    session: AsyncSession,
    org_id: uuid.UUID,
    text: str,
    *,
    title: str,
    project_id: uuid.UUID | None = None,
) -> None:
    await service.ingest_document(
        session,
        org_id=org_id,
        project_id=project_id,
        title=title,
        source="upload",
        text=text,
        created_by=None,
        embedder=HashingEmbedder(),
        max_chars=100_000,
        max_chunks=1000,
        embed_deadline_s=None,
    )


async def _doc_with_vectors(
    session: AsyncSession,
    org_id: uuid.UUID,
    *,
    title: str,
    vectors: Sequence[list[float]],
    project_id: uuid.UUID | None = None,
) -> None:
    doc = KnowledgeDocument(
        org_id=org_id,
        project_id=project_id,
        title=title,
        source="upload",
        content_sha256=uuid.uuid4().hex + uuid.uuid4().hex,
        status="ready",
        chunk_count=len(vectors),
    )
    session.add(doc)
    await session.flush()
    for ordinal, vector in enumerate(vectors):
        session.add(
            KnowledgeChunk(
                org_id=org_id,
                document_id=doc.id,
                ordinal=ordinal,
                heading=None,
                text=f"{title} chunk {ordinal}",
                char_start=0,
                char_end=10,
                token_estimate=2,
                embedding=vector,
                embedding_model=MODEL,
            )
        )
    await session.commit()


async def _search(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    query: str,
    mode: str,
    top_k: int = 5,
    project_id: uuid.UUID | None = None,
    embedder: object | None = None,
) -> search.SearchOutcome:
    return await search.run_search(
        session,
        org_id=org_id,
        project_id=project_id,
        query=query,
        mode=mode,  # type: ignore[arg-type]
        top_k=top_k,
        embedder=embedder or HashingEmbedder(),  # type: ignore[arg-type]
        reranker=None,
        embed_deadline_s=None,
        rerank_deadline_s=None,
    )


@pytest_asyncio.fixture
async def forced_hnsw_session(
    postgres_url: str, migrated: None
) -> AsyncIterator[AsyncSession]:
    """Session whose plans must order by distance through the HNSW index.

    Small test tables would otherwise be sorted exactly (btree on org_id, then
    sort), and the recall test would pass without touching HNSW. With sequential
    scans and explicit sorts disabled, HNSW is the only path that yields
    distance order.
    """
    engine = create_async_engine(
        postgres_url,
        connect_args={
            "server_settings": {"enable_seqscan": "off", "enable_sort": "off"}
        },
    )
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as s:
            yield s
    finally:
        await engine.dispose()


# ── Filtered HNSW recall (pgvector 0.8 iterative scan) ────────────────────────


async def test_forced_plan_uses_the_hnsw_index(
    forced_hnsw_session: AsyncSession,
) -> None:
    """Guard: the recall test below is only meaningful if HNSW serves the query."""
    stmt = search.build_vector_statement(
        org_id=uuid.uuid4(),
        project_id=None,
        model_name=MODEL,
        query_vector=_e(0),
        limit=20,
    )
    compiled = str(
        stmt.compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )
    rows = await forced_hnsw_session.execute(text("EXPLAIN " + compiled))
    plan = "\n".join(row[0] for row in rows)

    assert "ix_knowledge_chunks_embedding_hnsw" in plan, plan


async def test_filtered_hnsw_returns_own_org_chunks_behind_closer_foreign_ones(
    forced_hnsw_session: AsyncSession,
) -> None:
    query = _e(0)
    org_b = await _org(forced_hnsw_session)
    org_a = await _org(forced_hnsw_session)
    # 300 chunks in org B sit almost exactly on the query; org A's three are
    # clearly further away. Without iterative scans the first HNSW candidates
    # are all B's and the org A filter leaves nothing.
    foreign = []
    for i in range(300):
        vec = _e(0)
        vec[1 + i % 200] += 0.01
        foreign.append(vec)
    await _doc_with_vectors(forced_hnsw_session, org_b, title="B doc", vectors=foreign)
    own = []
    for axis in (1, 2, 3):
        vec = _e(0)
        vec[axis] = 0.5
        own.append(vec)
    await _doc_with_vectors(forced_hnsw_session, org_a, title="A doc", vectors=own)

    outcome = await _search(
        forced_hnsw_session,
        org_id=org_a,
        query="unrelated words",
        mode="vector",
        top_k=3,
        embedder=_FixedEmbedder(query),
    )

    assert len(outcome.results) == 3
    assert {r.document_title for r in outcome.results} == {"A doc"}


# ── Legs and modes ────────────────────────────────────────────────────────────


async def _doc_id(session: AsyncSession, org_id: uuid.UUID, title: str) -> uuid.UUID:
    doc = KnowledgeDocument(
        org_id=org_id,
        title=title,
        source="upload",
        content_sha256=uuid.uuid4().hex + uuid.uuid4().hex,
        status="ready",
        chunk_count=0,
    )
    session.add(doc)
    await session.flush()
    return doc.id


async def test_vector_leg_only_compares_chunks_of_the_current_model(
    session: AsyncSession,
) -> None:
    org_id = await _org(session)
    other_model = KnowledgeChunk(
        org_id=org_id,
        document_id=await _doc_id(session, org_id, "Other model"),
        ordinal=99,
        heading=None,
        text="other",
        char_start=0,
        char_end=5,
        token_estimate=1,
        embedding=_e(0),
        embedding_model="some-other-model",
    )
    session.add(other_model)
    await session.commit()

    hits = await search.vector_candidates(
        session,
        org_id=org_id,
        project_id=None,
        model_name=MODEL,
        query_vector=_e(0),
        limit=10,
    )

    assert hits == []


@pytest.mark.parametrize("query", ODD_QUERIES)
@pytest.mark.parametrize("mode", ["hybrid", "vector", "keyword"])
async def test_odd_queries_never_raise(
    session: AsyncSession, query: str, mode: str
) -> None:
    org_id = await _org(session)
    await _ingest(session, org_id, "Restart the worker. # Notes", title="N")

    outcome = await _search(session, org_id=org_id, query=query, mode=mode)

    assert isinstance(outcome.results, list)


async def test_keyword_leg_finds_exact_term_and_hybrid_surfaces_it(
    session: AsyncSession,
) -> None:
    org_id = await _org(session)
    # Distractors share only stopwords with the query, so the hashing vector
    # ranks them first while the keyword leg matches none of them.
    for i in range(6):
        await _ingest(
            session,
            org_id,
            f"the after the after the {i} after the the after the",
            title=f"Distractor {i}",
        )
    await _ingest(
        session,
        org_id,
        "Error QX7731 means the signing key rotated. Reissue the token.",
        title="Target",
    )
    query = "QX7731 after the"

    vector_top = await _search(
        session, org_id=org_id, query=query, mode="vector", top_k=3
    )
    keyword = await _search(
        session, org_id=org_id, query=query, mode="keyword", top_k=3
    )
    hybrid = await _search(session, org_id=org_id, query=query, mode="hybrid", top_k=3)

    assert "Target" not in [r.document_title for r in vector_top.results]
    assert [r.document_title for r in keyword.results] == ["Target"]
    assert keyword.results[0].keyword_rank == 1
    assert keyword.results[0].vector_rank is None
    assert hybrid.results[0].document_title == "Target"
    assert hybrid.results[0].keyword_rank == 1
    assert hybrid.results[0].vector_rank is not None
    assert hybrid.reranked is False


async def test_result_citation_fields_are_populated(
    session: AsyncSession,
) -> None:
    org_id = await _org(session)
    await _ingest(
        session,
        org_id,
        "# Runbook\n\nRollback runs the revert job.",
        title="Runbook",
    )

    outcome = await _search(
        session, org_id=org_id, query="rollback revert", mode="hybrid"
    )

    (result,) = outcome.results
    assert result.document_title == "Runbook"
    assert result.source == "upload"
    assert result.heading == "Runbook"
    assert result.char_end > result.char_start >= 0
    assert "revert" in result.text
    assert result.keyword_rank == 1 and result.vector_rank == 1
    assert result.score > 0


# ── Scope and tenancy ─────────────────────────────────────────────────────────


async def test_project_scope_includes_org_wide_and_own_project_only(
    session: AsyncSession,
) -> None:
    org_id = await _org(session)
    p1 = await _project(session, org_id, "P1")
    p2 = await _project(session, org_id, "P2")
    await _ingest(session, org_id, "shared widget manual", title="Shared")
    await _ingest(session, org_id, "p1 widget guide", title="P1 doc", project_id=p1)
    await _ingest(session, org_id, "p2 widget guide", title="P2 doc", project_id=p2)

    def titles(outcome: search.SearchOutcome) -> set[str]:
        return {r.document_title for r in outcome.results}

    in_p1 = await _search(
        session, org_id=org_id, query="widget", mode="keyword", project_id=p1
    )
    org_wide = await _search(session, org_id=org_id, query="widget", mode="keyword")

    assert titles(in_p1) == {"Shared", "P1 doc"}
    assert titles(org_wide) == {"Shared", "P1 doc", "P2 doc"}


@pytest.mark.parametrize("mode", ["hybrid", "vector", "keyword"])
async def test_search_never_returns_another_orgs_chunks(
    session: AsyncSession, mode: str
) -> None:
    org_x = await _org(session)
    org_y = await _org(session)
    await _ingest(session, org_x, "zebra crossing rules", title="X doc")
    await _ingest(session, org_y, "zebra crossing rules", title="Y doc")

    outcome = await _search(session, org_id=org_x, query="zebra", mode=mode)

    assert outcome.results, "expected org X to find its own document"
    assert {r.document_title for r in outcome.results} == {"X doc"}
