from __future__ import annotations

import asyncio
import shutil
import subprocess
import tempfile
import uuid
from datetime import UTC, datetime

import structlog

from testlyn_api.config import get_settings
from testlyn_api.core.runner import RunnerLaunchResult, RunnerStatus
from testlyn_api.core.runner_state import execution_to_status

log = structlog.get_logger(__name__)

_background_tasks: set[asyncio.Task] = set()


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

        return execution_to_status(execution)

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
        # Avoid a predictable temp path (bandit B108): a non-guessable file the
        # process owns, kept after close so the ZAP subprocess can write to it.
        with tempfile.NamedTemporaryFile(
            prefix=f"zap-{test_run_id}-", suffix=".json", delete=False
        ) as report_file:
            report_path = report_file.name

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

        settings = get_settings()
        callback_url = f"{settings.api_base_url}/v1/internal/runs/{test_run_id}/complete"

        async def _run_and_callback() -> None:
            try:
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                _stdout, _stderr = await proc.communicate()
                log.info(
                    "security_runner.subprocess_finished",
                    run_id=str(test_run_id),
                    exit_code=proc.returncode,
                )
                import httpx

                async with httpx.AsyncClient() as http:
                    await http.post(
                        callback_url,
                        json={"exit_code": proc.returncode or 0},
                        timeout=10,
                    )
            except Exception as exc:
                log.error("security_runner.subprocess_error", run_id=str(test_run_id), error=str(exc))
            finally:
                # Clean up the report temp file (delete=False keeps it for the
                # subprocess; remove once the run + callback are done).
                import os

                try:
                    os.unlink(report_path)
                except OSError:
                    pass

        _task = asyncio.create_task(_run_and_callback())
        _background_tasks.add(_task)
        _task.add_done_callback(_background_tasks.discard)

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
                            # Shared secret echoed back on the callback for
                            # X-Internal-Token gate parity with the load engine.
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
            "security_runner.launched_cloud",
            run_id=str(test_run_id),
            execution=execution_name,
        )
        return RunnerLaunchResult(
            runner_id=execution_name,
            started_at=datetime.now(tz=UTC),
            region=settings.gcp_region,
        )
