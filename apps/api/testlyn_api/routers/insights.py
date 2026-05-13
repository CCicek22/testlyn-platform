from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import structlog
from fastapi import APIRouter, Query
from sqlalchemy import desc, select

from testlyn_api.deps import CurrentUserDep, SessionDep
from testlyn_api.models.insights_snapshot import InsightsSnapshot

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/v1/orgs", tags=["insights"])


class InsightsSnapshotOut(dict):
    """Thin dict-based response — full schema in shared-types."""


def _snapshot_to_dict(snap: InsightsSnapshot) -> dict[str, Any]:
    return {
        "id": str(snap.id),
        "org_id": str(snap.org_id),
        "snapshot_time": snap.snapshot_time.isoformat(),
        "p95_latency_ms": float(snap.p95_latency_ms) if snap.p95_latency_ms is not None else None,
        "a11y_score": float(snap.a11y_score) if snap.a11y_score is not None else None,
        "open_critical_findings": snap.open_critical_findings,
        "contract_drift_count": snap.contract_drift_count,
        "synthetic_data_freshness_h": (
            float(snap.synthetic_data_freshness_h)
            if snap.synthetic_data_freshness_h is not None
            else None
        ),
        "payload": snap.payload,
    }


@router.get("/{org_id}/insights/snapshots")
async def list_snapshots(
    org_id: uuid.UUID,
    current_user: CurrentUserDep,
    session: SessionDep,
    limit: int = Query(default=24, ge=1, le=200),
) -> list[dict[str, Any]]:
    """
    Return the most recent N insights snapshots for an org.

    Snapshots are written by the Cloud Scheduler cron that calls
    POST /v1/internal/orgs/:id/insights/refresh.
    """
    result = await session.execute(
        select(InsightsSnapshot)
        .where(InsightsSnapshot.org_id == org_id)
        .order_by(desc(InsightsSnapshot.snapshot_time))
        .limit(limit)
    )
    snapshots = result.scalars().all()
    log.info(
        "insights.snapshots.listed",
        org_id=str(org_id),
        count=len(snapshots),
        user_id=str(current_user.id),
    )
    return [_snapshot_to_dict(s) for s in snapshots]


@router.get("/{org_id}/insights/latest")
async def get_latest_snapshot(
    org_id: uuid.UUID,
    current_user: CurrentUserDep,
    session: SessionDep,
) -> dict[str, Any]:
    """
    Return the single most recent insights snapshot for an org.

    Returns a stub with null KPIs when no snapshot exists yet.
    """
    result = await session.execute(
        select(InsightsSnapshot)
        .where(InsightsSnapshot.org_id == org_id)
        .order_by(desc(InsightsSnapshot.snapshot_time))
        .limit(1)
    )
    snap = result.scalar_one_or_none()

    if snap is None:
        log.info("insights.latest.no_snapshot", org_id=str(org_id))
        return {
            "id": None,
            "org_id": str(org_id),
            "snapshot_time": datetime.now(tz=UTC).isoformat(),
            "p95_latency_ms": None,
            "a11y_score": None,
            "open_critical_findings": None,
            "contract_drift_count": None,
            "synthetic_data_freshness_h": None,
            "payload": None,
        }

    log.info("insights.latest.found", org_id=str(org_id), snap_id=str(snap.id))
    return _snapshot_to_dict(snap)
