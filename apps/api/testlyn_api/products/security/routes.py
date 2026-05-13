from __future__ import annotations

import uuid

import structlog
from fastapi import APIRouter, status

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
