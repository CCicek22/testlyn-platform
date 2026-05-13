from __future__ import annotations

import uuid

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from testlyn_api.deps import CurrentUserDep, SessionDep
from testlyn_api.products.cicd_insights.schemas import CicdRunIngestRequest

router = APIRouter(prefix="/v1/products/cicd-insights", tags=["cicd_insights"])

_NOT_IMPLEMENTED = {
    "code": "NOT_IMPLEMENTED",
    "detail": "CI/CD Insights is not yet available.",
    "available_in": "Phase 4 GA",
}


@router.post("/runs")
async def ingest_run(
    body: CicdRunIngestRequest,
    current_user: CurrentUserDep,
    session: SessionDep,
) -> JSONResponse:
    """Ingest a CI/CD pipeline run. Returns 501 until Phase 4 GA."""
    return JSONResponse(status_code=501, content=_NOT_IMPLEMENTED)


@router.get("/runs/{run_id}")
async def get_run(
    run_id: uuid.UUID,
    current_user: CurrentUserDep,
    session: SessionDep,
) -> JSONResponse:
    """Fetch a CI/CD run record. Returns 501 until Phase 4 GA."""
    return JSONResponse(status_code=501, content=_NOT_IMPLEMENTED)
