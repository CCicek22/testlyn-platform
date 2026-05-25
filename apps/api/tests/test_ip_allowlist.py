"""Tests for IP allowlist middleware and helper utilities."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from testlyn_api.core.ip_allowlist import (
    AllowlistDBError,
    _cache,
    _extract_client_ip,
    _ip_in_cidr_list,
    _load_cidrs,
    invalidate_cache,
)
from testlyn_api.models.org import Organization
from testlyn_api.models.org_ip_allowlist import OrgIpAllowlist

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _make_org(session: AsyncSession) -> Organization:
    org = Organization(name="IP Corp", slug=f"ip-corp-{uuid.uuid4().hex[:8]}")
    session.add(org)
    await session.commit()
    await session.refresh(org)
    return org


async def _add_cidr(
    session: AsyncSession, org_id: uuid.UUID, cidr: str, active: bool = True
) -> OrgIpAllowlist:
    entry = OrgIpAllowlist(org_id=org_id, cidr=cidr, active=active)
    session.add(entry)
    await session.commit()
    return entry


# ---------------------------------------------------------------------------
# Unit: _ip_in_cidr_list
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "ip, cidrs, expected",
    [
        ("192.168.1.1", ["192.168.1.0/24"], True),
        ("192.168.2.1", ["192.168.1.0/24"], False),
        ("10.0.0.5", ["10.0.0.0/8"], True),
        ("172.16.0.1", ["172.16.0.0/12"], True),
        ("8.8.8.8", ["10.0.0.0/8", "192.168.0.0/16"], False),
        ("127.0.0.1", ["127.0.0.0/8"], True),
        ("::1", ["::1/128"], True),
        ("not-an-ip", ["10.0.0.0/8"], False),
        ("10.0.0.1", ["not-a-cidr"], False),
        ("10.0.0.1", [], False),
    ],
)
def test_ip_in_cidr_list(ip: str, cidrs: list[str], expected: bool) -> None:
    assert _ip_in_cidr_list(ip, cidrs) is expected


# ---------------------------------------------------------------------------
# Unit: _extract_client_ip
# ---------------------------------------------------------------------------


def _make_request(xff: str | None = None, client_host: str = "10.0.0.1"):
    """Minimal mock of a Starlette Request for IP extraction tests."""
    from unittest.mock import MagicMock

    req = MagicMock()
    headers = {}
    if xff:
        headers["X-Forwarded-For"] = xff
    req.headers.get = lambda key, default="": headers.get(key, default)
    req.client.host = client_host
    return req


def test_extract_client_ip_no_xff() -> None:
    req = _make_request()
    assert _extract_client_ip(req) == "10.0.0.1"


def test_extract_client_ip_single_xff() -> None:
    req = _make_request(xff="203.0.113.5")
    # trusted_depth=1 → take the rightmost entry = index -1
    assert _extract_client_ip(req, trusted_depth=1) == "203.0.113.5"


def test_extract_client_ip_multi_xff_depth1() -> None:
    # "client, proxy1, lb" — lb added the last entry; client is leftmost
    req = _make_request(xff="203.0.113.5, 10.1.1.1, 172.16.0.1")
    # depth=1 → take entry at index -1 = "172.16.0.1" (outermost proxy added it)
    assert _extract_client_ip(req, trusted_depth=1) == "172.16.0.1"


def test_extract_client_ip_multi_xff_depth2() -> None:
    req = _make_request(xff="203.0.113.5, 10.1.1.1, 172.16.0.1")
    # depth=2 → index -2 = "10.1.1.1"
    assert _extract_client_ip(req, trusted_depth=2) == "10.1.1.1"


def test_extract_client_ip_depth_exceeds_entries() -> None:
    req = _make_request(xff="203.0.113.5")
    # depth=5 but only 1 entry → fall back to parts[0]
    assert _extract_client_ip(req, trusted_depth=5) == "203.0.113.5"


# ---------------------------------------------------------------------------
# Unit: invalidate_cache
# ---------------------------------------------------------------------------


def test_invalidate_cache_clears_entry() -> None:
    _cache["some-org"] = (["10.0.0.0/8"], 9999999999.0)
    invalidate_cache("some-org")
    assert "some-org" not in _cache


def test_invalidate_cache_noop_on_missing() -> None:
    # Should not raise when key not present
    invalidate_cache("nonexistent-org")


# ---------------------------------------------------------------------------
# API integration: middleware allow-all when no CIDR entries
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_middleware_allow_all_when_no_entries(
    client: AsyncClient, dev_org_id: uuid.UUID
) -> None:
    """No CIDR entries → request should pass through (200 from actual endpoint)."""
    # We test against a real /v1/ endpoint with an org_id path segment.
    # The SSO providers list endpoint is a good candidate (returns 200 with empty list).
    resp = await client.get(f"/v1/orgs/{dev_org_id}/sso-providers")
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# API integration: middleware blocks + allows based on CIDR entries
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_middleware_blocks_ip_outside_cidr(
    client: AsyncClient,
    db_session: AsyncSession,
    dev_org_id: uuid.UUID,
) -> None:
    """Request from 1.2.3.4 should be blocked when only 10.0.0.0/8 is allowed."""
    await _add_cidr(db_session, dev_org_id, "10.0.0.0/8")
    # Clear cache so middleware re-reads from DB
    invalidate_cache(str(dev_org_id))

    # Patch _load_cidrs to return our CIDRs synchronously (avoids SQLite UUID cast issue)
    with patch(
        "testlyn_api.core.ip_allowlist._load_cidrs",
        new=AsyncMock(return_value=["10.0.0.0/8"]),
    ):
        resp = await client.get(
            f"/v1/orgs/{dev_org_id}/sso-providers",
            headers={"X-Forwarded-For": "1.2.3.4"},
        )
    assert resp.status_code == 403
    assert "not allowed" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_middleware_allows_ip_inside_cidr(
    client: AsyncClient,
    dev_org_id: uuid.UUID,
) -> None:
    """Request from 10.0.0.5 should pass when 10.0.0.0/8 is in the allowlist."""
    invalidate_cache(str(dev_org_id))

    with patch(
        "testlyn_api.core.ip_allowlist._load_cidrs",
        new=AsyncMock(return_value=["10.0.0.0/8"]),
    ):
        resp = await client.get(
            f"/v1/orgs/{dev_org_id}/sso-providers",
            headers={"X-Forwarded-For": "10.0.0.5"},
        )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_middleware_skips_non_v1_paths(
    client: AsyncClient,
    dev_org_id: uuid.UUID,
) -> None:
    """SCIM (/v2/) path is exempt from IP allowlist enforcement."""
    invalidate_cache(str(dev_org_id))

    with patch(
        "testlyn_api.core.ip_allowlist._load_cidrs",
        new=AsyncMock(return_value=["10.0.0.0/8"]),
    ):
        # Even from an "outside" IP, SCIM endpoint should respond (not 403)
        resp = await client.get(
            f"/v2/scim/{dev_org_id}/Users",
            headers={"X-Forwarded-For": "1.2.3.4"},
        )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_org_resolved_from_token_on_non_orgs_route(
    client: AsyncClient,
    dev_org_id: uuid.UUID,
) -> None:
    """Authenticated user's org is resolved from the verified token (via DB),
    so the allowlist now enforces on a route WITHOUT an /orgs/{id} segment.

    Proves the fix: previously _extract_org_id could only get org_id from the
    URL path, so allowlist was bypassed on every non-/v1/orgs route.
    """
    invalidate_cache(str(dev_org_id))

    with (
        patch(
            "testlyn_api.core.token_verify.verify_token",
            return_value={"uid": "member-uid", "email": "m@x.com"},
        ),
        patch(
            "testlyn_api.core.org_context.resolve_org_and_plan",
            new=AsyncMock(return_value=(str(dev_org_id), "pro")),
        ),
        patch(
            "testlyn_api.core.ip_allowlist._load_cidrs",
            new=AsyncMock(return_value=["10.0.0.0/8"]),
        ),
    ):
        # /v1/tests has NO /orgs/{id} segment — org_id can only come from token.
        resp = await client.get(
            "/v1/tests",
            headers={
                "Authorization": "Bearer fake.jwt.token",
                "X-Forwarded-For": "1.2.3.4",  # outside 10.0.0.0/8
            },
        )
    assert resp.status_code == 403
    assert "not allowed" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_middleware_cache_invalidation(
    client: AsyncClient,
    dev_org_id: uuid.UUID,
) -> None:
    """invalidate_cache clears TTL so next request re-reads from DB."""
    import time

    org_key = str(dev_org_id)
    _cache[org_key] = (["10.0.0.0/8"], time.monotonic() + 30)

    # Before invalidation: stale cache has a CIDR
    assert org_key in _cache

    invalidate_cache(org_key)

    # After invalidation: cache miss — no entry
    assert org_key not in _cache

    # Next middleware request will re-load (no entries in DB → allow-all)
    resp = await client.get(f"/v1/orgs/{dev_org_id}/sso-providers")
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Fail-CLOSED on DB error (operator decision 2026-05-24)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_load_cidrs_raises_on_db_error() -> None:
    """A DB failure must raise AllowlistDBError, NOT collapse to allow-all []."""
    org_id = str(uuid.uuid4())  # valid UUID so the failure is the session, not parse
    invalidate_cache(org_id)
    with patch(
        "testlyn_api.core.db._session_factory",
        side_effect=RuntimeError("connection refused"),
    ):
        with pytest.raises(AllowlistDBError):
            await _load_cidrs(org_id)
    # Must NOT cache the failure — next call retries the DB.
    assert org_id not in _cache


@pytest.mark.asyncio
async def test_middleware_denies_on_db_error(
    client: AsyncClient,
    dev_org_id: uuid.UUID,
) -> None:
    """DB error while loading CIDRs → 403 deny (fail closed), distinct from
    the zero-entries allow-all path."""
    invalidate_cache(str(dev_org_id))
    with patch(
        "testlyn_api.core.ip_allowlist._load_cidrs",
        new=AsyncMock(side_effect=AllowlistDBError(str(dev_org_id))),
    ):
        resp = await client.get(
            f"/v1/orgs/{dev_org_id}/sso-providers",
            headers={"X-Forwarded-For": "10.0.0.5"},  # would pass if it were allow-all
        )
    assert resp.status_code == 403
    assert "temporarily unavailable" in resp.json()["detail"]
