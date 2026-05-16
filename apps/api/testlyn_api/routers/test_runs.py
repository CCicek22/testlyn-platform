from __future__ import annotations

import uuid

import structlog
from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from testlyn_api.core import tasks as tasks_module
from testlyn_api.core.permissions import _enforce_perm
from testlyn_api.deps import AuditDep, CurrentUserDep, SessionDep
from testlyn_api.models.org import Organization
from testlyn_api.models.project import Project
from testlyn_api.models.test import Test
from testlyn_api.models.test_run import TestRun
from testlyn_api.schemas.test_run import RunCreate, RunOut
from testlyn_api.services.quota import QuotaService

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
    audit: AuditDep,
) -> RunOut:
    from testlyn_api.config import get_settings

    test = await _get_test_or_404(test_id, session)
    settings = get_settings()

    # Resolve org via project for quota check + audit
    project = await session.get(Project, test.project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    org = await session.get(Organization, project.org_id)
    if org is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")

    audit.set_org(org.id)
    await _enforce_perm("run", "test", user_id=current_user.id, org_id=org.id, project_id=project.id, session=session)

    # Extract VU/duration from test config (defaults: 1 VU, 60s)
    config: dict = test.config or {}
    vus: int = int(config.get("vus", 1))
    duration_seconds: int = int(config.get("duration_seconds", 60))

    quota = QuotaService(session)
    await quota.check_can_run(org, vus, duration_seconds)

    run = TestRun(
        test_id=test.id,
        product=test.product,
        state="queued",
        region=settings.gcp_region,
        triggered_by=current_user.id,
    )
    session.add(run)
    await session.flush()

    await quota.record_usage(org, run)
    await session.commit()
    await session.refresh(run)

    await audit.write(
        action="test_run.created",
        resource_type="test_run",
        resource_id=run.id,
        after={"test_id": str(test.id), "state": run.state, "product": run.product},
        org_id=org.id,
    )
    await session.commit()

    # Dispatch async — don't await (fire-and-forget via Cloud Tasks or docker).
    # Resolved through the module rather than as a direct binding so tests can
    # monkeypatch tasks.enqueue_run without touching this router.
    await tasks_module.enqueue_run(run.id)

    log.info("run.created", run_id=str(run.id), test_id=str(test_id))
    return RunOut.model_validate(run)


@router.get("/runs", response_model=list[RunOut])
async def list_runs(
    current_user: CurrentUserDep,
    session: SessionDep,
    product: str | None = None,
) -> list[RunOut]:
    """List runs triggered by the current user across all orgs they belong to."""
    from sqlalchemy import and_

    clauses = [TestRun.triggered_by == current_user.id]
    if product is not None:
        clauses.append(TestRun.product == product)
    result = await session.execute(
        select(TestRun).where(and_(*clauses)).order_by(TestRun.id.desc()).limit(200)
    )
    return [RunOut.model_validate(r) for r in result.scalars().all()]


@router.get("/runs/{run_id}", response_model=RunOut)
async def get_run(
    run_id: uuid.UUID,
    current_user: CurrentUserDep,
    session: SessionDep,
) -> RunOut:
    run = await _get_run_or_404(run_id, session)
    # Traverse run → test → project → org to enforce RBAC
    test = await session.get(Test, run.test_id)
    if test is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Test not found")
    project = await session.get(Project, test.project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    await _enforce_perm("read", "test_run", user_id=current_user.id, org_id=project.org_id, project_id=project.id, session=session)
    return RunOut.model_validate(run)


@router.get("/runs/{run_id}/summary")
async def get_run_summary(
    run_id: uuid.UUID,
    current_user: CurrentUserDep,
    session: SessionDep,
) -> dict:
    """Return the run summary JSON stored in GCS (if available)."""
    run = await _get_run_or_404(run_id, session)
    test = await session.get(Test, run.test_id)
    if test is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Test not found")
    project = await session.get(Project, test.project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    await _enforce_perm("read", "test_run", user_id=current_user.id, org_id=project.org_id, project_id=project.id, session=session)
    return {
        "run_id": str(run.id),
        "summary_uri": run.summary_uri,
        "state": run.state,
        "error_reason": run.error_reason,
    }


@router.post("/runs/{run_id}/cancel", status_code=status.HTTP_200_OK, response_model=RunOut)
async def cancel_run(
    run_id: uuid.UUID,
    current_user: CurrentUserDep,
    session: SessionDep,
) -> RunOut:
    """Cancel a queued or running test run."""
    from datetime import UTC, datetime

    run = await _get_run_or_404(run_id, session)
    test = await session.get(Test, run.test_id)
    if test is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Test not found")
    project = await session.get(Project, test.project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    await _enforce_perm("run", "test", user_id=current_user.id, org_id=project.org_id, project_id=project.id, session=session)

    if run.state not in {"queued", "running"}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Run is in state {run.state!r} and cannot be cancelled",
        )

    run.state = "cancelled"
    run.finished_at = datetime.now(tz=UTC)
    await session.commit()
    await session.refresh(run)

    log.info("run.cancelled", run_id=str(run_id), user_id=str(current_user.id))
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
