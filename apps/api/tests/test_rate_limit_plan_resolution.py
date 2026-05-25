"""Proves the rate limiter resolves the org's *plan* from the DB on the verified
Bearer path — so paid tiers get their real RPM bucket instead of the free 60.

Uses the shared conftest (which wires core.db._session_factory to the in-memory
test engine) so org_context.resolve_org_and_plan hits the same DB we seed here.
``verify_token`` is mocked to simulate a verified Firebase token carrying a uid.
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from testlyn_api.core import org_context
from testlyn_api.core.rate_limit import TIER_RPM, RateLimitMiddleware
from testlyn_api.models.org import Organization, OrgMember
from testlyn_api.models.user import User


@pytest.fixture(autouse=True)
def _clear_caches():
    org_context.clear_cache()
    yield
    org_context.clear_cache()


async def _seed_pro_user(session: AsyncSession, uid: str) -> uuid.UUID:
    user_id = uuid.uuid5(uuid.NAMESPACE_URL, uid)
    org_id = uuid.uuid4()
    session.add(User(id=user_id, email=f"{uid}@x.com", name="P", firebase_uid=uid))
    await session.flush()
    session.add(
        Organization(id=org_id, name="Pro Co", slug=f"pro-{uuid.uuid4().hex[:8]}", plan="pro")
    )
    await session.flush()
    session.add(OrgMember(org_id=org_id, user_id=user_id, role="owner"))
    await session.commit()
    return org_id


def _request_with_bearer() -> MagicMock:
    req = MagicMock()
    headers = {"Authorization": "Bearer fake.jwt.token"}
    req.headers.get = lambda key, default="": headers.get(key, default)
    req.url.path = "/v1/tests"
    req.client.host = "203.0.113.9"
    return req


@pytest.mark.asyncio
async def test_pro_org_gets_pro_limit_not_free(db_session: AsyncSession) -> None:
    """The whole point: a 'pro' org must resolve to the 6000 RPM bucket, not 60."""
    uid = "verified-pro-uid"
    org_id = await _seed_pro_user(db_session, uid)

    mw = RateLimitMiddleware(app=MagicMock())
    req = _request_with_bearer()

    # Firebase verification returns a verified token carrying the uid (no org_id).
    with patch(
        "testlyn_api.core.token_verify.verify_token",
        return_value={"uid": uid, "email": f"{uid}@x.com"},
    ):
        resolved_org, plan = await mw._resolve_identity(req)

    assert resolved_org == str(org_id)
    assert plan == "pro"
    assert TIER_RPM[plan] == 6_000  # not the free 60


@pytest.mark.asyncio
async def test_verified_user_without_org_falls_back_to_ip_free(db_session: AsyncSession) -> None:
    """A verified token whose uid has no membership -> IP key, free tier (no crash)."""
    mw = RateLimitMiddleware(app=MagicMock())
    req = _request_with_bearer()

    with patch(
        "testlyn_api.core.token_verify.verify_token",
        return_value={"uid": "stranger-uid", "email": "s@x.com"},
    ):
        resolved_org, plan = await mw._resolve_identity(req)

    assert resolved_org == "ip:203.0.113.9"
    assert plan == "free"
