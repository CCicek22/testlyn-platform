from __future__ import annotations

import structlog
from fastapi import APIRouter
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from testlyn_api.config import get_settings
from testlyn_api.deps import CurrentUserDep, SessionDep
from testlyn_api.models.org import Organization, OrgMember
from testlyn_api.schemas.user import OrgMembershipOut, UserOut

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
            await session.flush()
        except IntegrityError:
            # Concurrent caller created the org first — reload and continue.
            await session.rollback()
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


@router.get("/me", response_model=UserOut)
async def get_me(current_user: CurrentUserDep, session: SessionDep) -> UserOut:
    from testlyn_api.models.user import User

    result = await session.execute(select(User).where(User.id == current_user.id))
    user = result.scalar_one_or_none()

    if user is None:
        from testlyn_api.models.user import User as UserModel

        user = UserModel(
            id=current_user.id,
            email=current_user.email,
            firebase_uid=current_user.firebase_uid,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)

    await _ensure_bootstrap_org_membership(session, user.id, user.email)

    mem_result = await session.execute(
        select(OrgMember).where(OrgMember.user_id == current_user.id)
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
