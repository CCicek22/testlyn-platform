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
from datetime import UTC, datetime, timedelta
from typing import Final

import httpx
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from testlyn_api.models.webhook import WebhookDelivery, WebhookEndpoint

log = structlog.get_logger(__name__)

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

        delivery_ids: list[uuid.UUID] = []
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
            delivery_ids.append(delivery.id)
            # Kick off delivery in the background; session is already flushed.
            asyncio.create_task(  # noqa: RUF006
                _deliver_standalone(delivery.id, ep.url, ep.secret, payload, event_type)
            )

        if delivery_ids:
            await self._session.commit()
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
    headers = {
        "Content-Type": "application/json",
        "X-Testlyn-Signature": signature,
        "X-Testlyn-Delivery-Id": delivery_id,
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
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
            else:
                delivery.status = "abandoned"
        await session.commit()
