from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/v1/public", tags=["public"])

StatusLevel = Literal["operational", "degraded", "outage", "maintenance"]
_RANK: dict[StatusLevel, int] = {
    "operational": 0,
    "maintenance": 1,
    "degraded": 2,
    "outage": 3,
}

# Static component catalogue. We report "operational" for each: the API is
# responding (so "api" is true by construction) and we do not have a validated
# live health signal for the others — claiming a status we can't verify, or
# inventing uptime percentages, would commit us to behaviour we haven't proven.
_COMPONENTS: list[tuple[str, str]] = [
    ("api", "API"),
    ("web", "Web dashboard"),
    ("engine", "Load engine (k6 runner)"),
    ("bq", "BigQuery streaming"),
    ("auth", "Authentication (Identity Platform)"),
    ("storage", "Cloud Storage (reports / scripts)"),
]


class StatusComponent(BaseModel):
    id: str
    name: str
    status: StatusLevel
    uptime_90d: float | None = None


class StatusIncident(BaseModel):
    id: str
    title: str
    body: str
    severity: Literal["minor", "major", "critical"]
    created_at: str
    resolved_at: str | None = None


class StatusResponse(BaseModel):
    overall: StatusLevel
    components: list[StatusComponent]
    incidents: list[StatusIncident]
    fetched_at: str


@router.get("/status", response_model=StatusResponse, response_model_exclude_none=True)
async def public_status() -> StatusResponse:
    """Public system-status snapshot for the marketing /status page (no auth)."""
    components = [
        StatusComponent(id=cid, name=name, status="operational") for cid, name in _COMPONENTS
    ]
    overall = max((c.status for c in components), key=lambda s: _RANK[s])
    return StatusResponse(
        overall=overall,
        components=components,
        incidents=[],
        fetched_at=datetime.now(tz=UTC).isoformat(),
    )
