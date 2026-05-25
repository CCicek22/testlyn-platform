"""Tests for org_context.resolve_org_and_plan — DB-resolved org_id + plan.

These prove the shared resolver used by the rate-limit and IP-allowlist
middlewares: it maps a Firebase uid -> (org_id, plan) by querying Postgres
(OrgMember join Organization), caches per-uid with a short TTL, and degrades to
(None, "free") when the user has no membership.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from testlyn_api.core import org_context
from testlyn_api.models.org import Organization, OrgMember
from testlyn_api.models.user import User


async def _seed_user_org(
    session: AsyncSession, uid: str, plan: str
) -> tuple[uuid.UUID, uuid.UUID]:
    """Create a user (uuid5 from uid) belonging to one org with the given plan."""
    user_id = uuid.uuid5(uuid.NAMESPACE_URL, uid)
    org_id = uuid.uuid4()

    user = User(id=user_id, email=f"{uid}@example.com", name="U", firebase_uid=uid)
    session.add(user)
    await session.flush()

    org = Organization(id=org_id, name="Acme", slug=f"acme-{uuid.uuid4().hex[:8]}", plan=plan)
    session.add(org)
    await session.flush()

    session.add(OrgMember(org_id=org_id, user_id=user_id, role="owner"))
    await session.commit()
    return user_id, org_id


@pytest.fixture(autouse=True)
def _clear_org_context_cache():
    org_context.clear_cache()
    yield
    org_context.clear_cache()


@pytest.mark.asyncio
async def test_resolves_org_and_plan_for_member(db_session: AsyncSession) -> None:
    uid = "firebase-uid-pro"
    _, org_id = await _seed_user_org(db_session, uid, "pro")

    resolved_org, plan = await org_context.resolve_org_and_plan(uid)

    assert resolved_org == str(org_id)
    assert plan == "pro"


@pytest.mark.asyncio
async def test_no_membership_returns_none_free(db_session: AsyncSession) -> None:
    resolved_org, plan = await org_context.resolve_org_and_plan("uid-with-no-org")
    assert resolved_org is None
    assert plan == "free"


@pytest.mark.asyncio
async def test_cache_returns_same_value_within_ttl(db_session: AsyncSession) -> None:
    uid = "firebase-uid-cached"
    _, org_id = await _seed_user_org(db_session, uid, "hobby")

    first = await org_context.resolve_org_and_plan(uid)
    assert first == (str(org_id), "hobby")

    # Mutate the org plan directly; cached value should NOT change within TTL.
    org = await db_session.get(Organization, org_id)
    assert org is not None
    org.plan = "business"
    await db_session.commit()

    second = await org_context.resolve_org_and_plan(uid)
    assert second == first  # served from cache, still "hobby"

    # After invalidation the resolver re-reads the DB and sees the new plan.
    org_context.invalidate(uid)
    third = await org_context.resolve_org_and_plan(uid)
    assert third == (str(org_id), "business")


@pytest.mark.asyncio
async def test_deterministic_primary_org_is_earliest(db_session: AsyncSession) -> None:
    """User in two orgs -> resolver returns a single deterministic primary."""
    uid = "firebase-uid-multi"
    user_id = uuid.uuid5(uuid.NAMESPACE_URL, uid)
    session = db_session

    session.add(User(id=user_id, email=f"{uid}@x.com", name="M", firebase_uid=uid))
    await session.flush()

    org_a = Organization(id=uuid.uuid4(), name="A", slug=f"a-{uuid.uuid4().hex[:8]}", plan="pro")
    org_b = Organization(id=uuid.uuid4(), name="B", slug=f"b-{uuid.uuid4().hex[:8]}", plan="free")
    session.add_all([org_a, org_b])
    await session.flush()

    # org_a membership created first -> earliest created_at -> primary.
    session.add(OrgMember(org_id=org_a.id, user_id=user_id, role="owner"))
    await session.flush()
    session.add(OrgMember(org_id=org_b.id, user_id=user_id, role="member"))
    await session.commit()

    resolved_org, plan = await org_context.resolve_org_and_plan(uid)
    assert resolved_org == str(org_a.id)
    assert plan == "pro"
