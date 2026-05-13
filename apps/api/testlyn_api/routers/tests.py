from __future__ import annotations

import uuid

import structlog
from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from testlyn_api.core.permissions import _enforce_perm
from testlyn_api.deps import CurrentUserDep, SessionDep
from testlyn_api.models.project import Project
from testlyn_api.models.test import Test
from testlyn_api.schemas.test import TestCreate, TestOut, TestPatch

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/v1", tags=["tests"])


@router.get("/projects/{project_id}/tests", response_model=list[TestOut])
async def list_tests(
    project_id: uuid.UUID,
    current_user: CurrentUserDep,
    session: SessionDep,
) -> list[TestOut]:
    await _get_project_or_404(project_id, session)
    result = await session.execute(select(Test).where(Test.project_id == project_id))
    return [TestOut.model_validate(t) for t in result.scalars().all()]


@router.post(
    "/projects/{project_id}/tests",
    response_model=TestOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_test(
    project_id: uuid.UUID,
    body: TestCreate,
    current_user: CurrentUserDep,
    session: SessionDep,
) -> TestOut:
    project = await _get_project_or_404(project_id, session)
    await _enforce_perm("write", "test", user_id=current_user.id, org_id=project.org_id, project_id=project_id, session=session)

    script_uri: str | None = None
    if body.script_inline:
        # In production: upload to GCS and set script_uri; for Phase 1 store inline
        script_uri = None  # GCS upload handled by K6Runner on run creation

    test = Test(
        project_id=project_id,
        name=body.name,
        product=body.product,
        script_inline=body.script_inline,
        script_uri=script_uri,
        config=body.config.model_dump(),
        created_by=current_user.id,
    )
    session.add(test)
    await session.commit()
    await session.refresh(test)

    log.info("test.created", test_id=str(test.id), project_id=str(project_id))
    return TestOut.model_validate(test)


@router.get("/tests/{test_id}", response_model=TestOut)
async def get_test(
    test_id: uuid.UUID,
    current_user: CurrentUserDep,
    session: SessionDep,
) -> TestOut:
    test = await _get_test_or_404(test_id, session)
    return TestOut.model_validate(test)


@router.patch("/tests/{test_id}", response_model=TestOut)
async def patch_test(
    test_id: uuid.UUID,
    body: TestPatch,
    current_user: CurrentUserDep,
    session: SessionDep,
) -> TestOut:
    test = await _get_test_or_404(test_id, session)

    if body.name is not None:
        test.name = body.name
    if body.script_inline is not None:
        test.script_inline = body.script_inline
    if body.config is not None:
        test.config = body.config.model_dump()

    await session.commit()
    await session.refresh(test)
    return TestOut.model_validate(test)


async def _get_project_or_404(project_id: uuid.UUID, session: SessionDep) -> Project:
    result = await session.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project


async def _get_test_or_404(test_id: uuid.UUID, session: SessionDep) -> Test:
    result = await session.execute(select(Test).where(Test.id == test_id))
    test = result.scalar_one_or_none()
    if test is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Test not found")
    return test
