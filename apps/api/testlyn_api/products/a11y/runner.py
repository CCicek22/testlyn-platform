from __future__ import annotations

import uuid
from datetime import UTC, datetime

import structlog

from testlyn_api.config import get_settings
from testlyn_api.core.runner import RunnerLaunchResult, RunnerStatus
from testlyn_api.core.runner_state import execution_to_status

log = structlog.get_logger(__name__)


class A11yRunner:
    """
    Runner implementation for WCAG 2.2 accessibility audits via Playwright + axe-core.

    Cloud mode: dispatches a Cloud Run Job (testlyn-engine-a11y) via the
    testlyn-runs-a11y Cloud Tasks queue.
    Docker mode (RUN_MODE=docker): logs and returns a stub result — the
    engine-a11y container requires a real browser runtime.

    Conforms to the Runner Protocol defined in core/runner.py.
    product = 'a11y' is the discriminator used by runner_dispatcher.
    """

    product: str = "a11y"

    async def launch(
        self,
        *,
        test_run_id: uuid.UUID,
        script_uri: str,
        vus: int,
        duration_seconds: int,
        env: dict[str, str],
    ) -> RunnerLaunchResult:
        settings = get_settings()

        if settings.run_mode == "docker":
            log.info(
                "a11y_runner.docker_stub",
                run_id=str(test_run_id),
                note="engine-a11y needs real browser; returning stub result",
            )
            return RunnerLaunchResult(
                runner_id=f"a11y-docker-stub-{test_run_id}",
                started_at=datetime.now(tz=UTC),
                region="local",
            )

        return await self._launch_cloud(
            test_run_id=test_run_id,
            script_uri=script_uri,
            env=env,
        )

    async def cancel(self, *, runner_id: str) -> None:
        settings = get_settings()
        if settings.run_mode == "docker":
            log.info("a11y_runner.cancel_noop_docker", runner_id=runner_id)
            return

        from google.cloud import run_v2

        client = run_v2.JobsAsyncClient()
        await client.cancel_execution(name=runner_id)
        log.info("a11y_runner.cancelled", runner_id=runner_id)

    async def status(self, *, runner_id: str) -> RunnerStatus:
        settings = get_settings()
        if settings.run_mode == "docker":
            return RunnerStatus(
                state="running",
                started_at=None,
                finished_at=None,
                exit_reason=None,
            )

        from google.cloud import run_v2

        client = run_v2.JobsAsyncClient()
        execution = await client.get_execution(name=runner_id)

        return execution_to_status(execution)

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    async def _launch_cloud(
        self,
        *,
        test_run_id: uuid.UUID,
        script_uri: str,
        env: dict[str, str],
    ) -> RunnerLaunchResult:
        settings = get_settings()

        from google.cloud import run_v2

        client = run_v2.JobsAsyncClient()
        job_name = (
            f"projects/{settings.gcp_project_id}"
            f"/locations/{settings.gcp_region}"
            f"/jobs/testlyn-engine-a11y"
        )

        overrides = run_v2.RunJobRequest.Overrides(
            container_overrides=[
                run_v2.RunJobRequest.Overrides.ContainerOverride(
                    env=[
                        run_v2.EnvVar(name=k, value=v)
                        for k, v in {
                            "RUN_ID": str(test_run_id),
                            "AUDIT_CONFIG_URI": script_uri,
                            "BQ_DATASET": settings.gcp_bq_dataset,
                            "GCP_PROJECT": settings.gcp_project_id,
                            "CALLBACK_URL": (
                                f"{settings.api_base_url}"
                                f"/v1/internal/runs/{test_run_id}/complete"
                            ),
                            # Shared secret the entrypoint echoes back on its
                            # callback so the API's X-Internal-Token gate accepts
                            # it (parity with the load + security engines).
                            "INTERNAL_TOKEN": settings.internal_token,
                            **env,
                        }.items()
                    ]
                )
            ]
        )

        response = await client.run_job(
            request=run_v2.RunJobRequest(name=job_name, overrides=overrides),
        )
        op_meta = response.metadata
        execution_name = (
            op_meta.name if op_meta else f"{job_name}/executions/{test_run_id}"
        )

        log.info(
            "a11y_runner.launched_cloud",
            run_id=str(test_run_id),
            execution=execution_name,
        )
        return RunnerLaunchResult(
            runner_id=execution_name,
            started_at=datetime.now(tz=UTC),
            region=settings.gcp_region,
        )
