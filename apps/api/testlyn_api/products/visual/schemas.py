from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, HttpUrl


class IgnoreRegion(BaseModel):
    """A rectangular region to exclude from visual diff."""

    x: int
    y: int
    width: int
    height: int


class VisualScanRequest(BaseModel):
    """Request body for POST /v1/products/visual/scans."""

    org_id: UUID
    target_id: UUID
    baseline_uri: str = Field(..., description="GCS URI of the baseline screenshot.")
    current_uri: str = Field(..., description="GCS URI of the current screenshot.")
    ignore_regions: list[IgnoreRegion] = Field(
        default_factory=list,
        description="Regions to exclude from diff comparison.",
    )


class VisualScanResponse(BaseModel):
    """Response from POST /v1/products/visual/scans."""

    scan_id: UUID
    product: Literal["visual"] = "visual"
    status: Literal["queued", "running", "completed", "failed"] = "queued"
    diff_pixel_ratio: float | None = None
    message: str | None = None
