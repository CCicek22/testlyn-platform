from __future__ import annotations

import uuid

import structlog
from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from testlyn_api.core.permissions import _enforce_perm
from testlyn_api.deps import AuditDep, CurrentUserDep, SessionDep
from testlyn_api.models.org import Organization
from testlyn_api.models.project import Project
from testlyn_api.models.test import Test
from testlyn_api.models.test_run import TestRun
from testlyn_api.products.load import bq_queries
from testlyn_api.schemas.test_run import RunCreate, RunOut
from testlyn_api.services.quota import QuotaService
from testlyn_api.services.runs import create_run_for_test

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
    test = await _get_test_or_404(test_id, session)

    # Resolve org via project up front so RBAC + audit run before any mutation.
    project = await session.get(Project, test.project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    org = await session.get(Organization, project.org_id)
    if org is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")

    audit.set_org(org.id)
    await _enforce_perm("run", "test", user_id=current_user.id, org_id=org.id, project_id=project.id, session=session)

    run, org = await create_run_for_test(session, test, triggered_by=current_user.id)

    await audit.write(
        action="test_run.created",
        resource_type="test_run",
        resource_id=run.id,
        after={"test_id": str(test.id), "state": run.state, "product": run.product},
        org_id=org.id,
    )
    await session.commit()

    return RunOut.from_run_and_test(run, test)


@router.get("/runs", response_model=list[RunOut])
async def list_runs(
    current_user: CurrentUserDep,
    session: SessionDep,
    product: str | None = None,
) -> list[RunOut]:
    """List runs triggered by the current user in orgs they currently belong to.

    Membership is rechecked via run → test → project → org → OrgMember so a user
    removed from an org no longer sees runs they triggered while a member.
    """
    from sqlalchemy import and_

    from testlyn_api.models.org import OrgMember

    clauses = [TestRun.triggered_by == current_user.id]
    if product is not None:
        clauses.append(TestRun.product == product)
    result = await session.execute(
        select(TestRun)
        .join(Test, TestRun.test_id == Test.id)
        .join(Project, Test.project_id == Project.id)
        .join(
            OrgMember,
            and_(
                OrgMember.org_id == Project.org_id,
                OrgMember.user_id == current_user.id,
            ),
        )
        .options(joinedload(TestRun.test))
        .where(and_(*clauses))
        .order_by(TestRun.created_at.desc())
        .limit(200)
    )
    return [RunOut.from_run_and_test(r, r.test) for r in result.unique().scalars().all()]


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
    return RunOut.from_run_and_test(run, test)


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


@router.get("/runs/{run_id}/samples")
async def get_run_samples(
    run_id: uuid.UUID,
    current_user: CurrentUserDep,
    session: SessionDep,
) -> list[dict]:
    """Return the persisted per-second metrics for a run, oldest-first.

    Element shape matches the live SSE ``sample`` payload
    (``ts``, ``p95_duration_ms``, ``error_rate``, ``vus``) so the frontend can
    reuse the same chart for completed runs. Server-side authorized BQ read —
    the browser never gets BQ creds (CLAUDE.md §7). Empty array if no samples.
    """
    from testlyn_api.config import get_settings

    run = await _get_run_or_404(run_id, session)
    test = await session.get(Test, run.test_id)
    if test is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Test not found")
    project = await session.get(Project, test.project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    await _enforce_perm("read", "test_run", user_id=current_user.id, org_id=project.org_id, project_id=project.id, session=session)

    settings = get_settings()
    return await bq_queries.fetch_run_samples(
        run_id=run_id,
        project=settings.gcp_project_id,
        dataset=settings.gcp_bq_dataset,
    )


@router.post("/runs/{run_id}/cancel", status_code=status.HTTP_200_OK, response_model=RunOut)
async def cancel_run(
    run_id: uuid.UUID,
    current_user: CurrentUserDep,
    session: SessionDep,
) -> RunOut:
    """Cancel a queued or running test run.

    Quota is only released for runs that never launched (still queued, no
    runner_id) — a run that reached "running" consumed engine resources and
    keeps its quota charge.
    """
    from datetime import UTC, datetime

    # FOR UPDATE: serialize against a concurrent complete/start so we can't
    # overwrite a concurrently-committed terminal state with "cancelled".
    run = await _get_run_or_404(run_id, session, for_update=True)
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

    # Captured before mutation: quota is released only for runs that never
    # launched. Releasing for running runs let users burn engine time for free
    # by cancelling just before completion.
    never_launched = run.state == "queued" and run.runner_id is None

    # Stop the underlying runner so the Cloud Run Job actually halts instead of
    # continuing to stream to BQ and burn quota. runner_id is None while still
    # queued (never launched) — nothing to stop in that case.
    if run.runner_id is not None:
        from testlyn_api.core.runner_registry import RUNNERS

        runner = RUNNERS.get(run.product)
        if runner is not None:
            try:
                await runner.cancel(runner_id=run.runner_id)
            except Exception as exc:  # noqa: BLE001 — best-effort stop; still mark cancelled
                log.error(
                    "run.cancel_runner_failed",
                    run_id=str(run_id),
                    runner_id=run.runner_id,
                    error=str(exc),
                )

    run.state = "cancelled"
    run.finished_at = datetime.now(tz=UTC)

    # Reverse the usage recorded at create_run time ONLY when the run never
    # launched — it consumed nothing. Idempotent.
    if never_launched:
        org = await session.get(Organization, project.org_id)
        if org is not None:
            await QuotaService(session).release_usage(org, run)

    await session.commit()
    await session.refresh(run)

    log.info("run.cancelled", run_id=str(run_id), user_id=str(current_user.id))
    return RunOut.from_run_and_test(run, test)


async def _get_test_or_404(test_id: uuid.UUID, session: SessionDep) -> Test:
    result = await session.execute(select(Test).where(Test.id == test_id))
    test = result.scalar_one_or_none()
    if test is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Test not found")
    return test


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
