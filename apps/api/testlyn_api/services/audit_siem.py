"""Audit SIEM export service.

Sends audit_log rows to external destinations (Splunk HEC, Datadog Logs,
generic HTTPS) with simple retry logic (3 attempts, exponential back-off).

No tenacity dependency — handled with plain asyncio + httpx.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import UTC, datetime
from typing import Any

import httpx
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from testlyn_api.models.audit_log import AuditLog
from testlyn_api.models.audit_siem_sink import AuditSiemSink

log = structlog.get_logger(__name__)

_HTTP_TIMEOUT = 5.0  # seconds
_MAX_RETRIES = 3


# ── Formatters ────────────────────────────────────────────────────────────────


def _fmt_splunk(event: dict[str, Any]) -> dict[str, Any]:
    created_at = event.get("created_at")
    return {
        "time": datetime.fromisoformat(created_at).timestamp() if created_at else None,
        "sourcetype": "testlyn:audit",
        "event": event,
    }


def _fmt_datadog(event: dict[str, Any]) -> dict[str, Any]:
    return {
        "ddsource": "testlyn",
        "ddtags": f"org_id:{event['org_id']},action:{event['action']}",
        "service": "testlyn-api",
        "message": json.dumps(event),
        "date": event.get("created_at"),
    }


def _fmt_generic(event: dict[str, Any]) -> dict[str, Any]:
    return event


def _event_dict(event: AuditLog) -> dict[str, Any]:
    """Build a plain serialisable event dict from an ORM row.

    MUST be called while ``event`` is still attached to a live, flushed
    AsyncSession — ``id`` and ``created_at`` (a server_default) are only
    populated after flush, and any attribute access on a detached/closed
    session would trigger a lazy refresh and fail under asyncio.
    """
    return {
        "id": str(event.id),
        "org_id": str(event.org_id),
        "actor_user_id": str(event.actor_user_id) if event.actor_user_id else None,
        "action": event.action,
        "resource_type": event.resource_type,
        "resource_id": str(event.resource_id) if event.resource_id else None,
        "before": event.before,
        "after": event.after,
        "ip": event.ip,
        "user_agent": event.user_agent,
        "created_at": event.created_at.isoformat() if event.created_at else None,
    }


# ── HTTP dispatch ─────────────────────────────────────────────────────────────


async def _post_with_retry(
    url: str,
    headers: dict[str, str],
    payload: dict[str, Any],
) -> None:
    """POST payload to url, retrying up to _MAX_RETRIES times."""
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
                resp = await client.post(url, json=payload, headers=headers)
                resp.raise_for_status()
                return
        except (httpx.HTTPError, Exception) as exc:
            if attempt == _MAX_RETRIES:
                log.error(
                    "audit_siem.export_failed",
                    url=url,
                    attempt=attempt,
                    error=str(exc),
                )
                raise
            backoff = 2 ** (attempt - 1)
            log.warning(
                "audit_siem.retry",
                url=url,
                attempt=attempt,
                backoff=backoff,
                error=str(exc),
            )
            await asyncio.sleep(backoff)


# ── Public API ────────────────────────────────────────────────────────────────


async def active_sinks_for_org(
    org_id: uuid.UUID,
    session: AsyncSession,
) -> list[AuditSiemSink]:
    """Return the active SIEM sinks configured for an org (empty if none)."""
    result = await session.execute(
        select(AuditSiemSink).where(
            AuditSiemSink.org_id == org_id,
            AuditSiemSink.active.is_(True),
        )
    )
    return list(result.scalars().all())


async def _dispatch_safely(sink: AuditSiemSink, event: dict[str, Any]) -> None:
    """Run export_event, isolating any failure so it cannot propagate."""
    try:
        await export_event(sink, event)
    except Exception as exc:  # noqa: BLE001 — isolate one sink from the rest
        log.error(
            "audit_siem.dispatch_failed",
            sink_id=str(sink.id),
            event_id=event.get("id"),
            error=str(exc),
        )


def dispatch_event_background(
    sinks: list[AuditSiemSink],
    event: dict[str, Any],
) -> None:
    """Fire-and-forget delivery of one pre-built audit event to each active sink.

    ``event`` is a plain serialisable dict built ON-session via ``_event_dict``
    BEFORE the request's AsyncSession commits/closes — no ORM object is touched
    here, so the detached tasks never trigger a lazy refresh on a closed session
    (which previously failed silently and dropped every event).

    Each delivery runs in its own detached task so a slow or failing SIEM
    endpoint never blocks the request hot-path or breaks a sibling sink.
    Caller is responsible for the cheap "any sinks?" check before invoking.
    """
    for sink in sinks:
        task = asyncio.create_task(_dispatch_safely(sink, event))
        _BACKGROUND_TASKS.add(task)
        task.add_done_callback(_BACKGROUND_TASKS.discard)


# Strong refs so fire-and-forget tasks aren't GC'd mid-flight.
_BACKGROUND_TASKS: set[asyncio.Task[None]] = set()


async def export_event(sink: AuditSiemSink, event: dict[str, Any]) -> None:
    """Format and POST a single pre-built audit event (dict) to the given sink."""
    config: dict[str, Any] = sink.config or {}
    url: str = config.get("url", "")

    if not url:
        log.warning("audit_siem.no_url", sink_id=str(sink.id))
        return

    if sink.kind == "splunk_hec":
        payload = _fmt_splunk(event)
        token = config.get("token", "")
        headers = {"Authorization": f"Splunk {token}", "Content-Type": "application/json"}
    elif sink.kind == "datadog_logs":
        payload = _fmt_datadog(event)
        api_key = config.get("api_key", "")
        headers = {"DD-API-KEY": api_key, "Content-Type": "application/json"}
    else:  # generic_https
        payload = _fmt_generic(event)
        headers = {"Content-Type": "application/json"}
        # Optional Bearer token
        bearer = config.get("token")
        if bearer:
            headers["Authorization"] = f"Bearer {bearer}"

    await _post_with_retry(url, headers, payload)
    log.info("audit_siem.exported", sink_id=str(sink.id), event_id=event.get("id"))


async def backfill_recent(
    sink: AuditSiemSink,
    since_iso: str,
    session: AsyncSession,
) -> int:
    """Replay audit_log rows since since_iso to the given sink.

    Returns the count of events exported.
    """
    since_dt = datetime.fromisoformat(since_iso).replace(tzinfo=UTC)
    result = await session.execute(
        select(AuditLog)
        .where(AuditLog.org_id == sink.org_id, AuditLog.created_at >= since_dt)
        .order_by(AuditLog.created_at.asc())
    )
    events = result.scalars().all()
    # Build serialisable dicts while rows are still attached to the session.
    payloads = [_event_dict(event) for event in events]
    for payload in payloads:
        await export_event(sink, payload)
    log.info("audit_siem.backfill_done", sink_id=str(sink.id), count=len(events))
    return len(events)
