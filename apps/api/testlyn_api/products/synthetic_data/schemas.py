from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field


class GenerateRequest(BaseModel):
    """Request body for POST /v1/products/synthetic-data/generate."""

    org_id: UUID
    dsn_secret_id: str = Field(
        ...,
        description="Secret Manager secret ID for the Postgres DSN (e.g. 'testlyn-synth-dsn').",
    )
    schema_overrides: dict[str, Any] = Field(
        default_factory=dict,
        description="Per-table column overrides. Key = table name, value = {col: faker_provider}.",
    )
    gdpr_masking_rules: dict[str, Any] = Field(
        default_factory=dict,
        description="GDPR masking rules as JSONB. Key = table.column, value = mask strategy.",
    )
    row_count: int = Field(
        default=100,
        ge=1,
        le=100_000,
        description="Rows to generate per table.",
    )
    output_mode: Literal["gcs", "insert"] = Field(
        default="gcs",
        description="'gcs' writes a SQL dump to GCS; 'insert' inserts directly via DSN.",
    )


class GenerateResponse(BaseModel):
    """Response from POST /v1/products/synthetic-data/generate."""

    job_id: UUID
    product: Literal["synthetic_data"] = "synthetic_data"
    status: Literal["queued", "running", "completed", "failed"] = "queued"
    dump_gcs_uri: str | None = Field(
        default=None,
        description="GCS URI of the SQL dump (when output_mode='gcs').",
    )
    rows_inserted: int | None = Field(
        default=None,
        description="Rows inserted (when output_mode='insert').",
    )
    message: str | None = None
