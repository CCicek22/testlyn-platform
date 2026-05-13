from __future__ import annotations

import re
import uuid

import structlog
from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from testlyn_api.deps import CurrentUserDep, SessionDep
from testlyn_api.models.org import Organization, OrgMember
from testlyn_api.schemas.org import InviteCreate, InviteOut, OrgCreate, OrgOut

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/v1/orgs", tags=["orgs"])


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return f"{slug}-{uuid.uuid4().hex[:6]}"


@router.post("", response_model=OrgOut, status_code=status.HTTP_201_CREATED)
async def create_org(
    body: OrgCreate,
    current_user: CurrentUserDep,
    session: SessionDep,
) -> OrgOut:
    org = Organization(name=body.name, slug=_slugify(body.name))
    session.add(org)
    await session.flush()

    member = OrgMember(org_id=org.id, user_id=current_user.id, role="owner")
    session.add(member)
    await session.commit()
    await session.refresh(org)

    log.info("org.created", org_id=str(org.id), user_id=str(current_user.id))
    return OrgOut.model_validate(org)


@router.get("/{org_id}", response_model=OrgOut)
async def get_org(
    org_id: uuid.UUID,
    current_user: CurrentUserDep,
    session: SessionDep,
) -> OrgOut:
    org = await _get_org_or_404(org_id, session)
    await _assert_member(org_id, current_user.id, session)
    return OrgOut.model_validate(org)


@router.post("/{org_id}/invites", response_model=InviteOut, status_code=status.HTTP_201_CREATED)
async def create_invite(
    org_id: uuid.UUID,
    body: InviteCreate,
    current_user: CurrentUserDep,
    session: SessionDep,
) -> InviteOut:
    await _get_org_or_404(org_id, session)
    await _assert_member(org_id, current_user.id, session)
    # Phase 1: stub — write nothing, no email sent
    log.info("org.invite_stub", org_id=str(org_id), email=body.email, role=body.role)
    return InviteOut(org_id=org_id, email=body.email, role=body.role)


@router.get("/{org_id}/projects")
async def list_projects(
    org_id: uuid.UUID,
    current_user: CurrentUserDep,
    session: SessionDep,
) -> list[dict]:
    from testlyn_api.models.project import Project
    from testlyn_api.schemas.project import ProjectOut

    await _get_org_or_404(org_id, session)
    await _assert_member(org_id, current_user.id, session)

    result = await session.execute(select(Project).where(Project.org_id == org_id))
    return [ProjectOut.model_validate(p).model_dump() for p in result.scalars().all()]


async def _get_org_or_404(org_id: uuid.UUID, session: SessionDep) -> Organization:
    result = await session.execute(select(Organization).where(Organization.id == org_id))
    org = result.scalar_one_or_none()
    if org is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
    return org


async def _assert_member(org_id: uuid.UUID, user_id: uuid.UUID, session: SessionDep) -> None:
    result = await session.execute(
        select(OrgMember).where(OrgMember.org_id == org_id, OrgMember.user_id == user_id)
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not a member")
