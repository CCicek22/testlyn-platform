from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime

import structlog
from fastapi import APIRouter, Header, HTTPException, Request, status
from sqlalchemy import select

from testlyn_api.core.runner_registry import RUNNERS
from testlyn_api.deps import AuditDep, SessionDep
from testlyn_api.models.project import Project
from testlyn_api.models.test import Test
from testlyn_api.models.test_run import TestRun
from testlyn_api.schemas.test_run import ReportReadyPayload, RunCompletePayload, RunOut

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/v1/internal", tags=["internal"])

# In production (run_mode=cloud), callers must supply the X-Internal-Token header
# matching settings.internal_token. In docker/dev mode the check is skipped so
# the Cloud Tasks emulator (which doesn't add the header) can call freely.


def _verify_internal_token(x_internal_token: str | None) -> None:
    from testlyn_api.config import get_settings

    settings = get_settings()
    if settings.run_mode == "docker":
        return  # dev bypass — no header required
    expected = getattr(settings, "internal_token", None)
    if not expected:
        # Cloud mode requires a configured shared secret. Refusing rather than
        # allowing matches our "secure-by-default" posture: an unset secret in
        # production must be loud, not silently bypass authentication.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Internal token not configured",
        )
    if not x_internal_token or not secrets.compare_digest(x_internal_token, expected):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid internal token")


@router.post(
    "/tests/{test_id}/runs",
    response_model=RunOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_internal_run(
    test_id: uuid.UUID,
    session: SessionDep,
    audit: AuditDep,
    x_internal_token: str | None = Header(default=None),
) -> RunOut:
    """Create + enqueue a run for ``test_id`` without a user context.

    Authorized by the shared X-Internal-Token (same gate as the other
    ``/v1/internal/*`` endpoints). Used by Cloud Scheduler triggers — the
    user-facing ``POST /v1/tests/{id}/runs`` requires a Firebase bearer + RBAC
    which a Scheduler HTTP target can't supply. Org/quota/usage are resolved
    from the test row inside ``create_run_for_test``.
    """
    from testlyn_api.services.runs import create_run_for_test

    _verify_internal_token(x_internal_token)

    test_result = await session.execute(select(Test).where(Test.id == test_id))
    test = test_result.scalar_one_or_none()
    if test is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Test not found")

    run, org = await create_run_for_test(session, test, triggered_by=None)

    audit.set_org(org.id)
    await audit.write(
        action="test_run.created",
        resource_type="test_run",
        resource_id=run.id,
        after={
            "test_id": str(test.id),
            "state": run.state,
            "product": run.product,
            "trigger": "scheduler",
        },
        org_id=org.id,
    )
    await session.commit()

    log.info("run.created_internal", run_id=str(run.id), test_id=str(test_id))
    return RunOut.from_run_and_test(run, test)


@router.post("/runs/{run_id}/start", response_model=RunOut)
async def start_run(
    run_id: uuid.UUID,
    request: Request,
    session: SessionDep,
    x_internal_token: str | None = Header(default=None),
) -> RunOut:
    _verify_internal_token(x_internal_token)
    # Row lock: Cloud Tasks delivers at-least-once, so two start requests for
    # the same run can race. FOR UPDATE serializes them; the state check below
    # runs after the lock is acquired, so the loser sees the winner's state.
    run = await _get_run_or_404(run_id, session, for_update=True)

    if run.state != "queued":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Run is in state {run.state!r}, expected 'queued'",
        )

    # Fetch the parent test to get script + config
    test_result = await session.execute(select(Test).where(Test.id == run.test_id))
    test = test_result.scalar_one_or_none()
    if test is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Test not found")

    runner = RUNNERS.get(run.product)
    if runner is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"No runner registered for product {run.product!r}",
        )

    config = test.config or {}
    script_uri = test.script_uri or ""

    # Resolve org id (run → test → project → org) so the engine entrypoint,
    # which hard-requires ORG_ID, can scope its GCS paths and k6 tags.
    project_result = await session.execute(
        select(Project).where(Project.id == test.project_id)
    )
    project = project_result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    org_id = str(project.org_id)

    # Commit the transitional "running" state BEFORE launching the runner: a
    # duplicate Cloud Tasks delivery arriving mid-launch then sees "running"
    # and 409s instead of double-launching the engine job. Reverted to
    # "failed" below if the launch errors.
    run.state = "running"
    await session.commit()

    try:
        result = await runner.launch(
            test_run_id=run.id,
            script_uri=script_uri,
            vus=config.get("vus", 1),
            duration_seconds=config.get("duration_seconds", 30),
            env={
                "RUN_ID": str(run.id),
                "ORG_ID": org_id,
                "SCRIPT_INLINE": test.script_inline or "",
            },
        )
        run.runner_id = result.runner_id
        run.started_at = result.started_at
        run.region = result.region
    except Exception as exc:
        log.error("run.start_failed", run_id=str(run_id), error=str(exc))
        run.state = "failed"
        run.error_reason = str(exc)
        run.finished_at = datetime.now(tz=UTC)
        # Launch never happened — reverse the usage recorded at create_run time
        # so a failed launch doesn't inflate the org's monthly quota.
        from testlyn_api.models.org import Organization
        from testlyn_api.services.quota import QuotaService

        org = await session.get(Organization, project.org_id)
        if org is not None:
            await QuotaService(session).release_usage(org, run)

    await session.commit()
    await session.refresh(run)

    log.info("run.started", run_id=str(run_id), state=run.state)
    return RunOut.from_run_and_test(run, test)


