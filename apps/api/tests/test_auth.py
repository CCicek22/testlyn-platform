from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_me_no_auth_bypass_returns_401(client: AsyncClient, monkeypatch) -> None:
    """Without bypass, missing auth header returns 401."""

    monkeypatch.setenv("DEV_AUTH_BYPASS", "false")

    # Reset settings cache so it picks up new env
    from testlyn_api import config as cfg_module

    cfg_module.get_settings.cache_clear()

    response = await client.get("/v1/me")
    assert response.status_code == 401

    # Restore
    cfg_module.get_settings.cache_clear()


@pytest.mark.asyncio
async def test_me_with_dev_bypass_returns_200(client: AsyncClient) -> None:
    response = await client.get("/v1/me")
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "dev@testlyn.io"
    assert "memberships" in data


@pytest.mark.asyncio
async def test_me_idempotent(client: AsyncClient) -> None:
    """Second call to /v1/me with bypass should not error (seed is idempotent)."""
    r1 = await client.get("/v1/me")
    r2 = await client.get("/v1/me")
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r1.json()["id"] == r2.json()["id"]


# ── First-login user resolution (SCIM adoption + insert race) ─────────────────


def _override_current_user(client_app, user):  # type: ignore[no-untyped-def]
    from testlyn_api import deps

    async def _fake() -> object:
        return user

    client_app.dependency_overrides[deps._resolve_current_user] = _fake


@pytest.mark.asyncio
async def test_me_scim_provisioned_user_first_login(client: AsyncClient, db_session) -> None:
    """SCIM creates the user with a uuid4 id; the first Firebase login derives a
    DIFFERENT uuid5 id. /v1/me must adopt the SCIM row by email (and link the
    firebase uid) instead of blind-INSERTing into a unique-email 500."""
    import uuid as _uuid

    from testlyn_api.core.auth import CurrentUser
    from testlyn_api.main import app
    from testlyn_api.models.org import Organization
    from testlyn_api.models.user import User
    from testlyn_api.services.scim import scim_create_user

    org = Organization(name="ScimLoginOrg", slug=f"scim-{_uuid.uuid4().hex[:6]}")
    db_session.add(org)
    await db_session.commit()

    email = "scim-user@example.com"
    firebase_uid = "fb-scim-123"
    scim_resource = await scim_create_user(
        db_session,
        org.id,
        {"userName": email, "externalId": None, "name": {"formatted": "Scim User"}},
        "http://testserver",
    )
    scim_row_id = _uuid.UUID(scim_resource["id"])

    derived_id = _uuid.uuid5(_uuid.NAMESPACE_URL, firebase_uid)
    assert derived_id != scim_row_id  # the bug precondition

    _override_current_user(
        app, CurrentUser(id=derived_id, email=email, firebase_uid=firebase_uid)
    )
    try:
        resp = await client.get("/v1/me")
    finally:
        from testlyn_api import deps

        app.dependency_overrides.pop(deps._resolve_current_user, None)

    assert resp.status_code == 200, resp.text
    data = resp.json()
    # The SCIM row was adopted — not a new row under the derived id.
    assert data["id"] == str(scim_row_id)
    assert data["email"] == email
    # Memberships come from the adopted row's id.
    assert any(m["org_id"] == str(org.id) for m in data["memberships"])

    # The firebase uid was linked onto the adopted row.
    from sqlalchemy import select

    row = (
        await db_session.execute(select(User).where(User.id == scim_row_id))
    ).scalar_one()
    assert row.firebase_uid == firebase_uid

    # Second login keeps working (idempotent).
    _override_current_user(
        app, CurrentUser(id=derived_id, email=email, firebase_uid=firebase_uid)
    )
    try:
        resp2 = await client.get("/v1/me")
    finally:
        from testlyn_api import deps

        app.dependency_overrides.pop(deps._resolve_current_user, None)
    assert resp2.status_code == 200
    assert resp2.json()["id"] == str(scim_row_id)


@pytest.mark.asyncio
async def test_get_or_create_user_first_login_race_tolerated(db_session) -> None:
    """The loser of a concurrent first-login INSERT recovers via re-select
    (savepoint + IntegrityError tolerance) instead of 500ing."""
    import uuid as _uuid

    from sqlalchemy.exc import IntegrityError
    from testlyn_api.core.auth import CurrentUser
    from testlyn_api.models.user import User
    from testlyn_api.routers.auth import _get_or_create_user

    cu = CurrentUser(
        id=_uuid.uuid5(_uuid.NAMESPACE_URL, "fb-race"),
        email="race@example.com",
        firebase_uid="fb-race",
    )

    class _WinnerThenConflict:
        """Simulates the concurrent request winning the INSERT race: the row
        appears in the transaction, then our own INSERT raises IntegrityError."""

        async def __aenter__(self):
            db_session.add(
                User(id=cu.id, email=cu.email, firebase_uid=cu.firebase_uid)
            )
            await db_session.flush()
            raise IntegrityError("INSERT INTO users", {}, Exception("UNIQUE"))

        async def __aexit__(self, *exc):
            return False

    real_begin_nested = db_session.begin_nested
    db_session.begin_nested = lambda: _WinnerThenConflict()  # type: ignore[method-assign]
    try:
        user = await _get_or_create_user(db_session, cu)
    finally:
        db_session.begin_nested = real_begin_nested  # type: ignore[method-assign]

    assert user.id == cu.id
    assert user.email == cu.email
