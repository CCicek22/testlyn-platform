from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass

import structlog
from fastapi import HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from testlyn_api.config import get_settings

log = structlog.get_logger(__name__)

# Deterministic dev user UUID
_DEV_USER_ID = uuid.UUID("00000000-0000-0000-0000-d3eff3e10101")
_DEV_USER_EMAIL = "dev@testlyn.io"
_DEV_ORG_ID = uuid.UUID("00000000-0000-0000-0000-d3eff3e10102")


@dataclass
class CurrentUser:
    id: uuid.UUID
    email: str
    firebase_uid: str | None = None


async def _seed_dev_user(session: AsyncSession) -> None:
    """Seed dev user + default org into DB on first bypass call."""
    from sqlalchemy import select

    from testlyn_api.models.org import Organization, OrgMember
    from testlyn_api.models.user import User

    result = await session.execute(select(User).where(User.id == _DEV_USER_ID))
    if result.scalar_one_or_none() is not None:
        return

    user = User(
        id=_DEV_USER_ID,
        email=_DEV_USER_EMAIL,
        name="Dev User",
        firebase_uid=None,
    )
    org = Organization(
        id=_DEV_ORG_ID,
        name="Dev Org",
        slug="dev-org",
    )
    member = OrgMember(
        org_id=_DEV_ORG_ID,
        user_id=_DEV_USER_ID,
        role="owner",
    )
    session.add_all([user, org, member])
    try:
        await session.commit()
        log.info("auth.dev_bypass.seeded", user_id=str(_DEV_USER_ID), org_id=str(_DEV_ORG_ID))
    except Exception:
        await session.rollback()
        log.debug("auth.dev_bypass.seed_skipped")


async def get_current_user(
    request: Request,
    session: AsyncSession,
) -> CurrentUser:
    """
    FastAPI dependency that resolves the current user.

    Session is injected by deps.py (wraps this with get_session).
    This keeps the seeding within the same session as the request,
    which is critical for the test override to work correctly.
    """
    settings = get_settings()

    if settings.dev_auth_bypass:
        await _seed_dev_user(session)
        return CurrentUser(id=_DEV_USER_ID, email=_DEV_USER_EMAIL)

    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = auth_header.removeprefix("Bearer ").strip()

    try:
        import firebase_admin.auth as fb_auth

        # verify_id_token does blocking network I/O (JWKS fetch) — run it in a
        # worker thread so the event loop is never stalled.
        decoded = await asyncio.to_thread(fb_auth.verify_id_token, token)
        return CurrentUser(
            id=uuid.uuid5(uuid.NAMESPACE_URL, decoded["uid"]),
            email=decoded.get("email", ""),
            firebase_uid=decoded["uid"],
        )
    except Exception as exc:
        log.warning("auth.token_invalid", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
