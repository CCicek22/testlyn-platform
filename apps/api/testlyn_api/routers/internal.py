from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime

import structlog
from fastapi import APIRouter, Header, HTTPException, Request, status
from sqlalchemy import select

from testlyn_api.core.runner_registry import RUNNERS
from testlyn_api.deps import SessionDep
from testlyn_api.models.test import Test
from testlyn_api.models.test_run import TestRun
from testlyn_api.schemas.test_run import RunCompletePayload, RunOut

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
        return  # not configured — allow (backwards compat with existing deploys)
    if not x_internal_token or not secrets.compare_digest(x_internal_token, expected):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid internal token")


@router.post("/runs/{run_id}/start", response_model=RunOut)
async def start_run(
    run_id: uuid.UUID,
    request: Request,
    session: SessionDep,
    x_internal_token: str | None = Header(default=None),
) -> RunOut:
    _verify_internal_token(x_internal_token)
    run = await _get_run_or_404(run_id, session)

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

    try:
        result = await runner.launch(
            test_run_id=run.id,
            script_uri=script_uri,
            vus=config.get("vus", 1),
            duration_seconds=config.get("duration_seconds", 30),
            env={
                "RUN_ID": str(run.id),
                "SCRIPT_INLINE": test.script_inline or "",
            },
        )
        run.state = "running"
        run.runner_id = result.runner_id
        run.started_at = result.started_at
        run.region = result.region
    except Exception as exc:
        log.error("run.start_failed", run_id=str(run_id), error=str(exc))
        run.state = "failed"
        run.error_reason = str(exc)
        run.finished_at = datetime.now(tz=UTC)

    await session.commit()
    await session.refresh(run)

    log.info("run.started", run_id=str(run_id), state=run.state)
    return RunOut.model_validate(run)


@router.post("/runs/{run_id}/complete", response_model=RunOut)
async def complete_run(
    run_id: uuid.UUID,
    body: RunCompletePayload,
    session: SessionDep,
    x_internal_token: str | None = Header(default=None),
) -> RunOut:
    _verify_internal_token(x_internal_token)
    run = await _get_run_or_404(run_id, session)

    if run.state not in {"running", "queued"}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Run is in state {run.state!r}, cannot complete",
        )

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
    return RunOut.model_validate(run)


async def _get_run_or_404(run_id: uuid.UUID, session: SessionDep) -> TestRun:
    result = await session.execute(select(TestRun).where(TestRun.id == run_id))
    run = result.scalar_one_or_none()
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    return run
