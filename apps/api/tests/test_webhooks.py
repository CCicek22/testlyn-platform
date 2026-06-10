"""Tests for webhook service + admin API."""

from __future__ import annotations

import hashlib
import hmac
import inspect
import socket
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession
from testlyn_api.models.org import Organization, OrgMember
from testlyn_api.models.user import User
from testlyn_api.models.webhook import WebhookDelivery, WebhookEndpoint
from testlyn_api.services.webhooks import EVENTS, WebhookDispatcher, _sign

# Resolve every webhook hostname to a public IP so the SSRF guard
# (_assert_safe_url, now also enforced on create/update) passes offline in CI.
_PUBLIC_ADDRINFO = [
    (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("93.184.216.34", 443))
]


@pytest.fixture(autouse=True)
def _mock_public_dns():
    with patch("socket.getaddrinfo", return_value=_PUBLIC_ADDRINFO):
        yield

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
    org_id = await _seed_org(db_session)
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
    org_id = await _seed_org(db_session)
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
    org_id = await _seed_org(db_session)
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
        # Patch _spawn_tracked so the background coroutine is never scheduled
        # (avoids "coroutine was never awaited" warning in tests).
        with patch(
            "testlyn_api.services.webhooks._spawn_tracked",
            new=MagicMock(side_effect=_cancel_coro),
        ):
            ids = await dispatcher.fire(org_id, "test.completed", {"run_id": "r1"})

    assert len(ids) == 1


@pytest.mark.asyncio
async def test_dispatcher_fire_commits_before_scheduling(
    db_session: AsyncSession,
) -> None:
    """Regression: fire() must COMMIT delivery rows before scheduling background
    delivery. _deliver_standalone opens its own session; if the row is only
    flushed (not committed) the standalone session sees None and silently drops
    the delivery. We capture the delivery_id handed to the background task and
    assert that, at schedule time, a *separate* session can already read it.
    """
    org_id = await _seed_org(db_session)
    ep = WebhookEndpoint(
        org_id=org_id,
        url="https://example.com/hook",
        secret="s",
        events=["test.completed"],
        active=True,
    )
    db_session.add(ep)
    await db_session.commit()

    # The race is purely about ordering: was the producer session committed at
    # the moment the background task is scheduled? A standalone session (as used
    # by _deliver_standalone) can only see the row if commit already happened.
    # We capture, at _spawn_tracked() time, whether the producer session still
    # has an open (uncommitted) transaction — pre-fix it does (commit comes
    # after), post-fix it does not.
    open_txn_at_schedule: list[bool] = []

    def _capture(coro: object) -> None:
        open_txn_at_schedule.append(db_session.in_transaction())
        if inspect.iscoroutine(coro):
            coro.close()  # don't actually deliver

    dispatcher = WebhookDispatcher(db_session)
    with patch(
        "testlyn_api.services.webhooks._deliver_standalone", new=AsyncMock()
    ), patch(
        "testlyn_api.services.webhooks._spawn_tracked",
        new=MagicMock(side_effect=_capture),
    ):
        ids = await dispatcher.fire(org_id, "test.completed", {"run_id": "r1"})

    assert len(ids) == 1
    # A delivery WAS scheduled (vs. silently dropped) ...
    assert open_txn_at_schedule == [False], (
        "producer session still in an uncommitted transaction when the "
        "background delivery was scheduled → standalone session would see None"
    )


# ─── Retry scheduling: failed deliveries are actually re-delivered ────────────


async def _seed_endpoint_and_delivery(
    db_session: AsyncSession,
) -> tuple[uuid.UUID, uuid.UUID]:
    org_id = await _seed_org(db_session)
    ep = WebhookEndpoint(
        org_id=org_id,
        url="https://example.com/hook",
        secret="s",
        events=["test.completed"],
        active=True,
    )
    db_session.add(ep)
    await db_session.flush()
    delivery = WebhookDelivery(
        endpoint_id=ep.id,
        event_type="test.completed",
        payload={"run_id": "retry"},
        status="pending",
    )
    db_session.add(delivery)
    await db_session.commit()
    return ep.id, delivery.id


async def _wait_for_status(delivery_id: uuid.UUID, wanted: set[str], timeout: float = 2.0) -> str:
    """Poll the delivery row from a fresh session until it reaches a wanted status."""
    import asyncio

    from testlyn_api.core.db import _session_factory

    deadline = asyncio.get_event_loop().time() + timeout
    status_now = ""
    while asyncio.get_event_loop().time() < deadline:
        async with _session_factory() as session:
            row = await session.get(WebhookDelivery, delivery_id)
            status_now = row.status if row else ""
        if status_now in wanted:
            return status_now
        await asyncio.sleep(0.02)
    return status_now


