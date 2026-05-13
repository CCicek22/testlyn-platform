from __future__ import annotations

import uuid

from testlyn_api.core.runner import RunnerLaunchResult, RunnerNotAvailable, RunnerStatus


class RumRunner:
    """Runner stub for Real User Monitoring. Phase 4 GA."""

    product: str = "rum"

    async def launch(
        self,
        *,
        test_run_id: uuid.UUID,
        script_uri: str,
        vus: int,
        duration_seconds: int,
        env: dict[str, str],
    ) -> RunnerLaunchResult:
        raise RunnerNotAvailable("Phase 4 GA")

    async def cancel(self, *, runner_id: str) -> None:
        return

    async def status(self, *, runner_id: str) -> RunnerStatus:
        return RunnerStatus(
            state="unavailable",
            started_at=None,
            finished_at=None,
            exit_reason="Phase 4 not available",
        )
