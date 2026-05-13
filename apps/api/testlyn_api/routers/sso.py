"""SSO provider CRUD + scaffold login/ACS endpoints.

Endpoints
---------
GET    /v1/orgs/{org_id}/sso-providers              — list providers (owner)
POST   /v1/orgs/{org_id}/sso-providers              — create provider (owner)
GET    /v1/orgs/{org_id}/sso-providers/{pid}        — get provider (owner)
PUT    /v1/orgs/{org_id}/sso-providers/{pid}        — replace provider (owner)
DELETE /v1/orgs/{org_id}/sso-providers/{pid}        — delete provider (owner)

GET    /v1/sso/{pid}/login                          — redirect to IdP (public)
POST   /v1/sso/{pid}/acs                            — SAML ACS (public)
GET    /v1/sso/{pid}/callback                       — OIDC callback (public)
GET    /v1/sso/{pid}/metadata                       — SAML SP metadata (public)
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

import structlog
from fastapi import APIRouter, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import select

from testlyn_api.core.permissions import perm_dep
from testlyn_api.deps import CurrentUserDep, SessionDep
from testlyn_api.models.sso_provider import SsoProvider

log = structlog.get_logger(__name__)

router = APIRouter(tags=["sso"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class SsoProviderCreate(BaseModel):
    kind: str  # "saml" | "oidc"
    metadata_xml_or_discovery_url: str
    attribute_mappings: dict[str, Any] = {}
    active: bool = True


class SsoProviderOut(BaseModel):
    id: uuid.UUID
    org_id: uuid.UUID
    kind: str
    metadata_xml_or_discovery_url: str
    attribute_mappings: dict[str, Any]
    active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


@router.get(
    "/v1/orgs/{org_id}/sso-providers",
    response_model=list[SsoProviderOut],
    dependencies=[perm_dep("write", "org")],
)
async def list_sso_providers(
    org_id: uuid.UUID,
    current_user: CurrentUserDep,
    session: SessionDep,
) -> list[SsoProviderOut]:
    result = await session.execute(
        select(SsoProvider)
        .where(SsoProvider.org_id == org_id)
        .order_by(SsoProvider.created_at.asc())
    )
    return [SsoProviderOut.model_validate(p) for p in result.scalars().all()]


@router.post(
    "/v1/orgs/{org_id}/sso-providers",
    response_model=SsoProviderOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[perm_dep("write", "org")],
)
async def create_sso_provider(
    org_id: uuid.UUID,
    body: SsoProviderCreate,
    current_user: CurrentUserDep,
    session: SessionDep,
) -> SsoProviderOut:
    if body.kind not in ("saml", "oidc"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="kind must be 'saml' or 'oidc'",
        )
    provider = SsoProvider(
        org_id=org_id,
        kind=body.kind,
        metadata_xml_or_discovery_url=body.metadata_xml_or_discovery_url,
        attribute_mappings=body.attribute_mappings,
        active=body.active,
    )
    session.add(provider)
    await session.commit()
    await session.refresh(provider)
    log.info("sso_provider.created", provider_id=str(provider.id), org_id=str(org_id))
    return SsoProviderOut.model_validate(provider)


@router.get(
    "/v1/orgs/{org_id}/sso-providers/{pid}",
    response_model=SsoProviderOut,
    dependencies=[perm_dep("write", "org")],
)
async def get_sso_provider(
    org_id: uuid.UUID,
    pid: uuid.UUID,
    current_user: CurrentUserDep,
    session: SessionDep,
) -> SsoProviderOut:
    result = await session.execute(
        select(SsoProvider).where(SsoProvider.id == pid, SsoProvider.org_id == org_id)
    )
    provider = result.scalar_one_or_none()
    if provider is None:
        raise HTTPException(status_code=404, detail="SSO provider not found")
    return SsoProviderOut.model_validate(provider)


@router.put(
    "/v1/orgs/{org_id}/sso-providers/{pid}",
    response_model=SsoProviderOut,
    dependencies=[perm_dep("write", "org")],
)
async def replace_sso_provider(
    org_id: uuid.UUID,
    pid: uuid.UUID,
    body: SsoProviderCreate,
    current_user: CurrentUserDep,
    session: SessionDep,
) -> SsoProviderOut:
    result = await session.execute(
        select(SsoProvider).where(SsoProvider.id == pid, SsoProvider.org_id == org_id)
    )
    provider = result.scalar_one_or_none()
    if provider is None:
        raise HTTPException(status_code=404, detail="SSO provider not found")
    if body.kind not in ("saml", "oidc"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="kind must be 'saml' or 'oidc'",
        )
    provider.kind = body.kind
    provider.metadata_xml_or_discovery_url = body.metadata_xml_or_discovery_url
    provider.attribute_mappings = body.attribute_mappings
    provider.active = body.active
    await session.commit()
    await session.refresh(provider)
    return SsoProviderOut.model_validate(provider)


@router.delete(
    "/v1/orgs/{org_id}/sso-providers/{pid}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[perm_dep("write", "org")],
)
async def delete_sso_provider(
    org_id: uuid.UUID,
    pid: uuid.UUID,
    current_user: CurrentUserDep,
    session: SessionDep,
) -> None:
    result = await session.execute(
        select(SsoProvider).where(SsoProvider.id == pid, SsoProvider.org_id == org_id)
    )
    provider = result.scalar_one_or_none()
    if provider is None:
        raise HTTPException(status_code=404, detail="SSO provider not found")
    await session.delete(provider)
    await session.commit()
    log.info("sso_provider.deleted", provider_id=str(pid), org_id=str(org_id))


# ---------------------------------------------------------------------------
# Login / ACS / Callback — scaffold (Phase 4 GA: full IdP round-trip)
# ---------------------------------------------------------------------------


@router.get("/v1/sso/{pid}/login", include_in_schema=True, tags=["sso"])
async def sso_login(pid: uuid.UUID) -> JSONResponse:
    """Redirect to IdP for SP-initiated SSO. Phase 4 GA: returns real redirect."""
    return JSONResponse(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        content={
            "detail": "SSO login redirect not yet implemented (Phase 4 GA)",
            "provider_id": str(pid),
        },
    )


@router.post("/v1/sso/{pid}/acs", include_in_schema=True, tags=["sso"])
async def saml_acs(pid: uuid.UUID) -> JSONResponse:
    """SAML Assertion Consumer Service. Phase 4 GA: parse + validate assertion."""
    return JSONResponse(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        content={
            "detail": "SAML ACS not yet implemented (Phase 4 GA)",
            "provider_id": str(pid),
        },
    )


@router.get("/v1/sso/{pid}/callback", include_in_schema=True, tags=["sso"])
async def oidc_callback(pid: uuid.UUID) -> JSONResponse:
    """OIDC authorization code callback. Phase 4 GA: exchange code + provision user."""
    return JSONResponse(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        content={
            "detail": "OIDC callback not yet implemented (Phase 4 GA)",
            "provider_id": str(pid),
        },
    )


@router.get("/v1/sso/{pid}/metadata", include_in_schema=True, tags=["sso"])
async def saml_sp_metadata(pid: uuid.UUID) -> JSONResponse:
    """Return SAML SP metadata XML. Phase 4 GA: generate real SP metadata."""
    return JSONResponse(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        content={
            "detail": "SAML SP metadata endpoint not yet implemented (Phase 4 GA)",
            "provider_id": str(pid),
        },
    )