@pytest.mark.asyncio
async def test_failed_delivery_is_retried_until_success(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failed deliver() schedules an in-process retry that re-delivers."""
    import testlyn_api.services.webhooks as webhooks

    _, delivery_id = await _seed_endpoint_and_delivery(db_session)

    calls = {"n": 0}

    async def _fake_post(**kwargs) -> bool:
        calls["n"] += 1
        return calls["n"] >= 2  # fail first attempt, succeed on the retry

    monkeypatch.setattr(webhooks, "_post", _fake_post)
    monkeypatch.setattr(webhooks, "_RETRY_DELAYS", [0, 0])

    ok = await webhooks.WebhookDispatcher(db_session).deliver(delivery_id)
    assert ok is False  # first attempt failed

    final = await _wait_for_status(delivery_id, {"completed"})
    assert final == "completed"
    assert calls["n"] == 2


@pytest.mark.asyncio
async def test_failed_delivery_abandoned_after_max_attempts(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Retries stop (abandoned) once attempts exceed the retry schedule."""
    import testlyn_api.services.webhooks as webhooks

    _, delivery_id = await _seed_endpoint_and_delivery(db_session)

    calls = {"n": 0}

    async def _always_fail(**kwargs) -> bool:
        calls["n"] += 1
        return False

    monkeypatch.setattr(webhooks, "_post", _always_fail)
    monkeypatch.setattr(webhooks, "_RETRY_DELAYS", [0])  # 1 retry max

    ok = await webhooks.WebhookDispatcher(db_session).deliver(delivery_id)
    assert ok is False

    final = await _wait_for_status(delivery_id, {"abandoned"})
    assert final == "abandoned"
    assert calls["n"] == 2  # initial attempt + exactly one retry


# ─── RBAC: webhook admin requires admin for mutations (finding #5) ────────────


async def _set_role(session: AsyncSession, org_id: uuid.UUID, role: str) -> None:
    await session.execute(
        update(OrgMember)
        .where(OrgMember.org_id == org_id, OrgMember.user_id == _DEV_USER_ID)
        .values(role=role)
    )
    await session.commit()


async def _create_endpoint_as_owner(client: AsyncClient, org_id: uuid.UUID) -> str:
    resp = await client.post(
        f"/v1/webhooks-admin/orgs/{org_id}/endpoints",
        json={"url": "https://example.com/hook", "events": ["test.completed"]},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


@pytest.mark.parametrize("role,expected", [("viewer", 403), ("member", 403), ("admin", 201)])
@pytest.mark.asyncio
async def test_create_endpoint_requires_admin(
    client: AsyncClient, db_session: AsyncSession, role: str, expected: int
) -> None:
    org_id = await _seed_org(db_session)
    await _set_role(db_session, org_id, role)
    resp = await client.post(
        f"/v1/webhooks-admin/orgs/{org_id}/endpoints",
        json={"url": "https://example.com/hook", "events": ["test.completed"]},
    )
    assert resp.status_code == expected, resp.text


@pytest.mark.parametrize("role,expected", [("viewer", 403), ("member", 403), ("admin", 200)])
@pytest.mark.asyncio
async def test_patch_endpoint_requires_admin(
    client: AsyncClient, db_session: AsyncSession, role: str, expected: int
) -> None:
    org_id = await _seed_org(db_session)
    ep_id = await _create_endpoint_as_owner(client, org_id)
    await _set_role(db_session, org_id, role)
    resp = await client.patch(
        f"/v1/webhooks-admin/endpoints/{ep_id}", json={"active": False}
    )
    assert resp.status_code == expected, resp.text


@pytest.mark.parametrize("role,expected", [("viewer", 403), ("member", 403), ("admin", 204)])
@pytest.mark.asyncio
async def test_delete_endpoint_requires_admin(
    client: AsyncClient, db_session: AsyncSession, role: str, expected: int
) -> None:
    org_id = await _seed_org(db_session)
    ep_id = await _create_endpoint_as_owner(client, org_id)
    await _set_role(db_session, org_id, role)
    resp = await client.delete(f"/v1/webhooks-admin/endpoints/{ep_id}")
    assert resp.status_code == expected, resp.text


@pytest.mark.parametrize("role,expected", [("viewer", 403), ("member", 403), ("admin", 200)])
@pytest.mark.asyncio
async def test_replay_delivery_requires_admin(
    client: AsyncClient, db_session: AsyncSession, role: str, expected: int
) -> None:
    org_id = await _seed_org(db_session)
    ep_id = uuid.UUID(await _create_endpoint_as_owner(client, org_id))
    delivery = WebhookDelivery(
        endpoint_id=ep_id,
        event_type="test.completed",
        payload={"run_id": "rbac"},
        status="abandoned",
        attempts=6,
    )
    db_session.add(delivery)
    await db_session.commit()
    await db_session.refresh(delivery)
    await _set_role(db_session, org_id, role)

    with patch(
        "testlyn_api.routers.webhooks_admin._deliver_standalone",
        new=AsyncMock(return_value=None),
    ):
        resp = await client.post(f"/v1/webhooks-admin/deliveries/{delivery.id}/replay")
    assert resp.status_code == expected, resp.text


# ─── SSRF: destination URL validated on create/update ─────────────────────────


@pytest.mark.asyncio
async def test_create_endpoint_rejects_ssrf_url(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Even an admin cannot register a metadata/internal destination URL."""
    org_id = await _seed_org(db_session)  # dev user is owner (>= admin)
    resp = await client.post(
        f"/v1/webhooks-admin/orgs/{org_id}/endpoints",
        json={"url": "http://metadata.google.internal/x", "events": ["test.completed"]},
    )
    assert resp.status_code == 422, resp.text


@pytest.mark.asyncio
async def test_patch_endpoint_rejects_ssrf_url(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    org_id = await _seed_org(db_session)
    ep_id = await _create_endpoint_as_owner(client, org_id)
    resp = await client.patch(
        f"/v1/webhooks-admin/endpoints/{ep_id}",
        json={"url": "http://169.254.169.254/latest/meta-data/"},
    )
    assert resp.status_code == 422, resp.text


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
