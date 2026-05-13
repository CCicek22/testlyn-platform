from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, HttpUrl


class HypothesisSettings(BaseModel):
    """Schemathesis hypothesis test settings."""

    max_examples: int = Field(default=50, ge=1, le=1000)
    derandomize: bool = Field(default=False)
    suppress_health_check: list[str] = Field(default_factory=list)


class ContractScanRequest(BaseModel):
    """Request body for POST /v1/products/api-contract/scan."""

    org_id: UUID
    openapi_url: HttpUrl = Field(
        ...,
        description="URL to the OpenAPI spec (JSON or YAML) to validate against.",
    )
    target_url: HttpUrl = Field(
        ...,
        description="Base URL of the API under test.",
    )
    hypothesis_settings: HypothesisSettings = Field(
        default_factory=HypothesisSettings,
        description="Schemathesis / Hypothesis settings.",
    )


class DriftFinding(BaseModel):
    """A single contract drift finding from Schemathesis."""

    method: str
    path: str
    status_code: int
    failure_reason: str
    response_snippet: str | None = None


class ContractScanResponse(BaseModel):
    """Response from POST /v1/products/api-contract/scan."""

    scan_id: UUID
    product: Literal["api_contract"] = "api_contract"
    status: Literal["queued", "running", "completed", "failed"] = "queued"
    drift_count: int = 0
    findings: list[DriftFinding] = Field(default_factory=list)
    report_gcs_uri: str | None = None
    message: str | None = None
