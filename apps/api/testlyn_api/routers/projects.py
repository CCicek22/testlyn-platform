from __future__ import annotations

import re
import uuid

import structlog
from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from testlyn_api.deps import CurrentUserDep, SessionDep
from testlyn_api.models.org import Organization, OrgMember
from testlyn_api.models.project import Project
from testlyn_api.schemas.project import ProjectCreate, ProjectOut

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/v1/orgs", tags=["projects"])


def _slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


@router.post("/{org_id}/projects", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
async def create_project(
    org_id: uuid.UUID,
    body: ProjectCreate,
    current_user: CurrentUserDep,
    session: SessionDep,
) -> ProjectOut:
    await _assert_org_member(org_id, current_user.id, session)

    project = Project(org_id=org_id, name=body.name, slug=_slugify(body.name))
    session.add(project)
    await session.commit()
    await session.refresh(project)

    log.info("project.created", project_id=str(project.id), org_id=str(org_id))
    return ProjectOut.model_validate(project)


async def _assert_org_member(org_id: uuid.UUID, user_id: uuid.UUID, session: SessionDep) -> None:
    result = await session.execute(select(Organization).where(Organization.id == org_id))
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")

    result2 = await session.execute(
        select(OrgMember).where(OrgMember.org_id == org_id, OrgMember.user_id == user_id)
    )
    if result2.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not a member")
