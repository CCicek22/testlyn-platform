"""Knowledge store schema against real Postgres + pgvector (migration 0015).

Run with: TEST_POSTGRES_URL=postgresql+asyncpg://... uv run pytest -m postgres
Raw SQL here is test-only (catalog queries); app code uses the ORM.
"""

from __future__ import annotations

import subprocess
import uuid
from collections.abc import Callable

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from testlyn_api.models.knowledge import (
    KNOWLEDGE_EMBEDDING_DIM,
    KnowledgeChunk,
    KnowledgeDocument,
)
from testlyn_api.models.org import Organization

pytestmark = pytest.mark.postgres


async def _seed_document(
    session: AsyncSession, chunks: int = 1
) -> tuple[uuid.UUID, uuid.UUID]:
    org = Organization(name="PG Org", slug=f"pg-{uuid.uuid4().hex[:8]}", plan="free")
    session.add(org)
    await session.flush()
    doc = KnowledgeDocument(
        org_id=org.id,
        title="Runbook",
        source="upload",
        content_sha256=uuid.uuid4().hex + uuid.uuid4().hex[:32],
        status="ready",
        chunk_count=chunks,
    )
    session.add(doc)
    await session.flush()
    return org.id, doc.id


def _chunk(
    org_id: uuid.UUID, document_id: uuid.UUID, ordinal: int, dim: int
) -> KnowledgeChunk:
    return KnowledgeChunk(
        org_id=org_id,
        document_id=document_id,
        ordinal=ordinal,
        heading="Runbook",
        text=f"chunk {ordinal}",
        char_start=0,
        char_end=7,
        token_estimate=2,
        embedding=[0.5] * dim,
        embedding_model="test",
    )


async def test_upgrade_head_from_empty_database(
    run_alembic: Callable[..., subprocess.CompletedProcess[str]], fresh_schema: None
) -> None:
    result = run_alembic("upgrade", "head")
    assert result.returncode == 0, result.stderr
    assert "0014 -> 0015" in result.stderr


async def test_vector_extension_is_installed(session: AsyncSession) -> None:
    row = await session.execute(
        text("SELECT extname FROM pg_extension WHERE extname = 'vector'")
    )
    assert row.scalar_one() == "vector"


async def test_knowledge_indexes_exist(session: AsyncSession) -> None:
    rows = await session.execute(
        text(
            "SELECT indexname, indexdef FROM pg_indexes WHERE tablename = 'knowledge_chunks'"
        )
    )
    defs = dict(rows.all())
    assert "hnsw" in defs["ix_knowledge_chunks_embedding_hnsw"]
    assert "vector_cosine_ops" in defs["ix_knowledge_chunks_embedding_hnsw"]
    assert "gin" in defs["ix_knowledge_chunks_text_tsv"]
    assert "uq_knowledge_chunks_document_ordinal" in defs
    assert "uq_knowledge_documents_org_project_sha" in {
        name
        for (name,) in (
            await session.execute(
                text(
                    "SELECT conname FROM pg_constraint WHERE conrelid = 'knowledge_documents'::regclass"
                )
            )
        ).all()
    }


async def test_text_tsv_is_generated_column(session: AsyncSession) -> None:
    row = await session.execute(
        text(
            "SELECT is_generated FROM information_schema.columns "
            "WHERE table_name = 'knowledge_chunks' AND column_name = 'text_tsv'"
        )
    )
    assert row.scalar_one() == "ALWAYS"


async def test_chunk_round_trips_256_dimensional_embedding(
    session: AsyncSession,
) -> None:
    assert KNOWLEDGE_EMBEDDING_DIM == 256
    org_id, doc_id = await _seed_document(session)
    session.add(_chunk(org_id, doc_id, 0, KNOWLEDGE_EMBEDDING_DIM))
    await session.commit()
    session.expire_all()

    stored = (await session.execute(select(KnowledgeChunk))).scalar_one()
    assert len(stored.embedding) == KNOWLEDGE_EMBEDDING_DIM
    assert all(abs(x - 0.5) < 1e-6 for x in stored.embedding)


async def test_inserting_255_dimensional_embedding_fails(session: AsyncSession) -> None:
    org_id, doc_id = await _seed_document(session)
    session.add(_chunk(org_id, doc_id, 0, KNOWLEDGE_EMBEDDING_DIM - 1))
    with pytest.raises(DBAPIError):
        await session.commit()
    await session.rollback()


async def test_deleting_document_cascades_to_chunks(session: AsyncSession) -> None:
    org_id, doc_id = await _seed_document(session, chunks=2)
    session.add_all(
        [_chunk(org_id, doc_id, i, KNOWLEDGE_EMBEDDING_DIM) for i in range(2)]
    )
    await session.commit()

    doc = await session.get(KnowledgeDocument, doc_id)
    assert doc is not None
    await session.delete(doc)
    await session.commit()
    session.expire_all()

    remaining = (await session.execute(select(KnowledgeChunk))).scalars().all()
    assert remaining == []


async def test_downgrade_then_upgrade_round_trip(
    run_alembic: Callable[..., subprocess.CompletedProcess[str]],
    engine: AsyncEngine,
    migrated: None,
) -> None:
    down = run_alembic("downgrade", "-1")
    assert down.returncode == 0, down.stderr
    async with engine.connect() as conn:
        tables = await conn.execute(
            text("SELECT tablename FROM pg_tables WHERE tablename LIKE 'knowledge_%'")
        )
        assert tables.all() == []

    up = run_alembic("upgrade", "head")
    assert up.returncode == 0, up.stderr
    async with engine.connect() as conn:
        tables = await conn.execute(
            text(
                "SELECT tablename FROM pg_tables WHERE tablename LIKE 'knowledge_%' ORDER BY 1"
            )
        )
        assert [name for (name,) in tables.all()] == [
            "knowledge_chunks",
            "knowledge_documents",
        ]


async def test_duplicate_null_project_document_is_rejected(
    session: AsyncSession,
) -> None:
    # NULLS NOT DISTINCT: two org-level documents with the same text collide.
    org_id, _ = await _seed_document(session)
    sha = "ab" * 32
    session.add(
        KnowledgeDocument(
            org_id=org_id,
            project_id=None,
            title="first",
            source="upload",
            content_sha256=sha,
            status="ready",
            chunk_count=0,
        )
    )
    await session.commit()
    session.add(
        KnowledgeDocument(
            org_id=org_id,
            project_id=None,
            title="second",
            source="upload",
            content_sha256=sha,
            status="ready",
            chunk_count=0,
        )
    )
    with pytest.raises(IntegrityError):
        await session.commit()
    await session.rollback()


async def test_unique_constraint_is_nulls_not_distinct(session: AsyncSession) -> None:
    row = await session.execute(
        text(
            "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
            "WHERE conname = 'uq_knowledge_documents_org_project_sha'"
        )
    )
    assert "NULLS NOT DISTINCT" in row.scalar_one()


async def test_nul_byte_in_title_is_rejected_by_database(session: AsyncSession) -> None:
    # Postgres text cannot hold NUL; the server rejects the insert.
    org_id, _ = await _seed_document(session)
    session.add(
        KnowledgeDocument(
            org_id=org_id,
            title="bad\x00title",
            source="upload",
            content_sha256="cd" * 32,
            status="ready",
            chunk_count=0,
        )
    )
    with pytest.raises(DBAPIError, match="0x00"):
        await session.commit()
    await session.rollback()
