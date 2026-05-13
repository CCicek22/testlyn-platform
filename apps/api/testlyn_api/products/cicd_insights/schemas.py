from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class CicdRunIngestRequest(BaseModel):
    """Request body for POST /v1/products/cicd-insights/runs."""

    org_id: UUID
    pipeline_id: str = Field(..., description="External pipeline identifier.")
    duration_ms: int = Field(..., ge=0, description="Total pipeline duration in ms.")
    flaky_test_count: int = Field(default=0, ge=0)
    cost_estimate_usd: float = Field(
        default=0.0,
        ge=0.0,
        description="Estimated compute cost for this run in USD.",
    )


class CicdRunResponse(BaseModel):
    """Response from POST /v1/products/cicd-insights/runs."""

    run_id: UUID
    product: Literal["cicd_insights"] = "cicd_insights"
    message: str | None = None
