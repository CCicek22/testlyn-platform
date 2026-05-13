from __future__ import annotations

import uuid

from testlyn_api.core.runner import RunnerLaunchResult, RunnerStatus


class CicdInsightsRunner:
    """Runner stub for CI/CD Insights. Phase 4 GA."""

    product: str = "cicd_insights"

    async def launch(
        self,
        *,
        test_run_id: uuid.UUID,
        script_uri: str,
        vus: int,
        duration_seconds: int,
        env: dict[str, str],
    ) -> RunnerLaunchResult:
        raise NotImplementedError("Coming soon — Phase 4 GA")

    async def cancel(self, *, runner_id: str) -> None:
        raise NotImplementedError("Coming soon — Phase 4 GA")

    async def status(self, *, runner_id: str) -> RunnerStatus:
        raise NotImplementedError("Coming soon — Phase 4 GA")
