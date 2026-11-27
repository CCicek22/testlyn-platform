"""Knowledge search legs and run_search against real Postgres + pgvector.

Run with: TEST_POSTGRES_URL=postgresql+asyncpg://... uv run pytest -m postgres
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Sequence

import pytest
import pytest_asyncio
from sqlalchemy import func, select, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
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


async def test_forced_keyword_match_uses_the_gin_index_with_bound_language(
    forced_hnsw_session: AsyncSession,
) -> None:
    """The @@ predicate, with asyncpg-bound language and query, is served by GIN.

    The full keyword statement adds an org_id filter; on a near-empty table the
    planner prefers the org_id btree there (measured), so the GIN proof uses the
    predicate alone with seqscan and sort disabled.
    """
    stmt = select(KnowledgeChunk.id).where(search.keyword_match("refund policy"))
    conn = await forced_hnsw_session.connection()
    compiled = stmt.compile(dialect=conn.dialect)
    params = [compiled.params[name] for name in compiled.positiontup or []]
    rows = await conn.exec_driver_sql("EXPLAIN " + str(compiled), tuple(params))
    plan = "\n".join(row[0] for row in rows)

    assert "ix_knowledge_chunks_text_tsv" in plan, plan
    assert "'english'" not in str(compiled), str(compiled)


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


async def test_equal_distance_chunks_come_back_in_chunk_id_order(
    forced_hnsw_session: AsyncSession,
) -> None:
    """Ties in distance are broken by chunk id, so the leg is repeatable.

    Forty chunks share one vector. Without the tie-break the index returns
    them in graph order, which differs between builds.
    """
    org_id = await _org(forced_hnsw_session)
    await _doc_with_vectors(
        forced_hnsw_session, org_id, title="Ties", vectors=[_e(0)] * 40
    )
    rows = await forced_hnsw_session.execute(
        select(KnowledgeChunk.id).where(KnowledgeChunk.org_id == org_id)
    )
    expected = sorted(rows.scalars().all())[:20]

    hits = await search.vector_candidates(
        forced_hnsw_session,
        org_id=org_id,
        project_id=None,
        model_name=MODEL,
        query_vector=_e(0),
        limit=20,
    )

    assert [hit.chunk_id for hit in hits] == expected


async def test_project_scoped_hnsw_skips_sibling_project_and_foreign_org_chunks(
    forced_hnsw_session: AsyncSession,
) -> None:
    query = _e(0)
    org_b = await _org(forced_hnsw_session)
    org_a = await _org(forced_hnsw_session)
    project_p = await _project(forced_hnsw_session, org_a, "P")
    project_q = await _project(forced_hnsw_session, org_a, "Q")
    close = []
    for i in range(300):
        vec = _e(0)
        vec[1 + i % 200] += 0.01
        close.append(vec)
    # Closer chunks in a sibling project of the same org and in another org.
    await _doc_with_vectors(
        forced_hnsw_session, org_a, title="Q doc", vectors=close, project_id=project_q
    )
    await _doc_with_vectors(forced_hnsw_session, org_b, title="B doc", vectors=close)
    own = [_e(axis, 0.5) for axis in (1, 2, 3)]
    await _doc_with_vectors(
        forced_hnsw_session, org_a, title="P doc", vectors=own, project_id=project_p
    )

    outcome = await _search(
        forced_hnsw_session,
        org_id=org_a,
        project_id=project_p,
        query="unrelated words",
        mode="vector",
        top_k=3,
        embedder=_FixedEmbedder(query),
    )

    assert len(outcome.results) == 3
    assert {r.document_title for r in outcome.results} == {"P doc"}


async def test_project_scoped_statement_plan_uses_the_hnsw_index(
    forced_hnsw_session: AsyncSession,
) -> None:
    stmt = search.build_vector_statement(
        org_id=uuid.uuid4(),
        project_id=uuid.uuid4(),
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


class _RecordingReranker:
    """Records whether the search session holds a transaction during the call."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self.in_transaction_during_call: list[bool] = []

    async def rerank(
        self, query: str, documents: list[str], *, top_n: int
    ) -> list[tuple[int, float]]:
        self.in_transaction_during_call.append(self._session.in_transaction())
        return [(index, float(-index)) for index in range(min(top_n, len(documents)))]


