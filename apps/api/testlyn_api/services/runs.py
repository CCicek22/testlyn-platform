from __future__ import annotations

import uuid
from datetime import UTC, datetime

import structlog
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from testlyn_api.core import tasks as tasks_module
from testlyn_api.models.org import Organization
from testlyn_api.models.project import Project
from testlyn_api.models.test import Test
from testlyn_api.models.test_run import TestRun
from testlyn_api.services.quota import QuotaService

log = structlog.get_logger(__name__)


async def create_run_for_test(
    session: AsyncSession,
    test: Test,
    *,
    triggered_by: uuid.UUID | None,
) -> tuple[TestRun, Organization]:
    """Create + enqueue a TestRun for ``test``, enforcing quota and recording usage.

    Shared core used by both the authenticated user endpoint
    (``routers/test_runs.create_run``) and the internal scheduler-triggered
    endpoint (``routers/internal.create_internal_run``). Org is resolved via
    test → project → org so callers without a user context still scope quota +
    usage correctly.

    Audit logging stays in the calling router (the user path has an injected
    ``AuditDep``; the internal path writes its own audit entry). Returns the
    persisted run plus its owning org so callers can finalize.
    """
    from testlyn_api.config import get_settings

    settings = get_settings()

    project = await session.get(Project, test.project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    org = await session.get(Organization, project.org_id)
    if org is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found"
        )

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
        triggered_by=triggered_by,
    )
    session.add(run)
    await session.flush()

    await quota.record_usage(org, run)
    await session.commit()
    await session.refresh(run)

    # Dispatch async — don't await (fire-and-forget via Cloud Tasks or docker).
    # Resolved through the module so tests can monkeypatch tasks.enqueue_run.
    try:
        await tasks_module.enqueue_run(run.id)
    except Exception as exc:
        # Enqueue failed (Cloud Tasks outage, queue misconfig). Without this
        # guard the request 500s with the run stuck "queued" and the org's
        # quota silently consumed. Mark it failed, give the quota back, and
        # surface a clean 502.
        log.error("run.enqueue_failed", run_id=str(run.id), error=str(exc))
        run.state = "failed"
        run.error_reason = f"enqueue failed: {exc}"
        run.finished_at = datetime.now(tz=UTC)
        await quota.release_usage(org, run)
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to enqueue test run",
        ) from exc

    log.info("run.created", run_id=str(run.id), test_id=str(test.id))
    return run, org
