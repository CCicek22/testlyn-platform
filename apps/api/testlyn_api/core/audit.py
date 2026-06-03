from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

import structlog
from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from testlyn_api.core.auth import CurrentUser, get_current_user
from testlyn_api.core.db import get_session
from testlyn_api.models.audit_log import AuditLog
from testlyn_api.services import audit_siem

log = structlog.get_logger(__name__)


@dataclass
class AuditContext:
    """Captures request-level metadata used for every audit row."""

    ip: str | None
    user_agent: str | None
    actor_user_id: uuid.UUID | None
    org_id: uuid.UUID | None = None
    _session: AsyncSession | None = field(default=None, repr=False)

    async def write(
        self,
        *,
        action: str,
        resource_type: str,
        resource_id: uuid.UUID | None = None,
        before: dict[str, Any] | None = None,
        after: dict[str, Any] | None = None,
        org_id: uuid.UUID | None = None,
    ) -> None:
        """Persist a single audit row. org_id param overrides self.org_id."""
        effective_org_id = org_id or self.org_id
        if effective_org_id is None or self._session is None:
            log.warning(
                "audit.write.skipped",
                reason="missing org_id or session",
                action=action,
            )
            return

        entry = AuditLog(
            org_id=effective_org_id,
            actor_user_id=self.actor_user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            before=before,
            after=after,
            ip=self.ip,
            user_agent=self.user_agent,
        )
        self._session.add(entry)
        log.debug(
            "audit.written",
            action=action,
            resource_type=resource_type,
            resource_id=str(resource_id) if resource_id else None,
            org_id=str(effective_org_id),
        )
        await self._export_to_sinks(entry, effective_org_id)

    async def _export_to_sinks(
        self, entry: AuditLog, org_id: uuid.UUID
    ) -> None:
        """Fan an audit row out to active SIEM sinks, off the request hot-path.

        A cheap query returns early when the org has no sinks. Delivery itself
        runs in detached fire-and-forget tasks (see ``audit_siem``) so a slow or
        failing SIEM endpoint never blocks or fails the audit write, and one
        sink's failure can't break another or the caller.
        """
        if self._session is None:
            return
        try:
            sinks = await audit_siem.active_sinks_for_org(org_id, self._session)
            if not sinks:
                return
            # Flush so server_default columns (id, created_at) are populated,
            # then snapshot the row to a plain dict WHILE still on-session. The
            # detached dispatch tasks must never touch the ORM object — by the
            # time they run the request's AsyncSession may be committed/closed,
            # and a lazy refresh there fails silently, dropping every event.
            await self._session.flush()
            event = audit_siem._event_dict(entry)
            audit_siem.dispatch_event_background(sinks, event)
        except Exception as exc:  # noqa: BLE001 — SIEM must never break audit write
            log.error("audit.siem_dispatch_failed", org_id=str(org_id), error=str(exc))


class AuditService:
    """
    Thin wrapper around AuditContext that handles SQLAlchemy session state.

    Preferred usage:  inject via AuditDep in route signatures.
    """

    def __init__(self, ctx: AuditContext) -> None:
        self._ctx = ctx

    async def write(
        self,
        *,
        action: str,
        resource_type: str,
        resource_id: uuid.UUID | None = None,
        before: dict[str, Any] | None = None,
        after: dict[str, Any] | None = None,
        org_id: uuid.UUID | None = None,
    ) -> None:
        await self._ctx.write(
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            before=before,
            after=after,
            org_id=org_id,
        )

    def set_org(self, org_id: uuid.UUID) -> None:
        """Bind an org_id discovered during request handling."""
        self._ctx.org_id = org_id


def _client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return None


async def get_audit_service(
    request: Request,
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> AuditService:
    """
    FastAPI dependency — resolves actor identity from request (best-effort;
    does NOT raise if unauthenticated; audit rows for anonymous callers will
    have actor_user_id=None).
    """
    actor_id: uuid.UUID | None = None
    try:
        user: CurrentUser = await get_current_user(request=request, session=session)
        actor_id = user.id
    except Exception:
        pass  # unauthenticated — actor stays None

    ctx = AuditContext(
        ip=_client_ip(request),
        user_agent=request.headers.get("User-Agent"),
        actor_user_id=actor_id,
        _session=session,
    )
    return AuditService(ctx)
