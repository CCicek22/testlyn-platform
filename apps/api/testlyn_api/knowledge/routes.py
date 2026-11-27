from __future__ import annotations

import uuid
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from testlyn_api.config import get_settings
from testlyn_api.core.permissions import _enforce_perm
from testlyn_api.deps import CurrentUserDep, SessionDep
from testlyn_api.knowledge import service
from testlyn_api.knowledge.embeddings import Embedder, get_embedder
from testlyn_api.models.knowledge import KnowledgeDocument
from testlyn_api.models.project import Project
from testlyn_api.schemas.knowledge import (
    KnowledgeChunkOut,
    KnowledgeDocumentCreate,
    KnowledgeDocumentDetail,
    KnowledgeDocumentOut,
)

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/v1/orgs/{org_id}/knowledge", tags=["knowledge"])

EmbedderDep = Annotated[Embedder, Depends(get_embedder)]


@router.post(
    "/documents",
    response_model=KnowledgeDocumentOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_document(
    org_id: uuid.UUID,
    body: KnowledgeDocumentCreate,
    response: Response,
    current_user: CurrentUserDep,
    session: SessionDep,
    embedder: EmbedderDep,
) -> KnowledgeDocumentOut:
    await _enforce_perm(
        "write", "project", user_id=current_user.id, org_id=org_id, session=session
    )
    if body.project_id is not None:
        await _get_project_or_404(org_id, body.project_id, session)

    try:
        document, created = await service.ingest_document(
            session,
            org_id=org_id,
            project_id=body.project_id,
            title=body.title,
            source=body.source,
            text=body.text,
            created_by=current_user.id,
            embedder=embedder,
            max_chars=get_settings().knowledge_max_document_chars,
        )
    except service.KnowledgeInputError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

    if not created:
        response.status_code = status.HTTP_200_OK
    log.info(
        "knowledge.document_ingested", document_id=str(document.id), created=created
    )
    return KnowledgeDocumentOut.model_validate(document)


@router.get("/documents", response_model=list[KnowledgeDocumentOut])
async def list_documents(
    org_id: uuid.UUID,
    current_user: CurrentUserDep,
    session: SessionDep,
    project_id: uuid.UUID | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> list[KnowledgeDocumentOut]:
    await _enforce_perm(
        "read", "project", user_id=current_user.id, org_id=org_id, session=session
    )
    documents = await service.list_documents(
        session, org_id=org_id, project_id=project_id, limit=limit, offset=offset
    )
    return [KnowledgeDocumentOut.model_validate(d) for d in documents]


@router.get("/documents/{document_id}", response_model=KnowledgeDocumentDetail)
async def get_document(
    org_id: uuid.UUID,
    document_id: uuid.UUID,
    current_user: CurrentUserDep,
    session: SessionDep,
) -> KnowledgeDocumentDetail:
    await _enforce_perm(
        "read", "project", user_id=current_user.id, org_id=org_id, session=session
    )
    document = await _get_document_or_404(org_id, document_id, session)
    chunks = await service.list_chunks(session, org_id=org_id, document_id=document.id)
    return KnowledgeDocumentDetail(
        **KnowledgeDocumentOut.model_validate(document).model_dump(),
        chunks=[KnowledgeChunkOut.model_validate(c) for c in chunks],
    )


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    org_id: uuid.UUID,
    document_id: uuid.UUID,
    current_user: CurrentUserDep,
    session: SessionDep,
) -> None:
    await _enforce_perm(
        "delete", "project", user_id=current_user.id, org_id=org_id, session=session
    )
    deleted = await service.delete_document(
        session, org_id=org_id, document_id=document_id
    )
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Document not found"
        )


async def _get_document_or_404(
    org_id: uuid.UUID, document_id: uuid.UUID, session: AsyncSession
) -> KnowledgeDocument:
    document = await service.get_document(
        session, org_id=org_id, document_id=document_id
    )
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Document not found"
        )
    return document


async def _get_project_or_404(
    org_id: uuid.UUID, project_id: uuid.UUID, session: AsyncSession
) -> None:
    result = await session.execute(
        select(Project.id).where(Project.id == project_id, Project.org_id == org_id)
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
        )
