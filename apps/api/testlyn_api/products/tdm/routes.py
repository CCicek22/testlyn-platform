from __future__ import annotations

import uuid

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from testlyn_api.deps import CurrentUserDep, SessionDep
from testlyn_api.products.tdm.schemas import TdmSubsetRequest

router = APIRouter(prefix="/v1/products/tdm", tags=["tdm"])

_NOT_IMPLEMENTED = {
    "code": "NOT_IMPLEMENTED",
    "detail": "Test Data Management (subsetting) is not yet available.",
    "available_in": "Phase 4 GA",
}


@router.post("/subset-jobs")
async def create_subset_job(
    body: TdmSubsetRequest,
    current_user: CurrentUserDep,
    session: SessionDep,
) -> JSONResponse:
    """Enqueue a data subsetting job. Returns 501 until Phase 4 GA."""
    return JSONResponse(status_code=501, content=_NOT_IMPLEMENTED)


@router.get("/subset-jobs/{job_id}")
async def get_subset_job(
    job_id: uuid.UUID,
    current_user: CurrentUserDep,
    session: SessionDep,
) -> JSONResponse:
    """Fetch a subsetting job status. Returns 501 until Phase 4 GA."""
    return JSONResponse(status_code=501, content=_NOT_IMPLEMENTED)
