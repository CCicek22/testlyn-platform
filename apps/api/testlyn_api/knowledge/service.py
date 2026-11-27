"""Knowledge document ingestion and lookup. Every query filters by org_id."""

from __future__ import annotations

import hashlib
import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import defer

from testlyn_api.knowledge.chunking import chunk_markdown
from testlyn_api.knowledge.embeddings import Embedder
from testlyn_api.models.knowledge import KnowledgeChunk, KnowledgeDocument

STATUS_READY = "ready"


class KnowledgeInputError(ValueError):
    """Rejected input (empty, too large, or no chunkable content)."""


async def ingest_document(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    project_id: uuid.UUID | None,
    title: str,
    source: str,
    text: str,
    created_by: uuid.UUID | None,
    embedder: Embedder,
    max_chars: int,
) -> tuple[KnowledgeDocument, bool]:
    """Store a document and its embedded chunks.

    Returns ``(document, created)``. Identical text in the same org is a no-op
    and returns the existing document with ``created=False``. Embedding runs
    before any write, so a failing embedder leaves nothing behind.
    """
    if not text.strip():
        raise KnowledgeInputError("text must not be empty")
    if len(text) > max_chars:
        raise KnowledgeInputError(f"text exceeds {max_chars} characters")

    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    existing = await _find_by_sha(session, org_id, digest)
    if existing is not None:
        return existing, False

    chunks = chunk_markdown(text)
    if not chunks:
        raise KnowledgeInputError("text has no content to index")

    vectors = await embedder.embed([chunk.text for chunk in chunks])

    document = KnowledgeDocument(
        org_id=org_id,
        project_id=project_id,
        title=title,
        source=source,
        content_sha256=digest,
        status=STATUS_READY,
        chunk_count=len(chunks),
        created_by=created_by,
    )
    session.add(document)
    try:
        await session.flush()
        for chunk, vector in zip(chunks, vectors, strict=True):
            session.add(
                KnowledgeChunk(
                    org_id=org_id,
                    document_id=document.id,
                    ordinal=chunk.ordinal,
                    heading=chunk.heading,
                    text=chunk.text,
                    char_start=chunk.char_start,
                    char_end=chunk.char_end,
                    token_estimate=chunk.token_estimate,
                    embedding=vector,
                    embedding_model=embedder.model_name,
                )
            )
        await session.commit()
    except IntegrityError:
        # A concurrent request stored the same text between our lookup and insert.
        await session.rollback()
        winner = await _find_by_sha(session, org_id, digest)
        if winner is None:
            raise
        return winner, False
    except Exception:
        await session.rollback()
        raise

    await session.refresh(document)
    return document, True


async def list_documents(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    project_id: uuid.UUID | None,
    limit: int,
    offset: int,
) -> list[KnowledgeDocument]:
    stmt = select(KnowledgeDocument).where(KnowledgeDocument.org_id == org_id)
    if project_id is not None:
        stmt = stmt.where(KnowledgeDocument.project_id == project_id)
    stmt = (
        stmt.order_by(KnowledgeDocument.created_at.desc(), KnowledgeDocument.id.desc())
        .limit(limit)
        .offset(offset)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_document(
    session: AsyncSession, *, org_id: uuid.UUID, document_id: uuid.UUID
) -> KnowledgeDocument | None:
    result = await session.execute(
        select(KnowledgeDocument).where(
            KnowledgeDocument.id == document_id, KnowledgeDocument.org_id == org_id
        )
    )
    return result.scalar_one_or_none()


async def list_chunks(
    session: AsyncSession, *, org_id: uuid.UUID, document_id: uuid.UUID
) -> list[KnowledgeChunk]:
    """Chunks of one document, ordered, without loading the embedding column."""
    result = await session.execute(
        select(KnowledgeChunk)
        .options(defer(KnowledgeChunk.embedding))
        .where(
            KnowledgeChunk.org_id == org_id, KnowledgeChunk.document_id == document_id
        )
        .order_by(KnowledgeChunk.ordinal)
    )
    return list(result.scalars().all())


async def delete_document(
    session: AsyncSession, *, org_id: uuid.UUID, document_id: uuid.UUID
) -> bool:
    """Delete a document; its chunks go with it via ON DELETE CASCADE."""
    document = await get_document(session, org_id=org_id, document_id=document_id)
    if document is None:
        return False
    await session.delete(document)
    await session.commit()
    return True


async def _find_by_sha(
    session: AsyncSession, org_id: uuid.UUID, digest: str
) -> KnowledgeDocument | None:
    result = await session.execute(
        select(KnowledgeDocument).where(
            KnowledgeDocument.org_id == org_id,
            KnowledgeDocument.content_sha256 == digest,
        )
    )
    return result.scalar_one_or_none()
