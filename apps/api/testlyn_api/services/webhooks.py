"""Webhook dispatch + delivery service.

TODO wiring points — other streams should call dispatcher.fire() after their
state transitions:
  - routers/test_runs.py   → fire("test.completed") / fire("test.failed")
                             when a run transitions to completed/failed state
  - routers/orgs.py        → fire("member.invited") on OrgMember creation
  - services/stripe_webhook.py → fire("subscription.updated") on subscription
                             lifecycle events (created, updated, deleted)
  - products/load/ threshold checker → fire("threshold.breached")
  - products/a11y/ report publish → fire("scan.findings_published")

TODO Cloud Tasks: the current retry scheduler uses asyncio.create_task (in-
process). For production replace _schedule_retry() with a Cloud Tasks enqueue
call so retries survive process restarts. The deliver() method is already
idempotent (checks delivery.status before POSTing) and can safely be the
Cloud Tasks handler target at POST /v1/internal/webhooks/deliver/{delivery_id}.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import uuid
from collections.abc import Coroutine
from datetime import UTC, datetime, timedelta
from typing import Any, Final

import httpx
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from testlyn_api.core.url_safety import UnsafeURL, assert_safe_url, assert_safe_url_async
from testlyn_api.models.webhook import WebhookDelivery, WebhookEndpoint

log = structlog.get_logger(__name__)

# The SSRF guard now lives in core/url_safety.py so the scanner products reuse
# the identical policy. These module-level aliases preserve the historical
# names used by this module and its tests — behavior is unchanged.
UnsafeWebhookURL = UnsafeURL
_assert_safe_url = assert_safe_url

# Canonical event taxonomy for Phase 3.
EVENTS: Final[set[str]] = {
    "test.completed",
    "test.failed",
    "threshold.breached",
    "scan.findings_published",
    "subscription.updated",
    "member.invited",
}

# Exponential backoff delays (seconds) before giving up.
_RETRY_DELAYS: Final[list[int]] = [30, 120, 600, 1800, 3600]

# Strong refs so fire-and-forget delivery/retry tasks aren't GC'd mid-flight
# (same pattern as audit_siem._BACKGROUND_TASKS).
_DELIVERY_TASKS: Final[set[asyncio.Task[None]]] = set()


def _spawn_tracked(coro: Coroutine[Any, Any, None]) -> None:
    """Schedule a fire-and-forget coroutine with a strong task reference.

    A bare ``asyncio.create_task`` result can be garbage-collected mid-flight,
    silently dropping the delivery; keep a module-level ref until done.
    """
    task = asyncio.create_task(coro)
    _DELIVERY_TASKS.add(task)
    task.add_done_callback(_DELIVERY_TASKS.discard)


def _schedule_retry(delivery_id: uuid.UUID, delay: float) -> None:
    """Schedule an in-process re-delivery attempt after ``delay`` seconds.

    LIMITATION: in-process only — a pending retry is lost if the process
    restarts or scales to zero. Production hardening is a Cloud Tasks enqueue
    (see module TODO); ``deliver()`` is idempotent so the swap is safe. Max
    attempts are honored by ``deliver()`` itself, which abandons past
    ``len(_RETRY_DELAYS)`` attempts and stops re-scheduling.
    """
    _spawn_tracked(_retry_after(delivery_id, delay))


async def _retry_after(delivery_id: uuid.UUID, delay: float) -> None:
    await asyncio.sleep(delay)
    from testlyn_api.core.db import _session_factory  # local import avoids circular

    async with _session_factory() as session:
        await WebhookDispatcher(session).deliver(delivery_id)


def _sign(secret: str, body: bytes) -> str:
    """Return 'sha256=<hex>' HMAC-SHA256 signature."""
    mac = hmac.new(secret.encode(), body, hashlib.sha256)
    return f"sha256={mac.hexdigest()}"


class WebhookDispatcher:
    """Fan-out events to all active matching endpoints for an org."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def fire(
        self,
        org_id: uuid.UUID,
        event_type: str,
        payload: dict,
    ) -> list[uuid.UUID]:
        """
        Create WebhookDelivery rows for every active endpoint subscribed to
        event_type, then schedule async delivery for each.

        Returns the list of delivery IDs created.
        """
        if event_type not in EVENTS:
            log.warning("webhooks.fire.unknown_event", event_type=event_type)
            return []

        result = await self._session.execute(
            select(WebhookEndpoint).where(
                WebhookEndpoint.org_id == org_id,
                WebhookEndpoint.active.is_(True),
            )
        )
        endpoints = result.scalars().all()

        # Build delivery rows first; capture the target endpoint coords so we can
        # schedule background delivery AFTER the commit (the standalone task opens
        # its own session and must be able to read the committed row).
        pending: list[tuple[uuid.UUID, str, str]] = []  # (delivery_id, url, secret)
        for ep in endpoints:
            if event_type not in (ep.events or []):
                continue
            delivery = WebhookDelivery(
                endpoint_id=ep.id,
                event_type=event_type,
                payload=payload,
                status="pending",
            )
            self._session.add(delivery)
            await self._session.flush()
            pending.append((delivery.id, ep.url, ep.secret))

        delivery_ids = [d_id for d_id, _, _ in pending]
        if not pending:
            return delivery_ids

        # Commit BEFORE scheduling: _deliver_standalone uses a separate session
        # and would not see uncommitted rows (would silently drop the delivery).
        await self._session.commit()
        for delivery_id, url, secret in pending:
            _spawn_tracked(
                _deliver_standalone(delivery_id, url, secret, payload, event_type)
            )
        log.info(
            "webhooks.fired",
            event_type=event_type,
            org_id=str(org_id),
            count=len(delivery_ids),
        )
        return delivery_ids

    async def deliver(self, delivery_id: uuid.UUID) -> bool:
        """
        Attempt delivery of a single WebhookDelivery row.
        Updates status / attempts / last_error / next_retry_at in place.
        Returns True if delivered successfully.
        """
        delivery = await self._session.get(WebhookDelivery, delivery_id)
        if delivery is None:
            log.error("webhooks.deliver.not_found", delivery_id=str(delivery_id))
            return False

        if delivery.status in ("completed", "abandoned"):
            return delivery.status == "completed"

        endpoint = await self._session.get(WebhookEndpoint, delivery.endpoint_id)
        if endpoint is None:
            delivery.status = "abandoned"
            delivery.last_error = "endpoint deleted"
            await self._session.commit()
            return False

        body = _build_body(delivery.payload, delivery.event_type)
        signature = _sign(endpoint.secret, body)

        delivery.status = "delivering"
        delivery.attempts += 1
        await self._session.commit()

        success = await _post(
            url=endpoint.url,
            body=body,
            signature=signature,
            delivery_id=str(delivery.id),
        )

        if success:
            delivery.status = "completed"
            delivery.completed_at = datetime.now(UTC)
            delivery.last_error = None
            delivery.next_retry_at = None
            log.info("webhooks.delivered", delivery_id=str(delivery.id))
        else:
            attempt = delivery.attempts  # already incremented above
            if attempt <= len(_RETRY_DELAYS):
                delay = _RETRY_DELAYS[attempt - 1]
                delivery.status = "failed"
                delivery.next_retry_at = datetime.now(UTC) + timedelta(seconds=delay)
                _schedule_retry(delivery.id, delay)
                log.warning(
                    "webhooks.deliver.retry_scheduled",
                    delivery_id=str(delivery.id),
                    attempt=attempt,
                    retry_in_s=delay,
                )
            else:
                delivery.status = "abandoned"
                delivery.next_retry_at = None
                log.error(
                    "webhooks.deliver.abandoned",
                    delivery_id=str(delivery.id),
                    attempts=attempt,
                )

        await self._session.commit()
        return success


