"""Enterprise settings: IP allowlist CRUD + CMEK config (read-only display).

Endpoints
---------
GET    /v1/orgs/{org_id}/ip-allowlist          — list entries (owner)
POST   /v1/orgs/{org_id}/ip-allowlist          — add CIDR (owner)
DELETE /v1/orgs/{org_id}/ip-allowlist/{entry}  — remove CIDR (owner)
GET    /v1/orgs/{org_id}/cmek                  — show CMEK config (owner)
"""

from __future__ import annotations

import ipaddress
import uuid
from datetime import datetime

import structlog
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, field_validator
from sqlalchemy import select

from testlyn_api.core.ip_allowlist import invalidate_cache
from testlyn_api.core.permissions import perm_dep
from testlyn_api.deps import CurrentUserDep, SessionDep
from testlyn_api.models.org_ip_allowlist import OrgIpAllowlist

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/v1/orgs", tags=["enterprise"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class IpAllowlistCreate(BaseModel):
    cidr: str
    description: str | None = None
    active: bool = True

    @field_validator("cidr")
    @classmethod
    def validate_cidr(cls, v: str) -> str:
        try:
            ipaddress.ip_network(v, strict=False)
        except ValueError:
            raise ValueError(f"Invalid CIDR notation: {v!r}")
        return v


class IpAllowlistOut(BaseModel):
    id: uuid.UUID
    org_id: uuid.UUID
    cidr: str
    description: str | None
    active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class CmekConfigOut(BaseModel):
    """Read-only display of CMEK configuration.

    The actual key is managed via Terraform (infra/terraform/modules/cmek/).
    This endpoint surfaces the configured key name for UI display; it reads
    from the GCP_CMEK_KEY_NAME env var set during deployment.
    """

    cmek_key_name: str | None
    note: str


# ---------------------------------------------------------------------------
# IP allowlist endpoints
# ---------------------------------------------------------------------------


@router.get(
    "/{org_id}/ip-allowlist",
    response_model=list[IpAllowlistOut],
    dependencies=[perm_dep("write", "org")],
)
async def list_ip_allowlist(
    org_id: uuid.UUID,
    current_user: CurrentUserDep,
    session: SessionDep,
) -> list[IpAllowlistOut]:
    result = await session.execute(
        select(OrgIpAllowlist)
        .where(OrgIpAllowlist.org_id == org_id)
        .order_by(OrgIpAllowlist.created_at.asc())
    )
    return [IpAllowlistOut.model_validate(e) for e in result.scalars().all()]


@router.post(
    "/{org_id}/ip-allowlist",
    response_model=IpAllowlistOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[perm_dep("write", "org")],
)
async def create_ip_allowlist_entry(
    org_id: uuid.UUID,
    body: IpAllowlistCreate,
    current_user: CurrentUserDep,
    session: SessionDep,
) -> IpAllowlistOut:
    entry = OrgIpAllowlist(
        org_id=org_id,
        cidr=body.cidr,
        description=body.description,
        active=body.active,
    )
    session.add(entry)
    await session.commit()
    await session.refresh(entry)
    invalidate_cache(str(org_id))
    log.info("ip_allowlist.entry_created", org_id=str(org_id), cidr=body.cidr)
    return IpAllowlistOut.model_validate(entry)


@router.delete(
    "/{org_id}/ip-allowlist/{entry_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[perm_dep("write", "org")],
)
async def delete_ip_allowlist_entry(
    org_id: uuid.UUID,
    entry_id: uuid.UUID,
    current_user: CurrentUserDep,
    session: SessionDep,
) -> None:
    result = await session.execute(
        select(OrgIpAllowlist).where(
            OrgIpAllowlist.id == entry_id, OrgIpAllowlist.org_id == org_id
        )
    )
    entry = result.scalar_one_or_none()
    if entry is None:
        raise HTTPException(status_code=404, detail="IP allowlist entry not found")
    await session.delete(entry)
    await session.commit()
    invalidate_cache(str(org_id))
    log.info("ip_allowlist.entry_deleted", org_id=str(org_id), entry_id=str(entry_id))


# ---------------------------------------------------------------------------
# CMEK config (read-only — managed by Terraform)
# ---------------------------------------------------------------------------


@router.get(
    "/{org_id}/cmek",
    response_model=CmekConfigOut,
    dependencies=[perm_dep("write", "org")],
)
async def get_cmek_config(
    org_id: uuid.UUID,
    current_user: CurrentUserDep,
) -> CmekConfigOut:
    """Return the CMEK key configured for this deployment.

    The key is set at deploy time via the Terraform module
    infra/terraform/modules/cmek/ and surfaced here as a read-only display.
    No org-level CMEK override is supported in Phase 4 scaffold.
    """
    import os

    key_name = os.getenv("GCP_CMEK_KEY_NAME")
    return CmekConfigOut(
        cmek_key_name=key_name,
        note=(
            "CMEK is configured at the infrastructure level via Terraform. "
            "To change the key, update infra/terraform/modules/cmek/ and re-apply."
        ),
    )