async def test_real_legs_leave_no_transaction_open_for_the_reranker(
    session: AsyncSession,
) -> None:
    org_id = await _org(session)
    await _ingest(session, org_id, "refund policy for annual plans", title="Refunds")
    await _ingest(session, org_id, "shipping times by region", title="Shipping")
    reranker = _RecordingReranker(session)

    outcome = await search.run_search(
        session,
        org_id=org_id,
        project_id=None,
        query="refund policy",
        mode="hybrid",
        top_k=2,
        embedder=HashingEmbedder(),
        reranker=reranker,  # type: ignore[arg-type]
        embed_deadline_s=None,
        rerank_deadline_s=None,
    )

    assert outcome.reranked is True
    assert reranker.in_transaction_during_call == [False]


async def test_search_settings_do_not_leak_to_the_pooled_connection(
    postgres_url: str, migrated: None
) -> None:
    """One pooled connection only: any SET that survives the search would show."""
    engine = create_async_engine(postgres_url, pool_size=1, max_overflow=0)
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as s:
            org_id = await _org(s)
            await _ingest(s, org_id, "alpha beta gamma", title="Leak")
            await search.run_search(
                s,
                org_id=org_id,
                project_id=None,
                query="alpha",
                mode="hybrid",
                top_k=3,
                embedder=HashingEmbedder(),
                reranker=None,
                embed_deadline_s=None,
                rerank_deadline_s=None,
            )
            row = (
                await s.execute(
                    text(
                        "SELECT current_setting('hnsw.iterative_scan'), "
                        "current_setting('hnsw.ef_search')"
                    )
                )
            ).one()
            await s.commit()

        assert tuple(row) == ("off", "40")
    finally:
        await engine.dispose()


# ── Keyword leg: any-term matching ────────────────────────────────────────────

# Each hostile query is paired with the plain words it must behave like. The
# lexemes are identical, so the result titles must be identical too.
HOSTILE_PAIRS = [
    ("'alpha' | 'beta'", "alpha beta"),
    ("alpha & beta", "alpha beta"),
    ('alpha "beta"', "alpha beta"),
    ("alpha\\beta", "alpha beta"),
    ("alpha ! beta", "alpha beta"),
    ("alpha (beta) :* <-> gamma", "alpha beta gamma"),
    ("alpha\x07beta", "alpha beta"),
    ("alpha\tbeta\r\n", "alpha beta"),
    ("alpha 'beta", "alpha beta"),
    ("a'b\"c`d", "b c d"),
    ("ünïcödé alpha", "ünïcödé alpha"),
    ("alpha " + "x" * 3000 + " beta", "alpha " + "x" * 3000 + " beta"),
]


async def _keyword_titles(
    session: AsyncSession, org_id: uuid.UUID, query: str
) -> list[str]:
    outcome = await _search(
        session, org_id=org_id, query=query, mode="keyword", top_k=10
    )
    return [r.document_title for r in outcome.results]


async def test_keyword_any_term_returns_chunk_with_only_one_term(
    session: AsyncSession,
) -> None:
    org_id = await _org(session)
    await _ingest(session, org_id, "Only alpha appears in this note.", title="Alpha")
    await _ingest(session, org_id, "Nothing relevant here.", title="Other")

    titles = await _keyword_titles(session, org_id, "alpha missingterm")

    assert titles == ["Alpha"]


async def test_keyword_ranks_chunk_with_two_terms_above_one_term(
    session: AsyncSession,
) -> None:
    """Fixture-specific: ts_rank_cd scores occurrences and proximity, not a
    count of distinct terms, so this only pins this pair of chunks."""
    org_id = await _org(session)
    await _ingest(session, org_id, "alpha only here.", title="One term")
    await _ingest(session, org_id, "alpha and beta together.", title="Two terms")

    titles = await _keyword_titles(session, org_id, "alpha beta")

    assert titles == ["Two terms", "One term"]


