from __future__ import annotations

import structlog
from fastapi import APIRouter
from sqlalchemy import select

from testlyn_api.deps import CurrentUserDep, SessionDep
from testlyn_api.models.org import OrgMember
from testlyn_api.schemas.user import OrgMembershipOut, UserOut

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/v1", tags=["auth"])


@router.get("/me", response_model=UserOut)
async def get_me(current_user: CurrentUserDep, session: SessionDep) -> UserOut:
    from testlyn_api.models.user import User

    result = await session.execute(select(User).where(User.id == current_user.id))
    user = result.scalar_one_or_none()

    memberships: list[OrgMembershipOut] = []
    if user is not None:
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

    # User not in DB yet (fresh IdP login — create on first call)
    from testlyn_api.models.user import User as UserModel

    new_user = UserModel(
        id=current_user.id,
        email=current_user.email,
        firebase_uid=current_user.firebase_uid,
    )
    session.add(new_user)
    await session.commit()
    await session.refresh(new_user)

    return UserOut(
        id=new_user.id,
        email=new_user.email,
        name=new_user.name,
        avatar_url=new_user.avatar_url,
        created_at=new_user.created_at,
        memberships=[],
    )
