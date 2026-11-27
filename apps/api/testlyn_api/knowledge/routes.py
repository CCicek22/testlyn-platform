from __future__ import annotations

import uuid
from typing import Annotated

import structlog
from collections.abc import Awaitable, Callable

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from testlyn_api.config import get_settings
from testlyn_api.core.permissions import _enforce_perm
from testlyn_api.deps import CurrentUserDep, SessionDep
from testlyn_api.knowledge import search, service
from testlyn_api.knowledge.embeddings import Embedder, EmbeddingError, get_embedder
from testlyn_api.knowledge.rerank import Reranker, get_reranker
from testlyn_api.models.knowledge import KnowledgeDocument
from testlyn_api.models.project import Project
from testlyn_api.schemas.knowledge import (
    KnowledgeChunkOut,
    KnowledgeDocumentCreate,
    KnowledgeDocumentDetail,
    KnowledgeDocumentOut,
    KnowledgeSearchRequest,
    KnowledgeSearchResponse,
    KnowledgeSearchResult,
)

log = structlog.get_logger(__name__)


class _SafeValidationRoute(APIRoute):
    """Keep validation errors encodable.

    Pydantic echoes the rejected value into ``input``. A lone surrogate there
    cannot be encoded as UTF-8, so the default 422 response would crash. Drop
    ``input`` and ``ctx`` for this router only.
    """

    def get_route_handler(self) -> Callable[[Request], Awaitable[Response]]:
        original = super().get_route_handler()

        async def handler(request: Request) -> Response:
            try:
                return await original(request)
            except RequestValidationError as exc:
                errors = [
                    {k: v for k, v in err.items() if k not in ("input", "ctx")}
                    for err in exc.errors()
                ]
                return JSONResponse(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    content={"detail": jsonable_encoder(errors)},
                )

        return handler


router = APIRouter(
    prefix="/v1/orgs/{org_id}/knowledge",
    tags=["knowledge"],
    route_class=_SafeValidationRoute,
)

EmbedderDep = Annotated[Embedder, Depends(get_embedder)]
RerankerDep = Annotated[Reranker | None, Depends(get_reranker)]

# Permission model: every route first requires org membership (any role), so
# non-members get 403 and nothing about the org leaks. The action check then
# uses the project-aware matrix, so a project role override is honoured. A
# document with no project follows the org role.


async def _require_member(
    org_id: uuid.UUID, user_id: uuid.UUID, session: AsyncSession
) -> None:
    await _enforce_perm(
        "read", "project", user_id=user_id, org_id=org_id, session=session
    )


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
    await _require_member(org_id, current_user.id, session)
    if body.project_id is not None:
        # Verify the project belongs to this org before its id is used for
        # permissions: the override lookup does not check the org.
        await _get_project_or_404(org_id, body.project_id, session)
    await _enforce_perm(
        "write",
        "project",
        user_id=current_user.id,
        org_id=org_id,
        project_id=body.project_id,
        session=session,
    )

    settings = get_settings()
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
            max_chars=settings.knowledge_max_document_chars,
            max_chunks=settings.knowledge_max_chunks,
            embed_deadline_s=settings.knowledge_embedding_deadline_seconds,
        )
    except service.KnowledgeInputError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    except EmbeddingError as exc:
        # Generic message only: no endpoint, status body, or key reaches the client.
        log.warning("knowledge.embedding_unavailable", reason=str(exc))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Embedding service unavailable, try again later",
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
    await _require_member(org_id, current_user.id, session)
    if project_id is not None:
        await _get_project_or_404(org_id, project_id, session)
        await _enforce_perm(
            "read",
            "project",
            user_id=current_user.id,
            org_id=org_id,
            project_id=project_id,
            session=session,
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
    chunk_limit: int = Query(100, ge=1, le=500),
    chunk_offset: int = Query(0, ge=0),
) -> KnowledgeDocumentDetail:
    await _require_member(org_id, current_user.id, session)
    document = await _get_document_or_404(org_id, document_id, session)
    await _enforce_perm(
        "read",
        "project",
        user_id=current_user.id,
        org_id=org_id,
        project_id=document.project_id,
        session=session,
    )
    chunks = await service.list_chunks(
        session,
        org_id=org_id,
        document_id=document.id,
        limit=chunk_limit,
        offset=chunk_offset,
    )
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
    await _require_member(org_id, current_user.id, session)
    document = await _get_document_or_404(org_id, document_id, session)
    await _enforce_perm(
        "delete",
        "project",
        user_id=current_user.id,
        org_id=org_id,
        project_id=document.project_id,
        session=session,
    )
    await service.delete_document(session, document)


@router.post("/search", response_model=KnowledgeSearchResponse)
async def search_knowledge(
    org_id: uuid.UUID,
    body: KnowledgeSearchRequest,
    current_user: CurrentUserDep,
    session: SessionDep,
    embedder: EmbedderDep,
    reranker: RerankerDep,
) -> KnowledgeSearchResponse:
    # Org-wide search covers every document of the org: no role or override can
    # remove a member's project read access (viewer is the lowest role and
    # overrides are limited to the same four roles), so nothing is excluded.
    await _require_member(org_id, current_user.id, session)
    if body.project_id is not None:
        await _get_project_or_404(org_id, body.project_id, session)
        await _enforce_perm(
            "read",
            "project",
            user_id=current_user.id,
            org_id=org_id,
            project_id=body.project_id,
            session=session,
        )

    settings = get_settings()
    try:
        outcome = await search.run_search(
            session,
            org_id=org_id,
            project_id=body.project_id,
            query=body.query,
            mode=body.mode,
            top_k=body.top_k,
            embedder=embedder,
            reranker=reranker,
            embed_deadline_s=settings.knowledge_search_embedding_deadline_seconds,
            rerank_deadline_s=settings.knowledge_reranker_deadline_seconds,
        )
    except EmbeddingError as exc:
        # Generic message only: no endpoint, status body, or key reaches the client.
        log.warning("knowledge.embedding_unavailable", reason=str(exc))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Embedding service unavailable, try again later",
        ) from exc

    return KnowledgeSearchResponse(
        results=[KnowledgeSearchResult.model_validate(r) for r in outcome.results],
        mode=body.mode,
        reranked=outcome.reranked,
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
