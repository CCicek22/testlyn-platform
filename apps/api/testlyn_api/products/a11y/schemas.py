from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, HttpUrl


class A11yAuditConfig(BaseModel):
    """Config for a one-shot or scheduled a11y audit."""

    urls: list[HttpUrl] = Field(..., min_length=1, max_length=50)
    max_depth: int = Field(default=1, ge=1, le=5)
    wcag_tags: list[str] = Field(
        default=["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"],
        description="axe-core tag filters",
    )
    schedule_cron: str | None = Field(
        default=None,
        description="Optional Cloud Scheduler cron expression for recurring audits.",
    )


class A11yViolation(BaseModel):
    """Single axe-core violation row."""

    rule_id: str
    impact: Literal["critical", "serious", "moderate", "minor"]
    html_snippet: str
    dom_path: str
    help_url: str
    target_url: str
    remediation: str | None = None


class A11ySummary(BaseModel):
    """Violation counts by impact level."""

    total: int
    critical: int
    serious: int
    moderate: int
    minor: int


class A11yReport(BaseModel):
    """Full a11y audit report returned by GET /v1/runs/:id/violations."""

    run_id: UUID
    product: Literal["a11y"] = "a11y"
    summary: A11ySummary
    violations: list[A11yViolation]
    pdf_uri: str | None = Field(
        default=None,
        description="GCS URI of the branded WCAG 2.2 PDF report, once generated.",
    )
    created_at: datetime


class A11yAuditRequest(BaseModel):
    """Request body for POST /v1/products/a11y/audit (one-shot)."""

    test_run_id: UUID
    config: A11yAuditConfig


class A11yRecipeCreate(BaseModel):
    """Request body for POST /v1/products/a11y/recipes."""

    target_id: UUID
    urls: list[HttpUrl] = Field(..., min_length=1)
    max_depth: int = Field(default=1, ge=1, le=5)
    schedule_cron: str | None = None


class A11yRecipeOut(BaseModel):
    """Recipe response."""

    id: UUID
    target_id: UUID
    urls: list[str]
    max_depth: int
    schedule_cron: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
