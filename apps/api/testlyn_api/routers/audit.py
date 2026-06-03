"""Audit log + SIEM sinks router.

Endpoints
---------
GET  /v1/orgs/{org_id}/audit-log             — paginated list (admin+)
GET  /v1/orgs/{org_id}/audit-log.csv         — streaming CSV export (admin+)
GET  /v1/orgs/{org_id}/audit-log.json        — streaming JSON export (admin+)
GET  /v1/orgs/{org_id}/audit-sinks           — list sinks (owner)
POST /v1/orgs/{org_id}/audit-sinks           — create sink (owner)
DELETE /v1/orgs/{org_id}/audit-sinks/{sink_id} — delete sink (owner)
"""

from __future__ import annotations

import csv
import io
import json
import uuid
from datetime import datetime
from typing import Any

import structlog
from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from testlyn_api.core.permissions import perm_dep
from testlyn_api.deps import CurrentUserDep, SessionDep
from testlyn_api.models.audit_log import AuditLog
from testlyn_api.models.audit_siem_sink import SINK_KINDS, AuditSiemSink

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/v1/orgs", tags=["audit"])

_DEFAULT_LIMIT = 50
_MAX_LIMIT = 500


# ── Schemas ───────────────────────────────────────────────────────────────────


class AuditLogOut(BaseModel):
    id: uuid.UUID
    org_id: uuid.UUID
    actor_user_id: uuid.UUID | None
    action: str
    resource_type: str
    resource_id: uuid.UUID | None
    before: dict[str, Any] | None
    after: dict[str, Any] | None
    ip: str | None
    user_agent: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class AuditLogPage(BaseModel):
    items: list[AuditLogOut]
    cursor: uuid.UUID | None


class SinkCreate(BaseModel):
    kind: str
    config: dict[str, Any]
    active: bool = True


class SinkOut(BaseModel):
    id: uuid.UUID
    org_id: uuid.UUID
    kind: str
    config: dict[str, Any]
    active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ── Query helpers ─────────────────────────────────────────────────────────────


def _build_filter(
    org_id: uuid.UUID,
    *,
    action: str | None,
    actor_id: uuid.UUID | None,
    from_dt: datetime | None,
    to_dt: datetime | None,
    cursor_created_at: datetime | None,
    cursor: uuid.UUID | None,
) -> list[Any]:
    clauses: list[Any] = [AuditLog.org_id == org_id]
    if action:
        clauses.append(AuditLog.action == action)
    if actor_id:
        clauses.append(AuditLog.actor_user_id == actor_id)
    if from_dt:
        clauses.append(AuditLog.created_at >= from_dt)
    if to_dt:
        clauses.append(AuditLog.created_at <= to_dt)
    if cursor is not None and cursor_created_at is not None:
        # Keyset pagination on the SAME tuple we order by — (created_at DESC,
        # id DESC). Filtering on id alone is wrong here because id is a random
        # uuid4 and does not track created_at, which would skip/duplicate rows
        # across pages.
        clauses.append(
            or_(
                AuditLog.created_at < cursor_created_at,
                and_(
                    AuditLog.created_at == cursor_created_at,
                    AuditLog.id < cursor,
                ),
            )
        )
    return clauses


async def _resolve_cursor(
    session: AsyncSession, org_id: uuid.UUID, cursor: uuid.UUID
) -> datetime:
    """Resolve a cursor id to its created_at, scoped to org_id.

    Raises 400 if the cursor does not resolve within this org (stale, deleted,
    or cross-org). Falling through to a None cursor would silently drop the
    keyset clause and restart pagination from page 1 — producing duplicate
    pages and client loops — so an unresolved cursor is a hard error.
    """
    cursor_created_at = await session.scalar(
        select(AuditLog.created_at).where(
            AuditLog.id == cursor, AuditLog.org_id == org_id
        )
    )
    if cursor_created_at is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired cursor",
        )
    return cursor_created_at


