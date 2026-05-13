"""Tests for webhook service + admin API."""

from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from testlyn_api.models.org import Organization, OrgMember
from testlyn_api.models.user import User
from testlyn_api.models.webhook import WebhookDelivery, WebhookEndpoint
from testlyn_api.services.webhooks import EVENTS, WebhookDispatcher, _sign


# ─── Unit: HMAC helper ────────────────────────────────────────────────────────


def test_sign_returns_sha256_prefix() -> None:
    sig = _sign("secret", b"hello")
    assert sig.startswith("sha256=")


def test_sign_deterministic() -> None:
    assert _sign("secret", b"body") == _sign("secret", b"body")


def test_sign_differs_on_different_secret() -> None:
    assert _sign("s1", b"body") != _sign("s2", b"body")


def test_sign_correct_hmac() -> None:
    secret = "mysecret"
    body = b"payload"
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    assert _sign(secret, body) == expected


# ─── Unit: EVENTS set ─────────────────────────────────────────────────────────


def test_events_not_empty() -> None:
    assert len(EVENTS) >= 6


@pytest.mark.parametrize(
    "event",
    [
        "test.completed",
        "test.failed",
        "threshold.breached",
        "scan.findings_published",
        "subscription.updated",
        "member.invited",
    ],
)
def test_known_events_in_taxonomy(event: str) -> None:
    assert event in EVENTS


