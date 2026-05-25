from __future__ import annotations

import uuid

import structlog
from fastapi import APIRouter, HTTPException, status

from testlyn_api.core.permissions import _enforce_perm
from testlyn_api.core.url_safety import UnsafeURL, assert_safe_url
from testlyn_api.deps import CurrentUserDep, SessionDep
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

    scan_id = uuid.uuid4()

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
        status="queued",
        scan_kind=body.scan_kind,
        findings_count=0,
        message="ZAP not available — canned stub response (0 findings)" if is_stub else None,
    )
