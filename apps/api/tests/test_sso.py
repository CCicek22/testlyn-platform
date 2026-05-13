"""Tests for SSO provider CRUD + user provisioning service."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from testlyn_api.models.org import Organization, OrgMember
from testlyn_api.models.sso_provider import SsoProvider
from testlyn_api.services.sso import (
    FeatureDisabledError,
    OidcHandler,
    SamlHandler,
    get_active_provider,
    provision_sso_user,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _make_org(session: AsyncSession) -> Organization:
    org = Organization(name="SSO Corp", slug=f"sso-corp-{uuid.uuid4().hex[:8]}")
    session.add(org)
    await session.commit()
    await session.refresh(org)
    return org


# ---------------------------------------------------------------------------
# SSO provider CRUD via API
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_sso_provider_saml(client: AsyncClient, dev_org_id: uuid.UUID) -> None:
    resp = await client.post(
        f"/v1/orgs/{dev_org_id}/sso-providers",
        json={
            "kind": "saml",
            "metadata_xml_or_discovery_url": "<EntityDescriptor>...</EntityDescriptor>",
            "attribute_mappings": {"email": "email", "name": "displayName"},
            "active": True,
        },
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["kind"] == "saml"
    assert data["active"] is True
    assert data["attribute_mappings"]["email"] == "email"


@pytest.mark.asyncio
async def test_create_sso_provider_oidc(client: AsyncClient, dev_org_id: uuid.UUID) -> None:
    resp = await client.post(
        f"/v1/orgs/{dev_org_id}/sso-providers",
        json={
            "kind": "oidc",
            "metadata_xml_or_discovery_url": "https://accounts.google.com/.well-known/openid-configuration",
        },
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["kind"] == "oidc"


@pytest.mark.asyncio
async def test_create_sso_provider_invalid_kind(client: AsyncClient, dev_org_id: uuid.UUID) -> None:
    resp = await client.post(
        f"/v1/orgs/{dev_org_id}/sso-providers",
        json={"kind": "oauth1", "metadata_xml_or_discovery_url": "https://example.com"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_list_sso_providers(client: AsyncClient, dev_org_id: uuid.UUID) -> None:
    # Create two providers
    for kind in ("saml", "oidc"):
        await client.post(
            f"/v1/orgs/{dev_org_id}/sso-providers",
            json={"kind": kind, "metadata_xml_or_discovery_url": f"https://idp-{kind}.example.com"},
        )

    resp = await client.get(f"/v1/orgs/{dev_org_id}/sso-providers")
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) >= 2
    kinds = {p["kind"] for p in items}
    assert "saml" in kinds and "oidc" in kinds


@pytest.mark.asyncio
async def test_get_sso_provider(client: AsyncClient, dev_org_id: uuid.UUID) -> None:
    create_resp = await client.post(
        f"/v1/orgs/{dev_org_id}/sso-providers",
        json={"kind": "saml", "metadata_xml_or_discovery_url": "<xml/>"},
    )
    pid = create_resp.json()["id"]
    resp = await client.get(f"/v1/orgs/{dev_org_id}/sso-providers/{pid}")
    assert resp.status_code == 200
    assert resp.json()["id"] == pid


@pytest.mark.asyncio
async def test_get_sso_provider_not_found(client: AsyncClient, dev_org_id: uuid.UUID) -> None:
    resp = await client.get(f"/v1/orgs/{dev_org_id}/sso-providers/{uuid.uuid4()}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_replace_sso_provider(client: AsyncClient, dev_org_id: uuid.UUID) -> None:
    create_resp = await client.post(
        f"/v1/orgs/{dev_org_id}/sso-providers",
        json={"kind": "saml", "metadata_xml_or_discovery_url": "<old/>", "active": True},
    )
    pid = create_resp.json()["id"]
    resp = await client.put(
        f"/v1/orgs/{dev_org_id}/sso-providers/{pid}",
        json={"kind": "oidc", "metadata_xml_or_discovery_url": "https://new.example.com", "active": False},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["kind"] == "oidc"
    assert data["active"] is False


@pytest.mark.asyncio
async def test_delete_sso_provider(client: AsyncClient, dev_org_id: uuid.UUID) -> None:
    create_resp = await client.post(
        f"/v1/orgs/{dev_org_id}/sso-providers",
        json={"kind": "saml", "metadata_xml_or_discovery_url": "<xml/>"},
    )
    pid = create_resp.json()["id"]
    del_resp = await client.delete(f"/v1/orgs/{dev_org_id}/sso-providers/{pid}")
    assert del_resp.status_code == 204
    get_resp = await client.get(f"/v1/orgs/{dev_org_id}/sso-providers/{pid}")
    assert get_resp.status_code == 404


# ---------------------------------------------------------------------------
# Scaffold login/ACS/callback endpoints return 501
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sso_login_stub(client: AsyncClient) -> None:
    resp = await client.get(f"/v1/sso/{uuid.uuid4()}/login")
    assert resp.status_code == 501


@pytest.mark.asyncio
async def test_saml_acs_stub(client: AsyncClient) -> None:
    resp = await client.post(f"/v1/sso/{uuid.uuid4()}/acs")
    assert resp.status_code == 501


@pytest.mark.asyncio
async def test_oidc_callback_stub(client: AsyncClient) -> None:
    resp = await client.get(f"/v1/sso/{uuid.uuid4()}/callback")
    assert resp.status_code == 501


@pytest.mark.asyncio
async def test_saml_metadata_stub(client: AsyncClient) -> None:
    resp = await client.get(f"/v1/sso/{uuid.uuid4()}/metadata")
    assert resp.status_code == 501


# ---------------------------------------------------------------------------
# Service: user provisioning
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_provision_sso_user_new(db_session: AsyncSession, dev_org_id: uuid.UUID) -> None:
    email = f"new-sso-{uuid.uuid4().hex[:8]}@corp.example"
    user = await provision_sso_user(
        db_session, org_id=dev_org_id, email=email, name="New SSO User", external_sub="okta|123"
    )
    assert user.email == email
    assert user.name == "New SSO User"


@pytest.mark.asyncio
async def test_provision_sso_user_idempotent(db_session: AsyncSession, dev_org_id: uuid.UUID) -> None:
    email = f"idem-{uuid.uuid4().hex[:8]}@corp.example"
    u1 = await provision_sso_user(db_session, org_id=dev_org_id, email=email, name="A", external_sub=None)
    u2 = await provision_sso_user(db_session, org_id=dev_org_id, email=email, name="B", external_sub=None)
    assert u1.id == u2.id


@pytest.mark.asyncio
async def test_provision_sso_user_adds_membership(db_session: AsyncSession) -> None:
    from sqlalchemy import select

    org = await _make_org(db_session)
    email = f"mbr-{uuid.uuid4().hex[:8]}@corp.example"
    user = await provision_sso_user(db_session, org_id=org.id, email=email, name=None, external_sub=None)
    result = await db_session.execute(
        select(OrgMember).where(OrgMember.org_id == org.id, OrgMember.user_id == user.id)
    )
    member = result.scalar_one_or_none()
    assert member is not None
    assert member.role == "member"


# ---------------------------------------------------------------------------
# Service: optional lib graceful degradation
# ---------------------------------------------------------------------------


def test_saml_handler_feature_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    import testlyn_api.services.sso as sso_mod

    monkeypatch.setattr(sso_mod, "SamlHandler", SamlHandler)
    handler = SamlHandler()
    handler._auth_cls = None  # simulate missing lib
    with pytest.raises(FeatureDisabledError):
        handler._require_lib()


def test_oidc_handler_feature_disabled() -> None:
    handler = OidcHandler()
    handler._client_cls = None  # simulate missing lib
    with pytest.raises(FeatureDisabledError):
        handler._require_lib()


# ---------------------------------------------------------------------------
# Service: get_active_provider
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_active_provider(db_session: AsyncSession) -> None:
    org = await _make_org(db_session)
    provider = SsoProvider(
        org_id=org.id,
        kind="saml",
        metadata_xml_or_discovery_url="<xml/>",
        attribute_mappings={},
        active=True,
    )
    db_session.add(provider)
    await db_session.commit()

    found = await get_active_provider(db_session, org.id, kind="saml")
    assert found is not None
    assert found.kind == "saml"


@pytest.mark.asyncio
async def test_get_active_provider_none_when_inactive(db_session: AsyncSession) -> None:
    org = await _make_org(db_session)
    provider = SsoProvider(
        org_id=org.id,
        kind="oidc",
        metadata_xml_or_discovery_url="https://example.com",
        attribute_mappings={},
        active=False,
    )
    db_session.add(provider)
    await db_session.commit()

    found = await get_active_provider(db_session, org.id)
    assert found is None