async def _fetch_page(
    session: AsyncSession,
    org_id: uuid.UUID,
    *,
    action: str | None,
    actor_id: uuid.UUID | None,
    from_dt: datetime | None,
    to_dt: datetime | None,
    cursor: uuid.UUID | None,
    limit: int,
) -> list[AuditLog]:
    # Resolve the cursor row's created_at so the keyset comparison can use the
    # full (created_at, id) ordering key. Scoped to org_id; raises 400 if the
    # cursor is unresolvable.
    cursor_created_at: datetime | None = None
    if cursor is not None:
        cursor_created_at = await _resolve_cursor(session, org_id, cursor)

    clauses = _build_filter(
        org_id,
        action=action,
        actor_id=actor_id,
        from_dt=from_dt,
        to_dt=to_dt,
        cursor_created_at=cursor_created_at,
        cursor=cursor,
    )
    q = (
        select(AuditLog)
        .where(and_(*clauses))
        .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .limit(limit + 1)
    )
    result = await session.execute(q)
    return list(result.scalars().all())


async def _iter_all_rows(
    session: AsyncSession,
    org_id: uuid.UUID,
    *,
    action: str | None,
    actor_id: uuid.UUID | None,
    from_dt: datetime | None,
    to_dt: datetime | None,
) -> list[AuditLog]:
    """Page through the full keyset for an export — ALL matching rows, not a
    silent single-page cap. Walks (created_at DESC, id DESC) in _MAX_LIMIT
    batches until exhausted.
    """
    out: list[AuditLog] = []
    cursor: uuid.UUID | None = None
    while True:
        rows = await _fetch_page(
            session,
            org_id,
            action=action,
            actor_id=actor_id,
            from_dt=from_dt,
            to_dt=to_dt,
            cursor=cursor,
            limit=_MAX_LIMIT,
        )
        has_more = len(rows) > _MAX_LIMIT
        if has_more:
            rows = rows[:_MAX_LIMIT]
        out.extend(rows)
        if not has_more:
            break
        cursor = rows[-1].id
    return out


# ── Audit log list ─────────────────────────────────────────────────────────────


@router.get(
    "/{org_id}/audit-log",
    response_model=AuditLogPage,
    dependencies=[perm_dep("read", "audit_log")],
)
async def list_audit_log(
    org_id: uuid.UUID,
    current_user: CurrentUserDep,
    session: SessionDep,
    action: str | None = Query(default=None),
    actor_id: uuid.UUID | None = Query(default=None),
    from_dt: datetime | None = Query(default=None, alias="from_dt"),
    to_dt: datetime | None = Query(default=None, alias="to_dt"),
    cursor: uuid.UUID | None = Query(default=None),
    limit: int = Query(default=_DEFAULT_LIMIT, ge=1, le=_MAX_LIMIT),
) -> AuditLogPage:
    rows = await _fetch_page(
        session,
        org_id,
        action=action,
        actor_id=actor_id,
        from_dt=from_dt,
        to_dt=to_dt,
        cursor=cursor,
        limit=limit,
    )
    next_cursor: uuid.UUID | None = None
    if len(rows) > limit:
        rows = rows[:limit]
        next_cursor = rows[-1].id

    return AuditLogPage(
        items=[AuditLogOut.model_validate(r) for r in rows],
        cursor=next_cursor,
    )


# ── CSV export ────────────────────────────────────────────────────────────────


