from __future__ import annotations

import uuid

import structlog
from fastapi import APIRouter, HTTPException, status

from testlyn_api.core.permissions import _enforce_perm
from testlyn_api.core.url_safety import UnsafeURL, assert_safe_url
from testlyn_api.deps import CurrentUserDep, SessionDep
from testlyn_api.products.api_contract.runner import ApiContractRunner
from testlyn_api.products.api_contract.schemas import (
    ContractScanRequest,
    ContractScanResponse,
)

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/v1/products/api-contract", tags=["api_contract"])

_runner = ApiContractRunner()


@router.post(
    "/scan",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=ContractScanResponse,
)
async def scan(
    body: ContractScanRequest,
    current_user: CurrentUserDep,
    session: SessionDep,
) -> ContractScanResponse:
    """
    Enqueue an API contract drift scan via Schemathesis.

    Validates the running API at target_url against the OpenAPI spec at
    openapi_url. Returns immediately; check GET /v1/products/api-contract/scans/{scan_id}
    for results.

    Gracefully stubs when schemathesis binary is unavailable.
    """
    # Verify caller belongs to body.org_id — otherwise an authenticated user
    # could trigger contract scans against another tenant.
    await _enforce_perm(
        "run",
        "test",
        user_id=current_user.id,
        org_id=body.org_id,
        session=session,
    )

    # SSRF guard: both the spec URL and the API-under-test URL are fetched by
    # Schemathesis inside the worker, so reject private/loopback/link-local/
    # reserved/metadata targets before enqueueing the job.
    for url in (body.openapi_url, body.target_url):
        try:
            assert_safe_url(str(url))
        except UnsafeURL as exc:
            log.warning(
                "api_contract.scan.unsafe_url",
                url=str(url),
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
        duration_seconds=300,
        env={
            "OPENAPI_URL": str(body.openapi_url),
            "TARGET_URL": str(body.target_url),
            "MAX_EXAMPLES": str(body.hypothesis_settings.max_examples),
            "DERANDOMIZE": str(body.hypothesis_settings.derandomize).lower(),
        },
    )

    log.info(
        "api_contract.scan.enqueued",
        scan_id=str(scan_id),
        org_id=str(body.org_id),
        user_id=str(current_user.id),
        runner_id=result.runner_id,
    )

    is_stub = result.runner_id.startswith("contract-stub-")
    return ContractScanResponse(
        scan_id=scan_id,
        status="queued",
        drift_count=0,
        message="schemathesis not available — canned stub response" if is_stub else None,
    )
