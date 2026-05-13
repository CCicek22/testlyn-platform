from __future__ import annotations

import asyncio
import shutil
import subprocess
import uuid
from datetime import UTC, datetime
from typing import Any

import structlog

from testlyn_api.config import get_settings
from testlyn_api.core.runner import RunnerLaunchResult, RunnerStatus

log = structlog.get_logger(__name__)

# Canned response when schemathesis binary is unavailable
_CANNED_REPORT: dict[str, Any] = {
    "drift_count": 0,
    "findings": [],
    "message": "schemathesis not available — canned stub response",
}


class ApiContractRunner:
    """
    Runner stub for API contract drift detection via Schemathesis.

    Cloud mode: dispatches a Cloud Run Job.
    Docker / missing binary mode: runs schemathesis as a subprocess if
    available; otherwise returns a canned "0 drift detected" response.

    Conforms to the Runner Protocol (core/runner.py).
    """

    product: str = "api_contract"

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
            return await self._launch_subprocess(test_run_id=test_run_id, env=env)

        return await self._launch_cloud(test_run_id=test_run_id, env=env)

    async def cancel(self, *, runner_id: str) -> None:
        settings = get_settings()
        if settings.run_mode == "docker":
            log.info("api_contract_runner.cancel_noop_docker", runner_id=runner_id)
            return

        from google.cloud import run_v2

        client = run_v2.JobsAsyncClient()
        await client.cancel_execution(name=runner_id)
        log.info("api_contract_runner.cancelled", runner_id=runner_id)

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

        state_map = {
            run_v2.Execution.ExecutionStatus.EXECUTION_STATUS_UNSPECIFIED: "queued",
            run_v2.Execution.ExecutionStatus.ACTIVE: "running",
            run_v2.Execution.ExecutionStatus.SUCCEEDED: "completed",
            run_v2.Execution.ExecutionStatus.FAILED: "failed",
            run_v2.Execution.ExecutionStatus.CANCELLED: "cancelled",
        }
        state = state_map.get(execution.reconciling, "queued")

        return RunnerStatus(
            state=state,
            started_at=execution.start_time,
            finished_at=execution.completion_time,
            exit_reason=None,
        )

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    async def _launch_subprocess(
        self,
        *,
        test_run_id: uuid.UUID,
        env: dict[str, str],
    ) -> RunnerLaunchResult:
        """Try schemathesis subprocess; fall back to canned response."""
        if not shutil.which("schemathesis"):
            log.warning(
                "api_contract_runner.schemathesis_missing",
                run_id=str(test_run_id),
                note="returning canned stub; install schemathesis for real scans",
            )
            return RunnerLaunchResult(
                runner_id=f"contract-stub-{test_run_id}",
                started_at=datetime.now(tz=UTC),
                region="local",
            )

        openapi_url = env.get("OPENAPI_URL", "")
        target_url = env.get("TARGET_URL", "")
        max_examples = env.get("MAX_EXAMPLES", "50")

        cmd = [
            "schemathesis",
            "run",
            openapi_url,
            "--base-url",
            target_url,
            "--max-response-time",
            "5000",
            f"--hypothesis-max-examples={max_examples}",
            "--output-truncate=false",
            "--report",
            f"/tmp/schemathesis-{test_run_id}.json",
        ]

        log.info("api_contract_runner.subprocess_launch", run_id=str(test_run_id), cmd=cmd)

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            await proc.communicate()
        except Exception as exc:
            log.error("api_contract_runner.subprocess_error", run_id=str(test_run_id), error=str(exc))

        return RunnerLaunchResult(
            runner_id=f"contract-subprocess-{test_run_id}",
            started_at=datetime.now(tz=UTC),
            region="local",
        )

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
            f"/jobs/testlyn-engine-api-contract"
        )

        overrides = run_v2.RunJobRequest.Overrides(
            container_overrides=[
                run_v2.RunJobRequest.Overrides.ContainerOverride(
                    env=[
                        run_v2.EnvVar(name=k, value=v)
                        for k, v in {
                            "RUN_ID": str(test_run_id),
                            "GCP_PROJECT": settings.gcp_project_id,
                            "CALLBACK_URL": (
                                f"{settings.api_base_url}"
                                f"/v1/internal/runs/{test_run_id}/complete"
                            ),
                            **env,
                        }.items()
                    ]
                )
            ]
        )

        response = await client.run_job(name=job_name, overrides=overrides)
        op_meta = response.metadata
        execution_name = (
            op_meta.name if op_meta else f"{job_name}/executions/{test_run_id}"
        )

        log.info(
            "api_contract_runner.launched_cloud",
            run_id=str(test_run_id),
            execution=execution_name,
        )
        return RunnerLaunchResult(
            runner_id=execution_name,
            started_at=datetime.now(tz=UTC),
            region=settings.gcp_region,
        )
