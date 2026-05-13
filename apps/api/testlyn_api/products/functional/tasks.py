"""Cloud Tasks handler stub for the testlyn-runs-functional queue.

TODO: wire up to the Cloud Tasks push endpoint once the functional queue
is provisioned via Terraform (infra/terraform/modules/cloud_tasks).
"""

from __future__ import annotations

import uuid

import structlog
from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse

from testlyn_api.products.functional.reports import build_functional_report

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/v1/internal/functional", tags=["functional-internal"])


@router.post("/tasks/run-complete", status_code=status.HTTP_204_NO_CONTENT)
async def handle_run_complete(request: Request) -> JSONResponse:
    """Invoked by Cloud Tasks when a Playwright runner job finishes.

    Body: {"run_id": str, "status": "completed"|"failed", "exit_code": int}
    """
    body: dict = await request.json()
    run_id_raw = body.get("run_id", "")
    status_str = body.get("status", "unknown")

    try:
        run_id = uuid.UUID(run_id_raw)
    except ValueError:
        log.error("functional.tasks.invalid_run_id", run_id=run_id_raw)
        return JSONResponse({"error": "invalid run_id"}, status_code=400)

    log.info("functional.tasks.run_complete", run_id=str(run_id), status=status_str)

    if status_str == "completed":
        # TODO: update DB run record, trigger report builder
        await build_functional_report(run_id)

    return JSONResponse(None, status_code=204)
