from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class TdmSubsetRequest(BaseModel):
    """Request body for POST /v1/products/tdm/subset-jobs."""

    org_id: UUID
    dsn_secret_id: str = Field(
        ...,
        description="Secret Manager secret ID for the source database DSN.",
    )
    tables: list[str] = Field(
        ...,
        min_length=1,
        description="List of tables to include in the subset.",
    )
    row_limit: int = Field(
        default=10_000,
        ge=1,
        description="Maximum rows to extract per table.",
    )
    output_bucket: str = Field(
        ...,
        description="GCS bucket name for the subset output.",
    )


class TdmSubsetResponse(BaseModel):
    """Response from POST /v1/products/tdm/subset-jobs."""

    job_id: UUID
    product: Literal["tdm"] = "tdm"
    status: Literal["queued", "running", "completed", "failed"] = "queued"
    output_uri: str | None = None
    message: str | None = None
