"""Webhook endpoint CRUD + delivery log + replay.

Prefix: /v1/webhooks-admin  (avoids collision with /v1/webhooks stripe router)
Auth:   CurrentUserDep (dev-bypass in tests). Uses W3A requires() if available;
        falls back to org membership check when W3A permissions module is absent.
"""

from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime
from typing import Any

import structlog
from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, HttpUrl
from sqlalchemy import select

from testlyn_api.core.permissions import _enforce_perm
from testlyn_api.core.url_safety import UnsafeURL, assert_safe_url_async
from testlyn_api.deps import CurrentUserDep, SessionDep
from testlyn_api.models.org import OrgMember
from testlyn_api.models.webhook import WebhookDelivery, WebhookEndpoint
from testlyn_api.services.webhooks import EVENTS, _deliver_standalone, _spawn_tracked

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/v1/webhooks-admin", tags=["webhooks-admin"])

# ─── Auth helper ────────────────────────────────────────────────────────────


async def _assert_org_member(org_id: uuid.UUID, user_id: uuid.UUID, session: Any) -> None:
    """Raise 403 if user is not a member of the org."""
    result = await session.execute(
        select(OrgMember).where(
            OrgMember.org_id == org_id,
            OrgMember.user_id == user_id,
        )
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not an org member")


# ─── Schemas ─────────────────────────────────────────────────────────────────


class EndpointCreate(BaseModel):
    url: HttpUrl
    events: list[str]
    active: bool = True


class EndpointPatch(BaseModel):
    url: HttpUrl | None = None
    events: list[str] | None = None
    active: bool | None = None


class EndpointOut(BaseModel):
    id: uuid.UUID
    org_id: uuid.UUID
    url: str
    events: list[str]
    active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DeliveryOut(BaseModel):
    id: uuid.UUID
    endpoint_id: uuid.UUID
    event_type: str
    payload: dict
    status: str
    attempts: int
    last_error: str | None
    next_retry_at: datetime | None
    created_at: datetime
    completed_at: datetime | None

    model_config = {"from_attributes": True}


# ─── Endpoints CRUD ───────────────────────────────────────────────────────────


@router.post(
    "/orgs/{org_id}/endpoints",
    response_model=EndpointOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_endpoint(
    org_id: uuid.UUID,
    body: EndpointCreate,
    current_user: CurrentUserDep,
    session: SessionDep,
) -> EndpointOut:
    await _enforce_perm(
        "write", "webhook", user_id=current_user.id, org_id=org_id, session=session
    )
    await _validate_url(str(body.url))
    _validate_events(body.events)

    ep = WebhookEndpoint(
        org_id=org_id,
        url=str(body.url),
        secret=secrets.token_hex(32),
        events=body.events,
        active=body.active,
    )
    session.add(ep)
    await session.commit()
    await session.refresh(ep)
    log.info("webhook.endpoint.created", endpoint_id=str(ep.id), org_id=str(org_id))
    return EndpointOut.model_validate(ep)


@router.get("/orgs/{org_id}/endpoints", response_model=list[EndpointOut])
async def list_endpoints(
    org_id: uuid.UUID,
    current_user: CurrentUserDep,
    session: SessionDep,
) -> list[EndpointOut]:
    await _assert_org_member(org_id, current_user.id, session)
    result = await session.execute(
        select(WebhookEndpoint)
        .where(WebhookEndpoint.org_id == org_id)
        .order_by(WebhookEndpoint.created_at.desc())
    )
    return [EndpointOut.model_validate(ep) for ep in result.scalars().all()]


@router.get("/endpoints/{endpoint_id}", response_model=EndpointOut)
async def get_endpoint(
    endpoint_id: uuid.UUID,
    current_user: CurrentUserDep,
    session: SessionDep,
) -> EndpointOut:
    ep = await _get_endpoint_or_404(endpoint_id, session)
    await _assert_org_member(ep.org_id, current_user.id, session)
    return EndpointOut.model_validate(ep)


@router.patch("/endpoints/{endpoint_id}", response_model=EndpointOut)
async def patch_endpoint(
    endpoint_id: uuid.UUID,
    body: EndpointPatch,
    current_user: CurrentUserDep,
    session: SessionDep,
) -> EndpointOut:
    ep = await _get_endpoint_or_404(endpoint_id, session)
    await _enforce_perm(
        "write", "webhook", user_id=current_user.id, org_id=ep.org_id, session=session
    )

    if body.url is not None:
        await _validate_url(str(body.url))
        ep.url = str(body.url)
    if body.events is not None:
        _validate_events(body.events)
        ep.events = body.events
    if body.active is not None:
        ep.active = body.active

    ep.updated_at = datetime.now(UTC)
    await session.commit()
    await session.refresh(ep)
    return EndpointOut.model_validate(ep)


@router.delete("/endpoints/{endpoint_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_endpoint(
    endpoint_id: uuid.UUID,
    current_user: CurrentUserDep,
    session: SessionDep,
) -> None:
    ep = await _get_endpoint_or_404(endpoint_id, session)
    await _enforce_perm(
        "delete", "webhook", user_id=current_user.id, org_id=ep.org_id, session=session
    )
    await session.delete(ep)
    await session.commit()
    log.info("webhook.endpoint.deleted", endpoint_id=str(endpoint_id))


# ─── Delivery log ─────────────────────────────────────────────────────────────


@router.get("/deliveries", response_model=list[DeliveryOut])
async def list_deliveries(
    current_user: CurrentUserDep,
    session: SessionDep,
    endpoint_id: uuid.UUID | None = Query(None),
    delivery_status: str | None = Query(None, alias="status"),
    cursor: datetime | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
) -> list[DeliveryOut]:
    """Cursor-paginated delivery log.

    cursor is the created_at of the last item from the previous page (exclusive).
    """
    stmt = select(WebhookDelivery)

    if endpoint_id is not None:
        # Verify requester is a member of the endpoint's org
        ep = await _get_endpoint_or_404(endpoint_id, session)
        await _assert_org_member(ep.org_id, current_user.id, session)
        stmt = stmt.where(WebhookDelivery.endpoint_id == endpoint_id)
    else:
        # Scope to endpoints belonging to orgs the user is a member of
        member_org_ids_q = select(OrgMember.org_id).where(OrgMember.user_id == current_user.id)
        user_endpoint_ids_q = select(WebhookEndpoint.id).where(
            WebhookEndpoint.org_id.in_(member_org_ids_q)
        )
        stmt = stmt.where(WebhookDelivery.endpoint_id.in_(user_endpoint_ids_q))

    if delivery_status is not None:
        stmt = stmt.where(WebhookDelivery.status == delivery_status)

    if cursor is not None:
        stmt = stmt.where(WebhookDelivery.created_at < cursor)

    stmt = stmt.order_by(WebhookDelivery.created_at.desc()).limit(limit)
    result = await session.execute(stmt)
    return [DeliveryOut.model_validate(d) for d in result.scalars().all()]


# ─── Replay ───────────────────────────────────────────────────────────────────


@router.post("/deliveries/{delivery_id}/replay", response_model=DeliveryOut)
async def replay_delivery(
    delivery_id: uuid.UUID,
    current_user: CurrentUserDep,
    session: SessionDep,
) -> DeliveryOut:
    """Re-enqueue a delivery. Resets status to pending and clears retry state."""
    delivery = await session.get(WebhookDelivery, delivery_id)
    if delivery is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Delivery not found")

    ep = await _get_endpoint_or_404(delivery.endpoint_id, session)
    await _enforce_perm(
        "write", "webhook", user_id=current_user.id, org_id=ep.org_id, session=session
    )

    delivery.status = "pending"
    delivery.attempts = 0
    delivery.last_error = None
    delivery.next_retry_at = None
    delivery.completed_at = None
    await session.commit()
    await session.refresh(delivery)

    # Kick off delivery attempt via dispatcher. Strong-ref tracked — a bare
    # create_task can be GC'd mid-flight, silently dropping the replay.
    _spawn_tracked(
        _deliver_standalone(
            delivery.id,
            ep.url,
            ep.secret,
            delivery.payload,
            delivery.event_type,
        )
    )
    log.info("webhook.delivery.replayed", delivery_id=str(delivery_id))
    return DeliveryOut.model_validate(delivery)


# ─── Helpers ──────────────────────────────────────────────────────────────────


async def _get_endpoint_or_404(endpoint_id: uuid.UUID, session: Any) -> WebhookEndpoint:
    ep = await session.get(WebhookEndpoint, endpoint_id)
    if ep is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Endpoint not found")
    return ep


def _validate_events(events: list[str]) -> None:
    unknown = set(events) - EVENTS
    if unknown:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Unknown event types: {sorted(unknown)}. Valid: {sorted(EVENTS)}",
        )


async def _validate_url(url: str) -> None:
    """Reject SSRF-unsafe destination URLs at create/update time.

    Reuses the centralized SSRF guard (core.url_safety, the same policy webhook
    delivery uses) so invalid/internal endpoints are rejected early rather than
    silently failing on first delivery. Async-safe: DNS resolution runs off the
    event loop.
    """
    try:
        await assert_safe_url_async(url)
    except UnsafeURL as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Unsafe webhook URL: {exc}",
        ) from exc