def _build_body(payload: dict, event_type: str) -> bytes:
    import json

    return json.dumps({"event": event_type, "data": payload}, separators=(",", ":")).encode()


async def _post(url: str, body: bytes, signature: str, delivery_id: str) -> bool:
    # SSRF guard: validate the (user-supplied) target URL before any network
    # I/O. A rejection is treated as a failed delivery (return False), matching
    # this function's bool contract — we never raise into the caller. The async
    # variant runs the blocking DNS resolution off the event loop.
    try:
        await assert_safe_url_async(url)
    except UnsafeWebhookURL as exc:
        log.warning(
            "webhooks.ssrf_blocked", url=url, reason=str(exc), delivery_id=delivery_id
        )
        return False

    headers = {
        "Content-Type": "application/json",
        "X-Testlyn-Signature": signature,
        "X-Testlyn-Delivery-Id": delivery_id,
    }
    try:
        # follow_redirects=False is explicit (also the httpx default): a 3xx to
        # an internal URL would bypass _assert_safe_url, so never auto-follow.
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=False) as client:
            resp = await client.post(url, content=body, headers=headers)
            return resp.is_success
    except Exception as exc:
        log.warning("webhooks.post_error", url=url, error=str(exc))
        return False


async def _deliver_standalone(
    delivery_id: uuid.UUID,
    url: str,
    secret: str,
    payload: dict,
    event_type: str,
) -> None:
    """
    Fire-and-forget delivery used by fire().
    Uses its own short-lived session so it doesn't block the request session.
    Retries are handled by the retry scheduler (or Cloud Tasks in production).
    """
    from testlyn_api.core.db import _session_factory  # local import avoids circular

    body = _build_body(payload, event_type)
    signature = _sign(secret, body)
    success = await _post(url=url, body=body, signature=signature, delivery_id=str(delivery_id))

    async with _session_factory() as session:
        delivery = await session.get(WebhookDelivery, delivery_id)
        if delivery is None:
            return
        delivery.attempts += 1
        if success:
            delivery.status = "completed"
            delivery.completed_at = datetime.now(UTC)
        else:
            attempt = delivery.attempts
            if attempt <= len(_RETRY_DELAYS):
                delay = _RETRY_DELAYS[attempt - 1]
                delivery.status = "failed"
                delivery.next_retry_at = datetime.now(UTC) + timedelta(seconds=delay)
                _schedule_retry(delivery_id, delay)
            else:
                delivery.status = "abandoned"
        await session.commit()
