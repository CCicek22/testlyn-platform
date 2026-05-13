from __future__ import annotations

import uuid

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from testlyn_api.deps import CurrentUserDep, SessionDep
from testlyn_api.products.visual.schemas import VisualScanRequest

router = APIRouter(prefix="/v1/products/visual", tags=["visual"])

_NOT_IMPLEMENTED = {
    "code": "NOT_IMPLEMENTED",
    "detail": "Visual regression testing is not yet available.",
    "available_in": "Phase 4 GA",
}


@router.post("/scans")
async def create_scan(
    body: VisualScanRequest,
    current_user: CurrentUserDep,
    session: SessionDep,
) -> JSONResponse:
    """Enqueue a visual regression scan. Returns 501 until Phase 4 GA."""
    return JSONResponse(status_code=501, content=_NOT_IMPLEMENTED)


@router.get("/scans/{scan_id}")
async def get_scan(
    scan_id: uuid.UUID,
    current_user: CurrentUserDep,
    session: SessionDep,
) -> JSONResponse:
    """Fetch a visual scan result. Returns 501 until Phase 4 GA."""
    return JSONResponse(status_code=501, content=_NOT_IMPLEMENTED)
