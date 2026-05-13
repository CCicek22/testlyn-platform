from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class FunctionalTestConfig(BaseModel):
    """Configuration for a Playwright functional test run."""

    target_url: str
    script_ts: str
    viewport: dict[str, int] = {"width": 1280, "height": 720}
    timeouts: dict[str, int] = {"navigation": 30_000, "action": 10_000}


class FunctionalGenerateRequest(BaseModel):
    """Request body for AI test script generation."""

    prompt: str | None = None
    prd_file: str | None = None  # GCS URI of a PRD/spec file
    target_url: str | None = None


class FunctionalGenerateResponse(BaseModel):
    """Response from AI test script generation."""

    product: Literal["functional"] = "functional"
    script_ts: str
    locator_strategies: list[str]
