from __future__ import annotations

import uuid

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from testlyn_api.deps import CurrentUserDep, SessionDep
from testlyn_api.products.rum.schemas import RumSiteRegisterRequest

router = APIRouter(prefix="/v1/products/rum", tags=["rum"])

_NOT_IMPLEMENTED = {
    "code": "NOT_IMPLEMENTED",
    "detail": "Real User Monitoring is not yet available.",
    "available_in": "Phase 4 GA",
}


@router.post("/sites")
async def register_site(
    body: RumSiteRegisterRequest,
    current_user: CurrentUserDep,
    session: SessionDep,
) -> JSONResponse:
    """Register a site for RUM collection. Returns 501 until Phase 4 GA."""
    return JSONResponse(status_code=501, content=_NOT_IMPLEMENTED)


@router.get("/sites/{site_id}/pageviews")
async def get_pageviews(
    site_id: uuid.UUID,
    current_user: CurrentUserDep,
    session: SessionDep,
) -> JSONResponse:
    """Fetch aggregated pageview metrics. Returns 501 until Phase 4 GA."""
    return JSONResponse(status_code=501, content=_NOT_IMPLEMENTED)
