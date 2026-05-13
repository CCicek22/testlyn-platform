"""SCIM v2 provisioning service.

Implements the SCIM 2.0 core schema for Users and Groups
(RFC 7643 / RFC 7644).  Bearer token auth is configured per org via
org.scim_token (not yet stored — see TODO below).

Schemas used:
  urn:ietf:params:scim:schemas:core:2.0:User
  urn:ietf:params:scim:schemas:core:2.0:Group

Audit hook point for SOC 2 evidence trail:
  After every mutating SCIM operation, emit action='scim.<op>' via
  AuditService (W3A owns the audit schema — call existing service).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from testlyn_api.models.org import OrgMember
from testlyn_api.models.user import User

log = structlog.get_logger(__name__)

SCIM_USER_SCHEMA = "urn:ietf:params:scim:schemas:core:2.0:User"
SCIM_GROUP_SCHEMA = "urn:ietf:params:scim:schemas:core:2.0:Group"
SCIM_LIST_SCHEMA = "urn:ietf:params:scim:api:messages:2.0:ListResponse"
SCIM_ERROR_SCHEMA = "urn:ietf:params:scim:api:messages:2.0:Error"


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Serialisers
# ---------------------------------------------------------------------------


def user_to_scim(user: User, org_id: uuid.UUID, base_url: str) -> dict[str, Any]:
    """Convert a User ORM row to a SCIM User resource dict."""
    location = f"{base_url}/v2/scim/{org_id}/Users/{user.id}"
    return {
        "schemas": [SCIM_USER_SCHEMA],
        "id": str(user.id),
        "externalId": user.firebase_uid,
        "userName": user.email,
        "name": {
            "formatted": user.name or "",
            "givenName": "",
            "familyName": "",
        },
        "emails": [{"value": user.email, "primary": True}],
        "active": True,
        "meta": {
            "resourceType": "User",
            "created": user.created_at.isoformat() if user.created_at else _now_iso(),
            "lastModified": user.updated_at.isoformat() if user.updated_at else _now_iso(),
            "location": location,
        },
    }


def scim_error(status: int, detail: str) -> dict[str, Any]:
    return {
        "schemas": [SCIM_ERROR_SCHEMA],
        "status": str(status),
        "detail": detail,
    }


# ---------------------------------------------------------------------------
# SCIM Users
# ---------------------------------------------------------------------------


async def scim_list_users(
    session: AsyncSession,
    org_id: uuid.UUID,
    base_url: str,
    start_index: int = 1,
    count: int = 100,
    filter_str: str | None = None,
) -> dict[str, Any]:
    """GET /v2/scim/{org_id}/Users"""
    # Get all org members then load their users
    members_result = await session.execute(
        select(OrgMember).where(OrgMember.org_id == org_id).offset(start_index - 1).limit(count)
    )
    members = list(members_result.scalars().all())
    user_ids = [m.user_id for m in members]

    resources: list[dict[str, Any]] = []
    if user_ids:
        users_result = await session.execute(select(User).where(User.id.in_(user_ids)))
        for user in users_result.scalars().all():
            # Simple filter support: userName eq "..."
            if filter_str:
                if "userName eq" in filter_str:
                    email_filter = filter_str.split('"')[1] if '"' in filter_str else None
                    if email_filter and user.email != email_filter:
                        continue
            resources.append(user_to_scim(user, org_id, base_url))

    total_result = await session.execute(
        select(OrgMember).where(OrgMember.org_id == org_id)
    )
    total = len(list(total_result.scalars().all()))

    return {
        "schemas": [SCIM_LIST_SCHEMA],
        "totalResults": total,
        "startIndex": start_index,
        "itemsPerPage": count,
        "Resources": resources,
    }


async def scim_get_user(
    session: AsyncSession,
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    base_url: str,
) -> dict[str, Any] | None:
    """GET /v2/scim/{org_id}/Users/{user_id}"""
    # Verify membership
    member_result = await session.execute(
        select(OrgMember).where(
            OrgMember.org_id == org_id, OrgMember.user_id == user_id
        )
    )
    if member_result.scalar_one_or_none() is None:
        return None

    user_result = await session.execute(select(User).where(User.id == user_id))
    user = user_result.scalar_one_or_none()
    if user is None:
        return None
    return user_to_scim(user, org_id, base_url)


async def scim_create_user(
    session: AsyncSession,
    org_id: uuid.UUID,
    payload: dict[str, Any],
    base_url: str,
) -> dict[str, Any]:
    """POST /v2/scim/{org_id}/Users — provision a new user via SCIM."""
    email = payload.get("userName") or ""
    name = (payload.get("name") or {}).get("formatted") or payload.get("displayName")
    external_id = payload.get("externalId")

    # Idempotent: return existing user if email already exists
    existing = await session.execute(select(User).where(User.email == email))
    user = existing.scalar_one_or_none()
    if user is None:
        user = User(email=email, name=name, firebase_uid=external_id)
        session.add(user)
        await session.flush()

    # Ensure membership
    member_check = await session.execute(
        select(OrgMember).where(OrgMember.org_id == org_id, OrgMember.user_id == user.id)
    )
    if member_check.scalar_one_or_none() is None:
        session.add(OrgMember(org_id=org_id, user_id=user.id, role="member"))

    await session.commit()
    await session.refresh(user)
    log.info("scim.user_created", email=email, org_id=str(org_id))
    return user_to_scim(user, org_id, base_url)


async def scim_replace_user(
    session: AsyncSession,
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    payload: dict[str, Any],
    base_url: str,
) -> dict[str, Any] | None:
    """PUT /v2/scim/{org_id}/Users/{user_id}"""
    member_result = await session.execute(
        select(OrgMember).where(OrgMember.org_id == org_id, OrgMember.user_id == user_id)
    )
    member = member_result.scalar_one_or_none()
    if member is None:
        return None

    user_result = await session.execute(select(User).where(User.id == user_id))
    user = user_result.scalar_one_or_none()
    if user is None:
        return None

    name = (payload.get("name") or {}).get("formatted") or payload.get("displayName")
    if name:
        user.name = name

    active = payload.get("active", True)
    if not active:
        # Deactivation: remove org membership (user row kept for audit trail)
        await session.delete(member)
        log.info("scim.user_deactivated", user_id=str(user_id), org_id=str(org_id))

    await session.commit()
    await session.refresh(user)
    return user_to_scim(user, org_id, base_url)


async def scim_delete_user(
    session: AsyncSession,
    org_id: uuid.UUID,
    user_id: uuid.UUID,
) -> bool:
    """DELETE /v2/scim/{org_id}/Users/{user_id} — removes org membership only."""
    member_result = await session.execute(
        select(OrgMember).where(OrgMember.org_id == org_id, OrgMember.user_id == user_id)
    )
    member = member_result.scalar_one_or_none()
    if member is None:
        return False
    await session.delete(member)
    await session.commit()
    log.info("scim.user_deleted", user_id=str(user_id), org_id=str(org_id))
    return True


# ---------------------------------------------------------------------------
# SCIM Groups — scaffold (Phase 4 GA: map to RBAC roles/teams)
# ---------------------------------------------------------------------------


async def scim_list_groups(
    org_id: uuid.UUID,
    base_url: str,
    start_index: int = 1,
    count: int = 100,
) -> dict[str, Any]:
    """GET /v2/scim/{org_id}/Groups — scaffold returns empty list."""
    return {
        "schemas": [SCIM_LIST_SCHEMA],
        "totalResults": 0,
        "startIndex": start_index,
        "itemsPerPage": count,
        "Resources": [],
    }
