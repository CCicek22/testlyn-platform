from __future__ import annotations

import uuid
from datetime import UTC, datetime

import structlog

from testlyn_api.config import get_settings
from testlyn_api.core.runner import RunnerLaunchResult, RunnerStatus
from testlyn_api.core.runner_state import execution_to_status

log = structlog.get_logger(__name__)


class SyntheticDataRunner:
    """
    Runner stub for synthetic data generation.

    Invokes a Cloud Run Job that:
    1. Fetches the Postgres DSN from Secret Manager.
    2. Reflects the schema via SQLAlchemy.
    3. Generates Faker-based rows, applying GDPR masking rules.
    4. Writes a SQL dump to GCS (output_mode=gcs) or inserts directly.

    On missing creds / docker mode: returns a stub result.
    Conforms to the Runner Protocol (core/runner.py).
    """

    product: str = "synthetic_data"

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
                "synthetic_data_runner.docker_stub",
                run_id=str(test_run_id),
                note="returning stub; real runner needs Secret Manager + Cloud Run",
            )
            return RunnerLaunchResult(
                runner_id=f"synth-docker-stub-{test_run_id}",
                started_at=datetime.now(tz=UTC),
                region="local",
            )

        return await self._launch_cloud(test_run_id=test_run_id, env=env)

    async def cancel(self, *, runner_id: str) -> None:
        settings = get_settings()
        if settings.run_mode == "docker":
            log.info("synthetic_data_runner.cancel_noop_docker", runner_id=runner_id)
            return

        from google.cloud import run_v2

        client = run_v2.JobsAsyncClient()
        await client.cancel_execution(name=runner_id)
        log.info("synthetic_data_runner.cancelled", runner_id=runner_id)

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
        env: dict[str, str],
    ) -> RunnerLaunchResult:
        settings = get_settings()

        from google.cloud import run_v2

        client = run_v2.JobsAsyncClient()
        job_name = (
            f"projects/{settings.gcp_project_id}"
            f"/locations/{settings.gcp_region}"
            f"/jobs/testlyn-engine-synthetic-data"
        )

        overrides = run_v2.RunJobRequest.Overrides(
            container_overrides=[
                run_v2.RunJobRequest.Overrides.ContainerOverride(
                    env=[
                        run_v2.EnvVar(name=k, value=v)
                        for k, v in {
                            "RUN_ID": str(test_run_id),
                            "GCP_PROJECT": settings.gcp_project_id,
                            "GCS_RESULTS_BUCKET": settings.gcs_results_bucket,
                            "CALLBACK_URL": (
                                f"{settings.api_base_url}"
                                f"/v1/internal/runs/{test_run_id}/complete"
                            ),
                            # Shared secret echoed back on the callback for
                            # X-Internal-Token gate parity with the load engine.
                            # Without it, cloud callbacks are rejected with 403
                            # and the run never completes.
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
            "synthetic_data_runner.launched_cloud",
            run_id=str(test_run_id),
            execution=execution_name,
        )
        return RunnerLaunchResult(
            runner_id=execution_name,
            started_at=datetime.now(tz=UTC),
            region=settings.gcp_region,
        )
