from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class MobileRunRequest(BaseModel):
    """Request body for POST /v1/products/mobile/runs."""

    org_id: UUID
    target_id: UUID = Field(..., description="ID of the registered mobile target app.")
    device_profile: str = Field(
        default="pixel-7",
        description="Device emulation profile (e.g. 'pixel-7', 'iphone-15').",
    )
    scenario: str = Field(
        default="cold-start",
        description="Test scenario to execute.",
    )


class MobileRunResponse(BaseModel):
    """Response from POST /v1/products/mobile/runs."""

    run_id: UUID
    product: Literal["mobile"] = "mobile"
    status: Literal["queued", "running", "completed", "failed"] = "queued"
    message: str | None = None
