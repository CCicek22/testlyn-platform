from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncGenerator
from typing import Any

import structlog
from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from testlyn_api.core.sse import heartbeat_generator
from testlyn_api.deps import CurrentUserDep, SessionDep
from testlyn_api.models.test_run import TestRun
from testlyn_api.products.load import bq_queries

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/v1", tags=["stream"])

_TERMINAL_STATES = {"completed", "failed", "cancelled"}


@router.get("/runs/{run_id}/stream")
async def stream_run(
    run_id: uuid.UUID,
    request: Request,
    current_user: CurrentUserDep,
    session: SessionDep,
) -> StreamingResponse:
    result = await session.execute(select(TestRun).where(TestRun.id == run_id))
    run = result.scalar_one_or_none()
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")

    from testlyn_api.config import get_settings

    settings = get_settings()

    max_ticks = settings.sse_max_ticks  # 0 = unlimited

    async def _source() -> AsyncGenerator[dict[str, Any]]:
        tick = 0
        while True:
            if max_ticks > 0 and tick >= max_ticks:
                return

            if await request.is_disconnected():
                return

            # Re-fetch run state each tick
            async with session.begin_nested():
                fresh = await session.get(TestRun, run_id)
            if fresh is None:
                return

            # Query BQ for latest 1s window
            try:
                metrics = await bq_queries.stream_run_metrics(
                    run_id=run_id,
                    project=settings.gcp_project_id,
                    dataset=settings.gcp_bq_dataset,
                )
                if metrics:
                    yield {
                        "run_id": str(run_id),
                        "state": fresh.state,
                        "metrics": metrics,
                    }
            except Exception as exc:
                log.warning("stream.bq_error", run_id=str(run_id), error=str(exc))

            if fresh.state in _TERMINAL_STATES:
                return

            tick += 1
            await asyncio.sleep(1)

    async def _sse_body() -> AsyncGenerator[str]:
        async for chunk in heartbeat_generator(_source(), interval=settings.sse_heartbeat_interval):
            yield chunk

    return StreamingResponse(
        _sse_body(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
