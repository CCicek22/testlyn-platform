from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, HttpUrl


class RumSiteRegisterRequest(BaseModel):
    """Request body for POST /v1/products/rum/sites."""

    org_id: UUID
    target_id: UUID
    origin: HttpUrl = Field(..., description="Origin URL of the site to monitor.")


class RumSiteResponse(BaseModel):
    """Response from POST /v1/products/rum/sites."""

    site_id: UUID
    product: Literal["rum"] = "rum"
    snippet_id: str = Field(..., description="JS snippet ID to embed in the site.")
    message: str | None = None


class RumPageviewSummary(BaseModel):
    """Aggregated RUM metrics for a URL."""

    url: str
    lcp_p75_ms: float | None = None
    fid_p75_ms: float | None = None
    cls_p75: float | None = None
    sample_count: int = 0
