from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field


class QaMaturityAssessRequest(BaseModel):
    """Request body for POST /v1/products/qa-maturity/assessments."""

    org_id: UUID
    answers: dict[str, Any] = Field(
        ...,
        description="Questionnaire answers keyed by question ID.",
    )


class QaMaturityAssessResponse(BaseModel):
    """Response from POST /v1/products/qa-maturity/assessments."""

    assessment_id: UUID
    product: Literal["qa_maturity"] = "qa_maturity"
    score: float | None = Field(
        default=None,
        description="Maturity score 0–100.",
    )
    generated_roadmap_md: str | None = Field(
        default=None,
        description="LLM-generated improvement roadmap in Markdown.",
    )
    message: str | None = None