@router.post("/runs/{run_id}/complete", response_model=RunOut)
async def complete_run(
    run_id: uuid.UUID,
    body: RunCompletePayload,
    session: SessionDep,
    x_internal_token: str | None = Header(default=None),
) -> RunOut:
    _verify_internal_token(x_internal_token)
    # FOR UPDATE: serialize against concurrent start/cancel/complete so the
    # state check below reflects any concurrently-committed transition.
    run = await _get_run_or_404(run_id, session, for_update=True)

    if run.state not in {"running", "queued"}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Run is in state {run.state!r}, cannot complete",
        )

    test_result = await session.execute(select(Test).where(Test.id == run.test_id))
    test = test_result.scalar_one_or_none()
    if test is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Test not found")

    run.finished_at = datetime.now(tz=UTC)
    run.summary_uri = body.summary_uri
    run.error_reason = body.error_reason

    if body.exit_code == 0:
        run.state = "completed"
    else:
        run.state = "failed"
        if not run.error_reason:
            run.error_reason = f"k6 exited with code {body.exit_code}"

    await session.commit()
    await session.refresh(run)

    log.info("run.completed", run_id=str(run_id), state=run.state)
    return RunOut.from_run_and_test(run, test)


@router.post("/runs/{run_id}/report-ready", response_model=RunOut)
async def report_ready(
    run_id: uuid.UUID,
    body: ReportReadyPayload,
    session: SessionDep,
    x_internal_token: str | None = Header(default=None),
) -> RunOut:
    """Record the PDF report URI for a run.

    Called by the report-builder once it has uploaded the rendered PDF to GCS.
    """
    _verify_internal_token(x_internal_token)
    run = await _get_run_or_404(run_id, session)

    test_result = await session.execute(select(Test).where(Test.id == run.test_id))
    test = test_result.scalar_one_or_none()
    if test is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Test not found")

    run.report_uri = body.report_gcs_uri

    await session.commit()
    await session.refresh(run)

    log.info("run.report_ready", run_id=str(run_id), report_uri=run.report_uri)
    return RunOut.from_run_and_test(run, test)


async def _get_run_or_404(
    run_id: uuid.UUID, session: SessionDep, *, for_update: bool = False
) -> TestRun:
    stmt = select(TestRun).where(TestRun.id == run_id)
    if for_update:
        # Row lock for state transitions (no-op on SQLite test backend).
        stmt = stmt.with_for_update()
    result = await session.execute(stmt)
    run = result.scalar_one_or_none()
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    return run
