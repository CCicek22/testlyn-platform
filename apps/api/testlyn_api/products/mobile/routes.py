from __future__ import annotations

import uuid

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from testlyn_api.deps import CurrentUserDep, SessionDep
from testlyn_api.products.mobile.schemas import MobileRunRequest

router = APIRouter(prefix="/v1/products/mobile", tags=["mobile"])

_NOT_IMPLEMENTED = {
    "code": "NOT_IMPLEMENTED",
    "detail": "Mobile performance testing is not yet available.",
    "available_in": "Phase 4 GA",
}


@router.post("/runs")
async def create_run(
    body: MobileRunRequest,
    current_user: CurrentUserDep,
    session: SessionDep,
) -> JSONResponse:
    """Enqueue a mobile performance test run. Returns 501 until Phase 4 GA."""
    return JSONResponse(status_code=501, content=_NOT_IMPLEMENTED)


@router.get("/runs/{run_id}")
async def get_run(
    run_id: uuid.UUID,
    current_user: CurrentUserDep,
    session: SessionDep,
) -> JSONResponse:
    """Fetch a mobile run. Returns 501 until Phase 4 GA."""
    return JSONResponse(status_code=501, content=_NOT_IMPLEMENTED)
