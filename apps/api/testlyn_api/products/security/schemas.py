from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, HttpUrl


class ZapScanRequest(BaseModel):
    """Request body for POST /v1/products/security/scan."""

    org_id: UUID
    target_url: HttpUrl = Field(
        ...,
        description="URL of the application to scan.",
    )
    auth_recipe_id: UUID | None = Field(
        default=None,
        description="Optional auth recipe ID (stored Playwright trace) for authenticated scans.",
    )
    scan_kind: Literal["baseline", "full"] = Field(
        default="baseline",
        description="'baseline' = passive + light active; 'full' = comprehensive active scan.",
    )


class ZapFinding(BaseModel):
    """A single ZAP finding."""

    plugin_id: str
    alert: str
    risk: Literal["high", "medium", "low", "informational"]
    confidence: Literal["high", "medium", "low"]
    url: str
    description: str
    solution: str | None = None
    reference: str | None = None


class SecurityScanResponse(BaseModel):
    """Response from POST /v1/products/security/scan."""

    scan_id: UUID
    product: Literal["security"] = "security"
    status: Literal["queued", "running", "completed", "failed"] = "queued"
    scan_kind: Literal["baseline", "full"] = "baseline"
    findings_count: int = 0
    findings: list[ZapFinding] = Field(default_factory=list)
    report_gcs_uri: str | None = None
    message: str | None = None
