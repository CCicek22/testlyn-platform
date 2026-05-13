"""Audit SIEM export service.

Sends audit_log rows to external destinations (Splunk HEC, Datadog Logs,
generic HTTPS) with simple retry logic (3 attempts, exponential back-off).

No tenacity dependency — handled with plain asyncio + httpx.
"""

from __future__ import annotations

import asyncio
import json
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


def _fmt_splunk(event: AuditLog) -> dict[str, Any]:
    return {
        "time": event.created_at.timestamp() if event.created_at else None,
        "sourcetype": "testlyn:audit",
        "event": _event_dict(event),
    }


def _fmt_datadog(event: AuditLog) -> dict[str, Any]:
    return {
        "ddsource": "testlyn",
        "ddtags": f"org_id:{event.org_id},action:{event.action}",
        "service": "testlyn-api",
        "message": json.dumps(_event_dict(event)),
        "date": event.created_at.isoformat() if event.created_at else None,
    }


def _fmt_generic(event: AuditLog) -> dict[str, Any]:
    return _event_dict(event)


def _event_dict(event: AuditLog) -> dict[str, Any]:
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


async def export_event(sink: AuditSiemSink, event: AuditLog) -> None:
    """Format and POST a single audit event to the given sink."""
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
    log.info("audit_siem.exported", sink_id=str(sink.id), event_id=str(event.id))


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
    for event in events:
        await export_event(sink, event)
    log.info("audit_siem.backfill_done", sink_id=str(sink.id), count=len(events))
    return len(events)
