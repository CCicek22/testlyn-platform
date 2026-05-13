from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field


class EngAnalyticsConnectRequest(BaseModel):
    """Request body for POST /v1/products/eng-analytics/connections."""

    org_id: UUID
    provider: Literal["github", "gitlab", "jira", "linear"] = Field(
        ...,
        description="Source code / issue tracker provider.",
    )
    config: dict[str, Any] = Field(
        default_factory=dict,
        description="Provider-specific config (repo slugs, project keys, etc.).",
    )


class EngAnalyticsConnectionResponse(BaseModel):
    """Response from POST /v1/products/eng-analytics/connections."""

    connection_id: UUID
    product: Literal["eng_analytics"] = "eng_analytics"
    provider: str
    message: str | None = None
