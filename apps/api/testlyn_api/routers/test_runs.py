from __future__ import annotations

import uuid

import structlog
from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from testlyn_api.core.tasks import enqueue_run
from testlyn_api.deps import CurrentUserDep, SessionDep
from testlyn_api.models.test import Test
from testlyn_api.models.test_run import TestRun
from testlyn_api.schemas.test_run import RunCreate, RunOut

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/v1", tags=["test-runs"])


@router.post(
    "/tests/{test_id}/runs",
    response_model=RunOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_run(
    test_id: uuid.UUID,
    body: RunCreate,
    current_user: CurrentUserDep,
    session: SessionDep,
) -> RunOut:
    from testlyn_api.config import get_settings

    test = await _get_test_or_404(test_id, session)
    settings = get_settings()

    run = TestRun(
        test_id=test.id,
        product=test.product,
        state="queued",
        region=settings.gcp_region,
        triggered_by=current_user.id,
    )
    session.add(run)
    await session.commit()
    await session.refresh(run)

    # Dispatch async — don't await (fire-and-forget via Cloud Tasks or docker)
    await enqueue_run(run.id)

    log.info("run.created", run_id=str(run.id), test_id=str(test_id))
    return RunOut.model_validate(run)


@router.get("/runs/{run_id}", response_model=RunOut)
async def get_run(
    run_id: uuid.UUID,
    current_user: CurrentUserDep,
    session: SessionDep,
) -> RunOut:
    run = await _get_run_or_404(run_id, session)
    return RunOut.model_validate(run)


async def _get_test_or_404(test_id: uuid.UUID, session: SessionDep) -> Test:
    result = await session.execute(select(Test).where(Test.id == test_id))
    test = result.scalar_one_or_none()
    if test is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Test not found")
    return test


async def _get_run_or_404(run_id: uuid.UUID, session: SessionDep) -> TestRun:
    result = await session.execute(select(TestRun).where(TestRun.id == run_id))
    run = result.scalar_one_or_none()
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    return run
