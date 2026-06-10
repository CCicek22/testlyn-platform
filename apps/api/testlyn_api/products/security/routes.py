from __future__ import annotations

import uuid

import structlog
from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from testlyn_api.core.permissions import _enforce_perm
from testlyn_api.core.url_safety import UnsafeURL, assert_safe_url
from testlyn_api.deps import CurrentUserDep, SessionDep
from testlyn_api.models.project import Project
from testlyn_api.models.test import Test
from testlyn_api.models.test_run import TestRun
from testlyn_api.products.scan_runs import (
    create_scan_run,
    mark_run_launched,
    public_status,
)
from testlyn_api.products.security.runner import SecurityRunner
from testlyn_api.products.security.schemas import SecurityScanResponse, ZapScanRequest

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/v1/products/security", tags=["security"])

_runner = SecurityRunner()


@router.post(
    "/scan",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=SecurityScanResponse,
)
async def scan(
    body: ZapScanRequest,
    current_user: CurrentUserDep,
    session: SessionDep,
) -> SecurityScanResponse:
    """
    Enqueue a DAST security scan via OWASP ZAP.

    Returns immediately with scan_id. Poll
    GET /v1/products/security/scans/{scan_id} for status and findings.

    Gracefully stubs when ZAP binary is unavailable (returns 0 findings).
    """
    # Verify caller belongs to body.org_id — otherwise an authenticated user
    # could trigger DAST scans (and bill) against another tenant.
    await _enforce_perm(
        "run",
        "test",
        user_id=current_user.id,
        org_id=body.org_id,
        session=session,
    )

    # SSRF guard: ZAP fetches target_url from inside the worker network, so
    # reject private/loopback/link-local/reserved/metadata targets before
    # enqueueing the scan.
    try:
        assert_safe_url(str(body.target_url))
    except UnsafeURL as exc:
        log.warning(
            "security.scan.unsafe_url",
            url=str(body.target_url),
            reason=str(exc),
            org_id=str(body.org_id),
            user_id=str(current_user.id),
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="target URL is not allowed",
        ) from exc

    # Persist a real TestRun BEFORE launch so the engine's
    # /v1/internal/runs/{id}/complete callback finds a row to transition and
    # the GET status endpoint below can serve real state.
    run = await create_scan_run(
        session,
        org_id=body.org_id,
        product="security",
        triggered_by=current_user.id,
    )
    scan_id = run.id

    result = await _runner.launch(
        test_run_id=scan_id,
        script_uri="",
        vus=1,
        duration_seconds=600,
        env={
            "TARGET_URL": str(body.target_url),
            "SCAN_KIND": body.scan_kind,
            "AUTH_RECIPE_ID": str(body.auth_recipe_id) if body.auth_recipe_id else "",
        },
    )
    mark_run_launched(run, result)
    await session.commit()

    log.info(
        "security.scan.enqueued",
        scan_id=str(scan_id),
        org_id=str(body.org_id),
        user_id=str(current_user.id),
        scan_kind=body.scan_kind,
        runner_id=result.runner_id,
    )

    is_stub = result.runner_id.startswith("security-stub-")
    return SecurityScanResponse(
        scan_id=scan_id,
        status=public_status(run),
        scan_kind=body.scan_kind,
        findings_count=0,
        message="ZAP not available — canned stub response (0 findings)" if is_stub else None,
    )


@router.get("/scans/{scan_id}", response_model=SecurityScanResponse)
async def get_scan(
    scan_id: uuid.UUID,
    current_user: CurrentUserDep,
    session: SessionDep,
) -> SecurityScanResponse:
    """Return the current status of a security scan run."""
    run = (
        await session.execute(
            select(TestRun).where(TestRun.id == scan_id, TestRun.product == "security")
        )
    ).scalar_one_or_none()
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scan not found")

    test = await session.get(Test, run.test_id)
    project = await session.get(Project, test.project_id) if test else None
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scan not found")
    await _enforce_perm(
        "read",
        "test_run",
        user_id=current_user.id,
        org_id=project.org_id,
        session=session,
    )

    return SecurityScanResponse(
        scan_id=run.id,
        status=public_status(run),
        findings_count=0,
        message=run.error_reason,
    )
