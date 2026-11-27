"""Knowledge document ingestion and lookup. Every query filters by org_id."""

from __future__ import annotations

import asyncio
import hashlib
import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import defer

from testlyn_api.knowledge.chunking import chunk_markdown
from testlyn_api.knowledge.embeddings import Embedder, EmbeddingError
from testlyn_api.models.knowledge import KnowledgeChunk, KnowledgeDocument

STATUS_READY = "ready"


class KnowledgeInputError(ValueError):
    """Rejected input (empty, too large, or too many chunks)."""


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
    max_chunks: int,
    embed_deadline_s: float | None,
) -> tuple[KnowledgeDocument, bool]:
    """Store a document and its embedded chunks.

    Returns ``(document, created)``. Identical text in the same org and project
    is a no-op and returns the existing document with ``created=False``.

    Embedding runs with no database transaction open, so a slow embedder does
    not pin a pooled connection. It also runs before any write, so a failing or
    timed-out embedder leaves nothing behind. Raises ``EmbeddingError`` when the
    embedder fails or exceeds ``embed_deadline_s``.
    """
    if not text.strip():
        raise KnowledgeInputError("text must not be empty")
    if len(text) > max_chars:
        raise KnowledgeInputError(f"text exceeds {max_chars} characters")

    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    existing = await _find_existing(session, org_id, project_id, digest)
    if existing is not None:
        return existing, False

    chunks = chunk_markdown(text)
    if not chunks:
        raise KnowledgeInputError("text has no content to index")
    if len(chunks) > max_chunks:
        raise KnowledgeInputError(f"text would produce more than {max_chunks} chunks")

    # End the read transaction so the connection returns to the pool before the
    # slow embedding call. Nothing loaded above is used after this point.
    await session.commit()
    try:
        async with asyncio.timeout(embed_deadline_s):
            vectors = await embedder.embed([chunk.text for chunk in chunks])
    except TimeoutError as exc:
        raise EmbeddingError("embedding deadline exceeded") from exc

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
        winner = await _find_existing(session, org_id, project_id, digest)
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
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    document_id: uuid.UUID,
    limit: int,
    offset: int,
) -> list[KnowledgeChunk]:
    """One page of a document's chunks, ordered, without the embedding column."""
    result = await session.execute(
        select(KnowledgeChunk)
        .options(defer(KnowledgeChunk.embedding))
        .where(
            KnowledgeChunk.org_id == org_id,
            KnowledgeChunk.document_id == document_id,
        )
        .order_by(KnowledgeChunk.ordinal)
        .limit(limit)
        .offset(offset)
    )
    return list(result.scalars().all())


async def delete_document(session: AsyncSession, document: KnowledgeDocument) -> None:
    """Delete a document; its chunks go with it via ON DELETE CASCADE."""
    await session.delete(document)
    await session.commit()


async def _find_existing(
    session: AsyncSession,
    org_id: uuid.UUID,
    project_id: uuid.UUID | None,
    digest: str,
) -> KnowledgeDocument | None:
    # is_not_distinct_from: a NULL project matches only a NULL project.
    result = await session.execute(
        select(KnowledgeDocument).where(
            KnowledgeDocument.org_id == org_id,
            KnowledgeDocument.project_id.is_not_distinct_from(project_id),
            KnowledgeDocument.content_sha256 == digest,
        )
    )
    return result.scalar_one_or_none()
