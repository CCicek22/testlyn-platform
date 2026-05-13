from __future__ import annotations

import uuid

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from testlyn_api.deps import CurrentUserDep, SessionDep
from testlyn_api.products.qa_maturity.schemas import QaMaturityAssessRequest

router = APIRouter(prefix="/v1/products/qa-maturity", tags=["qa_maturity"])

_NOT_IMPLEMENTED = {
    "code": "NOT_IMPLEMENTED",
    "detail": "QA Maturity assessments are not yet available.",
    "available_in": "Phase 4 GA",
}


@router.post("/assessments")
async def create_assessment(
    body: QaMaturityAssessRequest,
    current_user: CurrentUserDep,
    session: SessionDep,
) -> JSONResponse:
    """Submit a QA maturity questionnaire. Returns 501 until Phase 4 GA."""
    return JSONResponse(status_code=501, content=_NOT_IMPLEMENTED)


@router.get("/assessments/{assessment_id}")
async def get_assessment(
    assessment_id: uuid.UUID,
    current_user: CurrentUserDep,
    session: SessionDep,
) -> JSONResponse:
    """Fetch an assessment result. Returns 501 until Phase 4 GA."""
    return JSONResponse(status_code=501, content=_NOT_IMPLEMENTED)
