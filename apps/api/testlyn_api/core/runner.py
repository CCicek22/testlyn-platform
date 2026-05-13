from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable
from uuid import UUID

from pydantic import BaseModel


class RunnerLaunchResult(BaseModel):
    runner_id: str  # e.g. Cloud Run Job execution name
    started_at: datetime
    region: str


class RunnerStatus(BaseModel):
    state: str  # queued | running | completed | failed | cancelled
    started_at: datetime | None
    finished_at: datetime | None
    exit_reason: str | None


@runtime_checkable
class Runner(Protocol):
    product: str  # 'load', 'functional', ...

    async def launch(
        self,
        *,
        test_run_id: UUID,
        script_uri: str,
        vus: int,
        duration_seconds: int,
        env: dict[str, str],
    ) -> RunnerLaunchResult: ...

    async def cancel(self, *, runner_id: str) -> None: ...

    async def status(self, *, runner_id: str) -> RunnerStatus: ...
