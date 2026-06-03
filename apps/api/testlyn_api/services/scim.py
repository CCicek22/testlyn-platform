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
from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from testlyn_api.models.org import OrgMember
from testlyn_api.models.user import User

log = structlog.get_logger(__name__)

SCIM_USER_SCHEMA = "urn:ietf:params:scim:schemas:core:2.0:User"
SCIM_GROUP_SCHEMA = "urn:ietf:params:scim:schemas:core:2.0:Group"
SCIM_LIST_SCHEMA = "urn:ietf:params:scim:api:messages:2.0:ListResponse"
SCIM_ERROR_SCHEMA = "urn:ietf:params:scim:api:messages:2.0:Error"


class ScimConflict(Exception):
    """Raised when a SCIM create targets an already-existing resource.

    RFC 7644 §3.3: POST to /Users with a userName that already exists (and is
    already a member of the org) must return 409 Conflict, not 201.
    """


def _now_iso() -> str:
    return datetime.now(tz=UTC).isoformat()


# ---------------------------------------------------------------------------
# Serialisers
# ---------------------------------------------------------------------------


def user_to_scim(
    user: User, org_id: uuid.UUID, base_url: str, *, active: bool = True
) -> dict[str, Any]:
    """Convert a User ORM row to a SCIM User resource dict.

    ``active`` reflects whether the user still has membership in ``org_id``.
    Callers must pass ``active=False`` after a deactivation so the IdP does not
    treat the user as active and trigger a reactivation loop (RFC 7644).
    """
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
        "active": active,
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


def _parse_username_filter(filter_str: str | None) -> str | None:
    """Extract the email from a SCIM ``userName eq "x"`` filter, else None."""
    if not filter_str or "userName eq" not in filter_str or '"' not in filter_str:
        return None
    return filter_str.split('"')[1]


async def scim_list_users(
    session: AsyncSession,
    org_id: uuid.UUID,
    base_url: str,
    start_index: int = 1,
    count: int = 100,
    filter_str: str | None = None,
) -> dict[str, Any]:
    """GET /v2/scim/{org_id}/Users

    The ``userName eq`` filter is applied at the DB level (joining members to
    users) so a matching member is found regardless of paging — IdP sync issues
    ``?filter=userName eq "x"`` and expects the single match. ``totalResults``
    reflects the *filtered* set so the IdP can decide create-vs-update.
    """
    email_filter = _parse_username_filter(filter_str)

    base_q = (
        select(User)
        .join(OrgMember, OrgMember.user_id == User.id)
        .where(OrgMember.org_id == org_id)
    )
    if email_filter is not None:
        base_q = base_q.where(User.email == email_filter)

    total_result = await session.execute(
        select(func.count()).select_from(base_q.subquery())
    )
    total = total_result.scalar_one()

    page_q = base_q.order_by(User.created_at.asc()).offset(start_index - 1).limit(count)
    users_result = await session.execute(page_q)
    resources = [
        user_to_scim(user, org_id, base_url) for user in users_result.scalars().all()
    ]

    return {
        "schemas": [SCIM_LIST_SCHEMA],
        "totalResults": total,
        "startIndex": start_index,
        # RFC 7644: itemsPerPage is the count of resources actually returned in
        # this page, not the requested page size.
        "itemsPerPage": len(resources),
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

    existing = await session.execute(select(User).where(User.email == email))
    user = existing.scalar_one_or_none()
    if user is not None:
        # User already exists; if already a member of this org the resource
        # already exists → 409 Conflict (RFC 7644 §3.3). If the user exists but
        # is not yet a member, this is a (re)provision → add membership.
        member_check = await session.execute(
            select(OrgMember).where(
                OrgMember.org_id == org_id, OrgMember.user_id == user.id
            )
        )
        if member_check.scalar_one_or_none() is not None:
            raise ScimConflict(f"User {email} already exists in org")
        session.add(OrgMember(org_id=org_id, user_id=user.id, role="member"))
    else:
        user = User(email=email, name=name, firebase_uid=external_id)
        session.add(user)
        await session.flush()
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
    # Reflect the post-mutation membership state: after a deactivation the user
    # is no longer a member, so the resource must report active=False (else the
    # IdP sees the user as active and re-creates / reactivates → sync loop).
    return user_to_scim(user, org_id, base_url, active=bool(active))


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