# ─── Integration: endpoints CRUD ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_endpoint(client: AsyncClient, db_session: AsyncSession) -> None:
    org_id = await _seed_org(db_session)

    resp = await client.post(
        f"/v1/webhooks-admin/orgs/{org_id}/endpoints",
        json={"url": "https://example.com/hook", "events": ["test.completed"]},
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["url"] == "https://example.com/hook"
    assert data["events"] == ["test.completed"]
    assert data["active"] is True
    assert "id" in data


@pytest.mark.asyncio
async def test_create_endpoint_unknown_event_rejected(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    org_id = await _seed_org(db_session)

    resp = await client.post(
        f"/v1/webhooks-admin/orgs/{org_id}/endpoints",
        json={"url": "https://example.com/hook", "events": ["not.a.real.event"]},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_list_endpoints(client: AsyncClient, db_session: AsyncSession) -> None:
    org_id = await _seed_org(db_session)

    await client.post(
        f"/v1/webhooks-admin/orgs/{org_id}/endpoints",
        json={"url": "https://example.com/a", "events": ["test.failed"]},
    )
    await client.post(
        f"/v1/webhooks-admin/orgs/{org_id}/endpoints",
        json={"url": "https://example.com/b", "events": ["test.completed"]},
    )

    resp = await client.get(f"/v1/webhooks-admin/orgs/{org_id}/endpoints")
    assert resp.status_code == 200
    assert len(resp.json()) == 2


@pytest.mark.asyncio
async def test_patch_endpoint(client: AsyncClient, db_session: AsyncSession) -> None:
    org_id = await _seed_org(db_session)

    create_resp = await client.post(
        f"/v1/webhooks-admin/orgs/{org_id}/endpoints",
        json={"url": "https://example.com/hook", "events": ["test.completed"]},
    )
    ep_id = create_resp.json()["id"]

    patch_resp = await client.patch(
        f"/v1/webhooks-admin/endpoints/{ep_id}",
        json={"active": False},
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["active"] is False


@pytest.mark.asyncio
async def test_delete_endpoint(client: AsyncClient, db_session: AsyncSession) -> None:
    org_id = await _seed_org(db_session)

    create_resp = await client.post(
        f"/v1/webhooks-admin/orgs/{org_id}/endpoints",
        json={"url": "https://example.com/hook", "events": ["test.completed"]},
    )
    ep_id = create_resp.json()["id"]

    del_resp = await client.delete(f"/v1/webhooks-admin/endpoints/{ep_id}")
    assert del_resp.status_code == 204

    get_resp = await client.get(f"/v1/webhooks-admin/endpoints/{ep_id}")
    assert get_resp.status_code == 404


# ─── Integration: delivery log ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_deliveries_empty(client: AsyncClient, db_session: AsyncSession) -> None:
    org_id = await _seed_org(db_session)
    ep_resp = await client.post(
        f"/v1/webhooks-admin/orgs/{org_id}/endpoints",
        json={"url": "https://example.com/hook", "events": ["test.completed"]},
    )
    ep_id = ep_resp.json()["id"]

    resp = await client.get(f"/v1/webhooks-admin/deliveries?endpoint_id={ep_id}")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_list_deliveries_with_data(client: AsyncClient, db_session: AsyncSession) -> None:
    org_id = await _seed_org(db_session)
    ep_resp = await client.post(
        f"/v1/webhooks-admin/orgs/{org_id}/endpoints",
        json={"url": "https://example.com/hook", "events": ["test.completed"]},
    )
    ep_id = uuid.UUID(ep_resp.json()["id"])

    # Seed a delivery row directly
    delivery = WebhookDelivery(
        endpoint_id=ep_id,
        event_type="test.completed",
        payload={"run_id": "abc"},
        status="completed",
    )
    db_session.add(delivery)
    await db_session.commit()

    resp = await client.get(f"/v1/webhooks-admin/deliveries?endpoint_id={ep_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["event_type"] == "test.completed"
    assert data[0]["status"] == "completed"


# ─── Integration: replay ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_replay_delivery(client: AsyncClient, db_session: AsyncSession) -> None:
    org_id = await _seed_org(db_session)
    ep_resp = await client.post(
        f"/v1/webhooks-admin/orgs/{org_id}/endpoints",
        json={"url": "https://example.com/hook", "events": ["test.completed"]},
    )
    ep_id = uuid.UUID(ep_resp.json()["id"])

    delivery = WebhookDelivery(
        endpoint_id=ep_id,
        event_type="test.completed",
        payload={"run_id": "xyz"},
        status="abandoned",
        attempts=6,
    )
    db_session.add(delivery)
    await db_session.commit()
    await db_session.refresh(delivery)

    with patch(
        "testlyn_api.routers.webhooks_admin._deliver_standalone",
        new=AsyncMock(return_value=None),
    ):
        resp = await client.post(f"/v1/webhooks-admin/deliveries/{delivery.id}/replay")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "pending"
    assert data["attempts"] == 0


# ─── Unit: WebhookDispatcher.fire ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_dispatcher_fire_skips_unknown_event(db_session: AsyncSession) -> None:
    dispatcher = WebhookDispatcher(db_session)
    ids = await dispatcher.fire(uuid.uuid4(), "not.a.real.event", {})
    assert ids == []


@pytest.mark.asyncio
async def test_dispatcher_fire_skips_inactive_endpoint(db_session: AsyncSession) -> None:
    org_id = uuid.uuid4()
    ep = WebhookEndpoint(
        org_id=org_id,
        url="https://example.com/hook",
        secret="s",
        events=["test.completed"],
        active=False,
    )
    db_session.add(ep)
    await db_session.commit()

    dispatcher = WebhookDispatcher(db_session)
    with patch("testlyn_api.services.webhooks._deliver_standalone", new=AsyncMock()):
        with patch("asyncio.create_task", new=MagicMock()):
            ids = await dispatcher.fire(org_id, "test.completed", {"x": 1})
    assert ids == []


@pytest.mark.asyncio
async def test_dispatcher_fire_skips_unsubscribed_event(db_session: AsyncSession) -> None:
    org_id = uuid.uuid4()
    ep = WebhookEndpoint(
        org_id=org_id,
        url="https://example.com/hook",
        secret="s",
        events=["test.failed"],  # subscribed to failed, not completed
        active=True,
    )
    db_session.add(ep)
    await db_session.commit()

    dispatcher = WebhookDispatcher(db_session)
    with patch("testlyn_api.services.webhooks._deliver_standalone", new=AsyncMock()):
        with patch("asyncio.create_task", new=MagicMock()):
            ids = await dispatcher.fire(org_id, "test.completed", {})
    assert ids == []


@pytest.mark.asyncio
async def test_dispatcher_fire_creates_delivery(db_session: AsyncSession) -> None:
    org_id = uuid.uuid4()
    ep = WebhookEndpoint(
        org_id=org_id,
        url="https://example.com/hook",
        secret="s",
        events=["test.completed"],
        active=True,
    )
    db_session.add(ep)
    await db_session.commit()

    def _cancel_coro(coro: object) -> None:
        """Consume the coroutine passed to create_task so GC doesn't warn."""
        import inspect

        if inspect.iscoroutine(coro):
            coro.close()

    dispatcher = WebhookDispatcher(db_session)
    with patch(
        "testlyn_api.services.webhooks._deliver_standalone",
        new=AsyncMock(return_value=None),
    ):
        # Patch create_task so the background coroutine is never scheduled
        # (avoids "coroutine was never awaited" warning in tests).
        with patch("asyncio.create_task", new=MagicMock(side_effect=_cancel_coro)):
            ids = await dispatcher.fire(org_id, "test.completed", {"run_id": "r1"})

    assert len(ids) == 1


# ─── Helpers ──────────────────────────────────────────────────────────────────

_DEV_USER_ID = uuid.UUID("00000000-0000-0000-0000-d3eff3e10101")


async def _seed_org(session: AsyncSession) -> uuid.UUID:
    """Seed a fresh org owned by the dev-bypass user and return org_id.

    We pre-seed the dev User so that when the request's auth-bypass calls
    ``_seed_dev_user`` it finds the row and returns immediately — avoiding a
    conflicting commit on the shared test session.
    """
    from sqlalchemy import select

    # Ensure dev User exists before OrgMember references it
    result = await session.execute(select(User).where(User.id == _DEV_USER_ID))
    if result.scalar_one_or_none() is None:
        session.add(
            User(
                id=_DEV_USER_ID,
                email="dev@testlyn.io",
                name="Dev User",
                firebase_uid=None,
            )
        )
        await session.flush()

    org_id = uuid.uuid4()
    org = Organization(id=org_id, name="Webhook Test Org", slug=f"wh-test-{org_id.hex[:6]}")
    session.add(org)
    await session.flush()
    member = OrgMember(org_id=org_id, user_id=_DEV_USER_ID, role="owner")
    session.add(member)
    await session.commit()
    return org_id
