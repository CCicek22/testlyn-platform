"""Tests for SCIM v2 provisioning endpoints and service layer."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from testlyn_api.models.org import Organization, OrgMember
from testlyn_api.models.user import User
from testlyn_api.services.scim import (
    SCIM_LIST_SCHEMA,
    SCIM_USER_SCHEMA,
    scim_create_user,
    scim_delete_user,
    scim_error,
    scim_get_user,
    scim_list_groups,
    scim_list_users,
    scim_replace_user,
    user_to_scim,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _make_org(session: AsyncSession) -> Organization:
    org = Organization(name="SCIM Corp", slug=f"scim-corp-{uuid.uuid4().hex[:8]}")
    session.add(org)
    await session.commit()
    await session.refresh(org)
    return org


async def _make_user(session: AsyncSession, email: str, name: str | None = None) -> User:
    user = User(email=email, name=name, firebase_uid=f"uid-{uuid.uuid4().hex[:8]}")
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def _add_member(session: AsyncSession, org_id: uuid.UUID, user_id: uuid.UUID) -> OrgMember:
    member = OrgMember(org_id=org_id, user_id=user_id, role="member")
    session.add(member)
    await session.commit()
    return member


_BASE_URL = "http://testserver"


# ---------------------------------------------------------------------------
# Service unit tests: user_to_scim + scim_error
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_user_to_scim_shape(db_session: AsyncSession) -> None:
    org = await _make_org(db_session)
    user = await _make_user(db_session, "alice@example.com", "Alice")
    result = user_to_scim(user, org.id, _BASE_URL)
    assert result["schemas"] == [SCIM_USER_SCHEMA]
    assert result["userName"] == "alice@example.com"
    assert result["name"]["formatted"] == "Alice"
    assert result["emails"][0]["value"] == "alice@example.com"
    assert result["active"] is True
    assert f"{org.id}/Users/{user.id}" in result["meta"]["location"]


def test_scim_error_shape() -> None:
    err = scim_error(404, "Not found")
    assert err["status"] == "404"
    assert err["detail"] == "Not found"


# ---------------------------------------------------------------------------
# Service: scim_list_users
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scim_list_users_empty(db_session: AsyncSession) -> None:
    org = await _make_org(db_session)
    result = await scim_list_users(db_session, org.id, _BASE_URL)
    assert result["schemas"] == [SCIM_LIST_SCHEMA]
    assert result["totalResults"] == 0
    assert result["Resources"] == []


@pytest.mark.asyncio
async def test_scim_list_users_returns_members(db_session: AsyncSession) -> None:
    org = await _make_org(db_session)
    user = await _make_user(db_session, "bob@example.com", "Bob")
    await _add_member(db_session, org.id, user.id)

    result = await scim_list_users(db_session, org.id, _BASE_URL)
    assert result["totalResults"] == 1
    assert len(result["Resources"]) == 1
    assert result["Resources"][0]["userName"] == "bob@example.com"


@pytest.mark.asyncio
async def test_scim_list_users_filter_by_username(db_session: AsyncSession) -> None:
    org = await _make_org(db_session)
    u1 = await _make_user(db_session, "carol@example.com")
    u2 = await _make_user(db_session, "dan@example.com")
    await _add_member(db_session, org.id, u1.id)
    await _add_member(db_session, org.id, u2.id)

    result = await scim_list_users(
        db_session, org.id, _BASE_URL, filter_str='userName eq "carol@example.com"'
    )
    assert len(result["Resources"]) == 1
    assert result["Resources"][0]["userName"] == "carol@example.com"


# ---------------------------------------------------------------------------
# Service: scim_get_user
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scim_get_user_found(db_session: AsyncSession) -> None:
    org = await _make_org(db_session)
    user = await _make_user(db_session, "eve@example.com", "Eve")
    await _add_member(db_session, org.id, user.id)

    result = await scim_get_user(db_session, org.id, user.id, _BASE_URL)
    assert result is not None
    assert result["id"] == str(user.id)


@pytest.mark.asyncio
async def test_scim_get_user_not_member(db_session: AsyncSession) -> None:
    org = await _make_org(db_session)
    user = await _make_user(db_session, "frank@example.com")
    # user exists but not a member of this org
    result = await scim_get_user(db_session, org.id, user.id, _BASE_URL)
    assert result is None


@pytest.mark.asyncio
async def test_scim_get_user_nonexistent(db_session: AsyncSession) -> None:
    org = await _make_org(db_session)
    result = await scim_get_user(db_session, org.id, uuid.uuid4(), _BASE_URL)
    assert result is None


# ---------------------------------------------------------------------------
# Service: scim_create_user
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scim_create_user_new(db_session: AsyncSession) -> None:
    org = await _make_org(db_session)
    payload = {
        "schemas": [SCIM_USER_SCHEMA],
        "userName": "grace@example.com",
        "name": {"formatted": "Grace Hopper"},
        "externalId": "okta|grace",
    }
    result = await scim_create_user(db_session, org.id, payload, _BASE_URL)
    assert result["userName"] == "grace@example.com"
    assert result["name"]["formatted"] == "Grace Hopper"

    # Membership created
    member = await db_session.execute(
        select(OrgMember).where(OrgMember.org_id == org.id)
    )
    assert member.scalar_one_or_none() is not None


@pytest.mark.asyncio
async def test_scim_create_user_idempotent(db_session: AsyncSession) -> None:
    org = await _make_org(db_session)
    payload = {
        "userName": "heidi@example.com",
        "name": {"formatted": "Heidi"},
        "externalId": None,
    }
    r1 = await scim_create_user(db_session, org.id, payload, _BASE_URL)
    r2 = await scim_create_user(db_session, org.id, payload, _BASE_URL)
    assert r1["id"] == r2["id"]

    # Only one membership row
    members = await db_session.execute(
        select(OrgMember).where(OrgMember.org_id == org.id)
    )
    assert len(list(members.scalars().all())) == 1


# ---------------------------------------------------------------------------
# Service: scim_replace_user
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scim_replace_user_updates_name(db_session: AsyncSession) -> None:
    org = await _make_org(db_session)
    user = await _make_user(db_session, "ivan@example.com", "Ivan")
    await _add_member(db_session, org.id, user.id)

    result = await scim_replace_user(
        db_session,
        org.id,
        user.id,
        {"name": {"formatted": "Ivan Updated"}, "active": True},
        _BASE_URL,
    )
    assert result is not None
    assert result["name"]["formatted"] == "Ivan Updated"


@pytest.mark.asyncio
async def test_scim_replace_user_deactivation_removes_membership(db_session: AsyncSession) -> None:
    org = await _make_org(db_session)
    user = await _make_user(db_session, "judy@example.com", "Judy")
    await _add_member(db_session, org.id, user.id)

    await scim_replace_user(
        db_session,
        org.id,
        user.id,
        {"active": False},
        _BASE_URL,
    )

    # Membership removed
    member = await db_session.execute(
        select(OrgMember).where(OrgMember.org_id == org.id, OrgMember.user_id == user.id)
    )
    assert member.scalar_one_or_none() is None

    # User row still exists (audit trail preserved)
    user_row = await db_session.execute(select(User).where(User.id == user.id))
    assert user_row.scalar_one_or_none() is not None


@pytest.mark.asyncio
async def test_scim_replace_user_not_found(db_session: AsyncSession) -> None:
    org = await _make_org(db_session)
    result = await scim_replace_user(db_session, org.id, uuid.uuid4(), {}, _BASE_URL)
    assert result is None


# ---------------------------------------------------------------------------
# Service: scim_delete_user
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scim_delete_user_removes_membership_only(db_session: AsyncSession) -> None:
    org = await _make_org(db_session)
    user = await _make_user(db_session, "karl@example.com", "Karl")
    await _add_member(db_session, org.id, user.id)

    deleted = await scim_delete_user(db_session, org.id, user.id)
    assert deleted is True

    # Membership gone
    member = await db_session.execute(
        select(OrgMember).where(OrgMember.org_id == org.id, OrgMember.user_id == user.id)
    )
    assert member.scalar_one_or_none() is None

    # User row preserved
    user_row = await db_session.execute(select(User).where(User.id == user.id))
    assert user_row.scalar_one_or_none() is not None


@pytest.mark.asyncio
async def test_scim_delete_user_not_member(db_session: AsyncSession) -> None:
    org = await _make_org(db_session)
    deleted = await scim_delete_user(db_session, org.id, uuid.uuid4())
    assert deleted is False


# ---------------------------------------------------------------------------
# Service: scim_list_groups (scaffold)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scim_list_groups_empty_scaffold() -> None:
    result = await scim_list_groups(uuid.uuid4(), _BASE_URL)
    assert result["totalResults"] == 0
    assert result["Resources"] == []
    assert result["schemas"] == [SCIM_LIST_SCHEMA]


# ---------------------------------------------------------------------------
# API integration tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_api_list_users_empty(client: AsyncClient, dev_org_id: uuid.UUID) -> None:
    resp = await client.get(f"/v2/scim/{dev_org_id}/Users")
    assert resp.status_code == 200
    data = resp.json()
    assert data["schemas"] == [SCIM_LIST_SCHEMA]
    assert data["totalResults"] == 0


@pytest.mark.asyncio
async def test_api_create_and_get_user(client: AsyncClient, dev_org_id: uuid.UUID) -> None:
    resp = await client.post(
        f"/v2/scim/{dev_org_id}/Users",
        json={
            "schemas": [SCIM_USER_SCHEMA],
            "userName": f"scim-{uuid.uuid4().hex[:8]}@example.com",
            "name": {"formatted": "SCIM Test User"},
            "externalId": "okta|scim-test",
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["schemas"] == [SCIM_USER_SCHEMA]
    user_id = data["id"]

    # GET the same user
    get_resp = await client.get(f"/v2/scim/{dev_org_id}/Users/{user_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == user_id


@pytest.mark.asyncio
async def test_api_get_user_not_found(client: AsyncClient, dev_org_id: uuid.UUID) -> None:
    resp = await client.get(f"/v2/scim/{dev_org_id}/Users/{uuid.uuid4()}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_api_replace_user(client: AsyncClient, dev_org_id: uuid.UUID) -> None:
    create = await client.post(
        f"/v2/scim/{dev_org_id}/Users",
        json={
            "userName": f"rep-{uuid.uuid4().hex[:8]}@example.com",
            "name": {"formatted": "Original"},
        },
    )
    uid = create.json()["id"]
    resp = await client.put(
        f"/v2/scim/{dev_org_id}/Users/{uid}",
        json={"name": {"formatted": "Updated"}, "active": True},
    )
    assert resp.status_code == 200
    assert resp.json()["name"]["formatted"] == "Updated"


@pytest.mark.asyncio
async def test_api_delete_user(client: AsyncClient, dev_org_id: uuid.UUID) -> None:
    create = await client.post(
        f"/v2/scim/{dev_org_id}/Users",
        json={"userName": f"del-{uuid.uuid4().hex[:8]}@example.com"},
    )
    uid = create.json()["id"]
    del_resp = await client.delete(f"/v2/scim/{dev_org_id}/Users/{uid}")
    assert del_resp.status_code == 204

    # GET after delete should 404
    get_resp = await client.get(f"/v2/scim/{dev_org_id}/Users/{uid}")
    assert get_resp.status_code == 404


@pytest.mark.asyncio
async def test_api_list_groups_scaffold(client: AsyncClient, dev_org_id: uuid.UUID) -> None:
    resp = await client.get(f"/v2/scim/{dev_org_id}/Groups")
    assert resp.status_code == 200
    data = resp.json()
    assert data["totalResults"] == 0
    assert data["Resources"] == []


@pytest.mark.asyncio
async def test_api_bearer_token_rejected_when_bypass_disabled(
    client: AsyncClient, dev_org_id: uuid.UUID, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When DEV_AUTH_BYPASS is false, missing/empty bearer token must 401."""
    import testlyn_api.routers.scim as scim_router_mod

    class _FakeSettings:
        dev_auth_bypass = False
        scim_enabled = True

    # Patch where the router module resolves get_settings (its own import reference)
    monkeypatch.setattr(scim_router_mod, "get_settings", lambda: _FakeSettings())
    resp = await client.get(f"/v2/scim/{dev_org_id}/Users")
    assert resp.status_code == 401