@router.get(
    "/{org_id}/audit-log.csv",
    dependencies=[perm_dep("read", "audit_log")],
)
async def export_audit_csv(
    org_id: uuid.UUID,
    current_user: CurrentUserDep,
    session: SessionDep,
    action: str | None = Query(default=None),
    actor_id: uuid.UUID | None = Query(default=None),
    from_dt: datetime | None = Query(default=None, alias="from_dt"),
    to_dt: datetime | None = Query(default=None, alias="to_dt"),
) -> StreamingResponse:
    rows = await _iter_all_rows(
        session,
        org_id,
        action=action,
        actor_id=actor_id,
        from_dt=from_dt,
        to_dt=to_dt,
    )

    def _generate() -> Any:
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(
            ["id", "actor_user_id", "action", "resource_type", "resource_id", "ip", "created_at"]
        )
        for r in rows:
            writer.writerow([
                str(r.id),
                str(r.actor_user_id) if r.actor_user_id else "",
                r.action,
                r.resource_type,
                str(r.resource_id) if r.resource_id else "",
                r.ip or "",
                r.created_at.isoformat() if r.created_at else "",
            ])
        yield buf.getvalue()

    return StreamingResponse(
        _generate(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="audit-{org_id}.csv"'},
    )


# ── JSON export ───────────────────────────────────────────────────────────────


@router.get(
    "/{org_id}/audit-log.json",
    dependencies=[perm_dep("read", "audit_log")],
)
async def export_audit_json(
    org_id: uuid.UUID,
    current_user: CurrentUserDep,
    session: SessionDep,
    action: str | None = Query(default=None),
    actor_id: uuid.UUID | None = Query(default=None),
    from_dt: datetime | None = Query(default=None, alias="from_dt"),
    to_dt: datetime | None = Query(default=None, alias="to_dt"),
) -> StreamingResponse:
    rows = await _iter_all_rows(
        session,
        org_id,
        action=action,
        actor_id=actor_id,
        from_dt=from_dt,
        to_dt=to_dt,
    )
    data = [AuditLogOut.model_validate(r).model_dump(mode="json") for r in rows]

    def _generate() -> Any:
        yield json.dumps(data, default=str)

    return StreamingResponse(
        _generate(),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="audit-{org_id}.json"'},
    )


# ── SIEM sinks ────────────────────────────────────────────────────────────────


@router.get(
    "/{org_id}/audit-sinks",
    response_model=list[SinkOut],
    dependencies=[perm_dep("write", "audit_log")],
)
async def list_sinks(
    org_id: uuid.UUID,
    current_user: CurrentUserDep,
    session: SessionDep,
) -> list[SinkOut]:
    result = await session.execute(
        select(AuditSiemSink).where(AuditSiemSink.org_id == org_id).order_by(AuditSiemSink.created_at.asc())
    )
    return [SinkOut.model_validate(s) for s in result.scalars().all()]


@router.post(
    "/{org_id}/audit-sinks",
    response_model=SinkOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[perm_dep("write", "audit_log")],
)
async def create_sink(
    org_id: uuid.UUID,
    body: SinkCreate,
    current_user: CurrentUserDep,
    session: SessionDep,
) -> SinkOut:
    if body.kind not in SINK_KINDS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"kind must be one of {SINK_KINDS}",
        )
    sink = AuditSiemSink(
        org_id=org_id,
        kind=body.kind,
        config=body.config,
        active=body.active,
    )
    session.add(sink)
    await session.commit()
    await session.refresh(sink)
    log.info("audit_sink.created", sink_id=str(sink.id), org_id=str(org_id))
    return SinkOut.model_validate(sink)


@router.delete(
    "/{org_id}/audit-sinks/{sink_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[perm_dep("delete", "audit_log")],
)
async def delete_sink(
    org_id: uuid.UUID,
    sink_id: uuid.UUID,
    current_user: CurrentUserDep,
    session: SessionDep,
) -> None:
    result = await session.execute(
        select(AuditSiemSink).where(
            AuditSiemSink.id == sink_id, AuditSiemSink.org_id == org_id
        )
    )
    sink = result.scalar_one_or_none()
    if sink is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sink not found")
    await session.delete(sink)
    await session.commit()
    log.info("audit_sink.deleted", sink_id=str(sink_id), org_id=str(org_id))