@pytest.mark.parametrize("query", ["the and of", "!!! ... ???", "a an the", "  "])
async def test_stopword_or_punctuation_only_query_returns_nothing(
    session: AsyncSession, query: str
) -> None:
    org_id = await _org(session)
    await _ingest(session, org_id, "The alpha note of the day.", title="Note")

    assert await _keyword_titles(session, org_id, query) == []


@pytest.mark.parametrize(("hostile", "plain"), HOSTILE_PAIRS)
async def test_hostile_keyword_input_matches_its_plain_words(
    session: AsyncSession, hostile: str, plain: str
) -> None:
    org_id = await _org(session)
    foreign_org = await _org(session)
    await _ingest(session, org_id, "alpha beta gamma delta", title="Mine")
    await _ingest(session, foreign_org, "alpha beta gamma delta", title="Foreign")

    hostile_titles = await _keyword_titles(session, org_id, hostile)

    assert hostile_titles == await _keyword_titles(session, org_id, plain)
    assert "Foreign" not in hostile_titles


async def test_injected_syntax_is_dropped_not_interpreted(
    session: AsyncSession,
) -> None:
    """Quotes, & and | do not bind anything: each word is an independent OR branch."""
    org_id = await _org(session)
    await _ingest(session, org_id, "alpha note", title="Alpha")
    await _ingest(session, org_id, "beta note", title="Beta")
    await _ingest(session, org_id, "gamma note", title="Gamma")

    for query in [
        "'alpha' | 'beta'",
        "alpha & beta",
        "alpha:* | beta",
        "(alpha) !beta",
    ]:
        assert sorted(await _keyword_titles(session, org_id, query)) == [
            "Alpha",
            "Beta",
        ], query


async def test_quoted_phrase_is_matched_as_loose_terms(session: AsyncSession) -> None:
    """Quote characters are dropped. "gate timeout" matches a chunk that has only
    "timeout", as the unquoted words would."""
    org_id = await _org(session)
    await _ingest(session, org_id, "The timeout is long.", title="Timeout only")

    assert await _keyword_titles(session, org_id, '"gate timeout"') == ["Timeout only"]


async def test_minus_is_not_an_exclusion_operator(session: AsyncSession) -> None:
    """A leading minus is dropped. The excluded word still matches."""
    org_id = await _org(session)
    await _ingest(session, org_id, "beta alone.", title="Beta")

    assert await _keyword_titles(session, org_id, "alpha -beta") == ["Beta"]


async def test_or_is_an_english_stopword_and_is_dropped(session: AsyncSession) -> None:
    """ "or" is removed by the english stopword list, like "the". "alpha or beta"
    is the same query as "alpha beta"."""
    org_id = await _org(session)
    await _ingest(session, org_id, "beta alone.", title="Beta")
    await _ingest(session, org_id, "alpha alone.", title="Alpha")

    assert sorted(await _keyword_titles(session, org_id, "alpha or beta")) == [
        "Alpha",
        "Beta",
    ]
    assert sorted(await _keyword_titles(session, org_id, "alpha beta")) == [
        "Alpha",
        "Beta",
    ]


async def test_any_term_keyword_respects_org_and_project_scope(
    session: AsyncSession,
) -> None:
    """Two-term query. "beta" appears only in a foreign org and a sibling project,
    so neither may be returned for a project-scoped search."""
    org_a = await _org(session)
    org_b = await _org(session)
    project = await _project(session, org_a, "Scoped")
    sibling = await _project(session, org_a, "Sibling")
    await _ingest(session, org_a, "alpha in org wide", title="Org Wide")
    await _ingest(
        session, org_a, "alpha in project", title="Project", project_id=project
    )
    await _ingest(
        session, org_a, "beta in sibling", title="Sibling", project_id=sibling
    )
    await _ingest(session, org_b, "alpha and beta in foreign org", title="Foreign")

    scoped = await _search(
        session, org_id=org_a, query="alpha beta", mode="keyword", project_id=project
    )
    org_wide = await _search(session, org_id=org_a, query="alpha beta", mode="keyword")

    assert sorted(r.document_title for r in scoped.results) == ["Org Wide", "Project"]
    assert sorted(r.document_title for r in org_wide.results) == [
        "Org Wide",
        "Project",
        "Sibling",
    ]


