from __future__ import annotations

import uuid

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from testlyn_api.deps import CurrentUserDep, SessionDep
from testlyn_api.products.eng_analytics.schemas import EngAnalyticsConnectRequest

router = APIRouter(prefix="/v1/products/eng-analytics", tags=["eng_analytics"])

_NOT_IMPLEMENTED = {
    "code": "NOT_IMPLEMENTED",
    "detail": "Engineering Analytics is not yet available.",
    "available_in": "Phase 4 GA",
}


@router.post("/connections")
async def create_connection(
    body: EngAnalyticsConnectRequest,
    current_user: CurrentUserDep,
    session: SessionDep,
) -> JSONResponse:
    """Register an engineering data source connection. Returns 501 until Phase 4 GA."""
    return JSONResponse(status_code=501, content=_NOT_IMPLEMENTED)


@router.get("/connections/{connection_id}")
async def get_connection(
    connection_id: uuid.UUID,
    current_user: CurrentUserDep,
    session: SessionDep,
) -> JSONResponse:
    """Fetch a connection. Returns 501 until Phase 4 GA."""
    return JSONResponse(status_code=501, content=_NOT_IMPLEMENTED)
