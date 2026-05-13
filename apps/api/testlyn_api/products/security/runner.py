from __future__ import annotations

import asyncio
import shutil
import subprocess
import uuid
from datetime import UTC, datetime

import structlog

from testlyn_api.config import get_settings
from testlyn_api.core.runner import RunnerLaunchResult, RunnerStatus

log = structlog.get_logger(__name__)


class SecurityRunner:
    """
    Runner stub for DAST security scanning via OWASP ZAP.

    Cloud mode: dispatches a Cloud Run Job (testlyn-engine-security).
    Docker mode / missing binary: shells out to zap-baseline.py if available;
    otherwise returns a canned empty findings response.

    Conforms to the Runner Protocol (core/runner.py).
    """

    product: str = "security"

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
            log.info("security_runner.cancel_noop_docker", runner_id=runner_id)
            return

        from google.cloud import run_v2

        client = run_v2.JobsAsyncClient()
        await client.cancel_execution(name=runner_id)
        log.info("security_runner.cancelled", runner_id=runner_id)

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
        """Try zap-baseline.py; fall back to canned stub."""
        zap_script = shutil.which("zap-baseline.py") or shutil.which("zap.sh")

        if not zap_script:
            log.warning(
                "security_runner.zap_missing",
                run_id=str(test_run_id),
                note="returning canned stub; install OWASP ZAP for real scans",
            )
            return RunnerLaunchResult(
                runner_id=f"security-stub-{test_run_id}",
                started_at=datetime.now(tz=UTC),
                region="local",
            )

        target_url = env.get("TARGET_URL", "")
        scan_kind = env.get("SCAN_KIND", "baseline")
        report_path = f"/tmp/zap-{test_run_id}.json"

        cmd = [
            "python3",
            zap_script,
            "-t",
            target_url,
            "-J",
            report_path,
        ]
        if scan_kind == "full":
            cmd.append("-a")  # include active scanning

        log.info("security_runner.subprocess_launch", run_id=str(test_run_id), cmd=cmd)

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            await proc.communicate()
        except Exception as exc:
            log.error("security_runner.subprocess_error", run_id=str(test_run_id), error=str(exc))

        return RunnerLaunchResult(
            runner_id=f"security-subprocess-{test_run_id}",
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
            f"/jobs/testlyn-engine-security"
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
            "security_runner.launched_cloud",
            run_id=str(test_run_id),
            execution=execution_name,
        )
        return RunnerLaunchResult(
            runner_id=execution_name,
            started_at=datetime.now(tz=UTC),
            region=settings.gcp_region,
        )