async def test_keyword_query_with_forty_distinct_words_is_capped(
    session: AsyncSession,
) -> None:
    """Word 1 is kept, word 40 is past KEYWORD_MAX_TERMS and dropped."""
    words = [f"word{chr(97 + n // 26)}{chr(97 + n % 26)}" for n in range(40)]
    org_id = await _org(session)
    await _ingest(session, org_id, f"only {words[0]} here", title="First")
    await _ingest(session, org_id, f"only {words[39]} here", title="Last")

    titles = await _keyword_titles(session, org_id, " ".join(words))

    assert titles == ["First"]


@pytest.mark.parametrize("word_count", [0, 1, search.KEYWORD_MAX_TERMS, 33, 40])
async def test_built_query_never_has_more_than_the_cap(
    session: AsyncSession, word_count: int
) -> None:
    """numnode of a cap-sized OR is 2 * 32 - 1 = 63; 1000 hostile chars stay under."""
    words = " ".join(f"term{n}x" for n in range(word_count))
    nodes = await session.scalar(select(func.numnode(search.keyword_tsquery(words))))

    assert nodes <= 2 * search.KEYWORD_MAX_TERMS - 1


async def test_hostile_thousand_chars_stay_under_the_node_cap(
    session: AsyncSession,
) -> None:
    hostile = ("alpha-beta.gamma/delta 'x' & | ! (y) " * 40)[:1000]
    nodes = await session.scalar(select(func.numnode(search.keyword_tsquery(hostile))))

    assert 0 < nodes <= 2 * search.KEYWORD_MAX_TERMS - 1


async def test_url_path_with_apostrophe_round_trips(session: AsyncSession) -> None:
    org_id = await _org(session)
    await _ingest(session, org_id, "see x.com/it's/ok for details", title="Url")

    assert await _keyword_titles(session, org_id, "x.com/it's/ok") == ["Url"]
    assert await _keyword_titles(session, org_id, "see x.com/it's/ok for details") == [
        "Url"
    ]


async def test_ampersand_inside_a_term_round_trips(session: AsyncSession) -> None:
    org_id = await _org(session)
    await _ingest(session, org_id, "the route /a&b is slow", title="Route")

    assert await _keyword_titles(session, org_id, "/a&b") == ["Route"]
    assert await _keyword_titles(session, org_id, "slow /a&b") == ["Route"]


async def test_keyword_timeout_raises_and_the_session_recovers(
    engine: AsyncEngine, session: AsyncSession
) -> None:
    org_id = await _org(session)
    await _ingest(session, org_id, "alpha note", title="Alpha")
    await session.commit()

    async with engine.begin() as blocker:
        await blocker.execute(
            text("LOCK TABLE knowledge_chunks IN ACCESS EXCLUSIVE MODE")
        )
        with pytest.raises(search.KeywordSearchTimeout):
            await search.run_search(
                session,
                org_id=org_id,
                project_id=None,
                query="alpha",
                mode="keyword",
                top_k=5,
                embedder=HashingEmbedder(),
                reranker=None,
                embed_deadline_s=None,
                rerank_deadline_s=None,
                keyword_timeout_ms=1,
            )

    outcome = await _search(session, org_id=org_id, query="alpha", mode="keyword")
    assert [r.document_title for r in outcome.results] == ["Alpha"]
    assert (await session.execute(text("SHOW statement_timeout"))).scalar_one() == "0"


async def test_keyword_timeout_setting_is_restored_after_a_normal_search(
    session: AsyncSession,
) -> None:
    org_id = await _org(session)
    await _ingest(session, org_id, "alpha note", title="Alpha")

    outcome = await search.run_search(
        session,
        org_id=org_id,
        project_id=None,
        query="alpha",
        mode="hybrid",
        top_k=5,
        embedder=HashingEmbedder(),
        reranker=None,
        embed_deadline_s=None,
        rerank_deadline_s=None,
        keyword_timeout_ms=5000,
    )

    assert [r.document_title for r in outcome.results] == ["Alpha"]
    assert (await session.execute(text("SHOW statement_timeout"))).scalar_one() == "0"
