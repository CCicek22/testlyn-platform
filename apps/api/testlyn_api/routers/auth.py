from __future__ import annotations

from typing import TYPE_CHECKING

import structlog
from fastapi import APIRouter
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError

from testlyn_api.config import get_settings
from testlyn_api.deps import CurrentUserDep, SessionDep
from testlyn_api.models.org import Organization, OrgMember
from testlyn_api.models.user import User
from testlyn_api.schemas.user import OrgMembershipOut, UserOut

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from testlyn_api.core.auth import CurrentUser

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/v1", tags=["auth"])


async def _ensure_bootstrap_org_membership(
    session: SessionDep,
    user_id,
    email: str | None,
) -> None:
    """Auto-grant owner role on the bootstrap dev org for allowlisted emails.

    Race: two concurrent /v1/me requests for the same user pass the
    ``scalar_one_or_none() is None`` membership check simultaneously, both
    insert, and the second commit blows up on the PK / unique constraint.
    Wrap the insert in a savepoint and treat IntegrityError as "another
    request already inserted" — the desired end-state is reached either way.
    """
    settings = get_settings()
    if not email or email.lower() not in {e.lower() for e in settings.bootstrap_admin_emails}:
        return

    result = await session.execute(
        select(Organization).where(Organization.slug == settings.bootstrap_org_slug)
    )
    org = result.scalar_one_or_none()
    if org is None:
        org = Organization(
            slug=settings.bootstrap_org_slug,
            name=settings.bootstrap_org_name,
        )
        session.add(org)
        try:
            async with session.begin_nested():  # SAVEPOINT
                await session.flush()
        except IntegrityError:
            # Concurrent caller created the org first — the savepoint rolled back
            # only this insert (not the whole transaction); reload and continue.
            result = await session.execute(
                select(Organization).where(Organization.slug == settings.bootstrap_org_slug)
            )
            org = result.scalar_one()

    mem_q = await session.execute(
        select(OrgMember).where(OrgMember.org_id == org.id, OrgMember.user_id == user_id)
    )
    if mem_q.scalar_one_or_none() is None:
        try:
            async with session.begin_nested():  # SAVEPOINT
                session.add(OrgMember(org_id=org.id, user_id=user_id, role="owner"))
        except IntegrityError:
            # Concurrent /v1/me already inserted the membership — fine.
            log.debug(
                "auth.bootstrap.member_race",
                user_id=str(user_id),
                org_id=str(org.id),
            )
    await session.commit()


async def _get_or_create_user(session: AsyncSession, current_user: CurrentUser) -> User:
    """Resolve the DB row for the authenticated principal, creating it on first login.

    Lookup order:
    1. Auth-derived id (``uuid5`` of the firebase uid) — the normal path.
    2. Email — SCIM-provisioned rows carry a ``uuid4`` id but the same unique
       email; adopt that row (and link the firebase uid) instead of blind-
       INSERTing into a unique-email collision that 500s on every login.
    3. INSERT, savepoint-guarded: two concurrent first logins both pass the
       miss checks; the loser's IntegrityError means the row now exists, so
       re-select instead of failing (same pattern as
       ``_ensure_bootstrap_org_membership``).
    """
    result = await session.execute(select(User).where(User.id == current_user.id))
    user = result.scalar_one_or_none()

    if user is None and current_user.email:
        result = await session.execute(
            select(User).where(User.email == current_user.email)
        )
        user = result.scalar_one_or_none()
        if user is not None:
            if current_user.firebase_uid and not user.firebase_uid:
                user.firebase_uid = current_user.firebase_uid
            log.info(
                "auth.me.adopted_provisioned_user",
                user_id=str(user.id),
                derived_id=str(current_user.id),
            )

    if user is None:
        try:
            async with session.begin_nested():  # SAVEPOINT
                session.add(
                    User(
                        id=current_user.id,
                        email=current_user.email,
                        firebase_uid=current_user.firebase_uid,
                    )
                )
                await session.flush()
        except IntegrityError:
            # Concurrent first login already inserted the row — re-select below.
            log.debug("auth.me.first_login_race", user_id=str(current_user.id))
        result = await session.execute(
            select(User).where(
                or_(User.id == current_user.id, User.email == current_user.email)
            )
        )
        user = result.scalars().first()
        if user is None:  # pragma: no cover — insert succeeded or row exists
            raise RuntimeError("user row unresolvable after insert")

    await session.commit()
    return user


@router.get("/me", response_model=UserOut)
async def get_me(current_user: CurrentUserDep, session: SessionDep) -> UserOut:
    user = await _get_or_create_user(session, current_user)

    await _ensure_bootstrap_org_membership(session, user.id, user.email)

    # Memberships are keyed by the DB row id — for SCIM-provisioned users this
    # differs from the auth-derived current_user.id.
    mem_result = await session.execute(
        select(OrgMember).where(OrgMember.user_id == user.id)
    )
    memberships = [
        OrgMembershipOut(org_id=m.org_id, role=m.role) for m in mem_result.scalars().all()
    ]
    return UserOut(
        id=user.id,
        email=user.email,
        name=user.name,
        avatar_url=user.avatar_url,
        created_at=user.created_at,
        memberships=memberships,
    )
