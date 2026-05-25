from __future__ import annotations

import asyncio
import subprocess
import uuid
from datetime import UTC, datetime
from typing import Any

import structlog

from testlyn_api.config import get_settings
from testlyn_api.core.runner import RunnerLaunchResult, RunnerStatus
from testlyn_api.core.runner_state import execution_to_status

log = structlog.get_logger(__name__)

_background_tasks: set[Any] = set()
_MAX_SCRIPT_BYTES = 1 * 1024 * 1024  # 1 MiB


class K6Runner:
    """
    Concrete Runner implementation for load testing via stock grafana/k6.

    Cloud mode: uploads script to GCS, dispatches Cloud Run Job.
    Docker mode (RUN_MODE=docker): shells out to `docker run grafana/k6`.
    """

    product: str = "load"

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
            return await self._launch_docker(
                test_run_id=test_run_id,
                vus=vus,
                duration_seconds=duration_seconds,
                env=env,
            )
        return await self._launch_cloud(
            test_run_id=test_run_id,
            script_uri=script_uri,
            vus=vus,
            duration_seconds=duration_seconds,
            env=env,
        )

    async def cancel(self, *, runner_id: str) -> None:
        settings = get_settings()
        if settings.run_mode == "docker":
            log.info("k6_runner.cancel_noop_docker", runner_id=runner_id)
            return

        from google.cloud import run_v2

        client = run_v2.JobsAsyncClient()
        # runner_id is the execution resource name
        await client.cancel_execution(name=runner_id)
        log.info("k6_runner.cancelled", runner_id=runner_id)

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
    # Private helpers
    # ------------------------------------------------------------------

    async def _launch_cloud(
        self,
        *,
        test_run_id: uuid.UUID,
        script_uri: str,
        vus: int,
        duration_seconds: int,
        env: dict[str, str],
    ) -> RunnerLaunchResult:
        settings = get_settings()

        from google.cloud import run_v2

        client = run_v2.JobsAsyncClient()
        job_name = f"projects/{settings.gcp_project_id}/locations/{settings.gcp_region}/jobs/testlyn-engine"

        overrides = run_v2.RunJobRequest.Overrides(
            container_overrides=[
                run_v2.RunJobRequest.Overrides.ContainerOverride(
                    env=[
                        run_v2.EnvVar(name=k, value=v)
                        for k, v in {
                            "RUN_ID": str(test_run_id),
                            "SCRIPT_GCS_URI": script_uri,
                            "VUS": str(vus),
                            "DURATION": f"{duration_seconds}s",
                            "BQ_DATASET": settings.gcp_bq_dataset,
                            "GCP_PROJECT": settings.gcp_project_id,
                            "CALLBACK_URL": f"{settings.api_base_url}/v1/internal/runs/{test_run_id}/complete",
                            # Shared secret the engine echoes back on its callback
                            # so the API's X-Internal-Token gate accepts it.
                            "INTERNAL_TOKEN": settings.internal_token,
                            # ORG_ID arrives via **env (resolved in start_run); the
                            # engine entrypoint hard-requires it.
                            **env,
                        }.items()
                    ]
                )
            ]
        )

        response = await client.run_job(
            name=job_name,
            overrides=overrides,
        )
        # response is an Operation; execution name is in metadata
        op_meta = response.metadata
        execution_name = op_meta.name if op_meta else f"{job_name}/executions/{test_run_id}"

        log.info("k6_runner.launched_cloud", run_id=str(test_run_id), execution=execution_name)
        return RunnerLaunchResult(
            runner_id=execution_name,
            started_at=datetime.now(tz=UTC),
            region=settings.gcp_region,
        )

    async def _launch_docker(
        self,
        *,
        test_run_id: uuid.UUID,
        vus: int,
        duration_seconds: int,
        env: dict[str, str],
    ) -> RunnerLaunchResult:
        settings = get_settings()

        script_inline = env.get("SCRIPT_INLINE", "")
        if not script_inline:
            script_inline = "import http from 'k6/http';\nexport default function() { http.get('http://test.k6.io'); }"

        # Write script to a temp file and mount it into the container
        import os
        import tempfile

        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".js", mode="w", encoding="utf-8")
        tmp.write(script_inline)
        tmp.flush()
        script_path = tmp.name
        tmp.close()

        docker_cmd = [
            "docker",
            "run",
            "--rm",
            "-v",
            f"{script_path}:/tmp/script.js:ro",
            "-e",
            f"RUN_ID={test_run_id}",
            settings.k6_image_tag,
            "run",
            f"--vus={vus}",
            f"--duration={duration_seconds}s",
            "--out",
            "json=/tmp/k6.jsonl",
            "/tmp/script.js",
        ]

        log.info("k6_runner.docker_launch", run_id=str(test_run_id), cmd=docker_cmd)

        async def _run_docker() -> None:
            try:
                proc = await asyncio.create_subprocess_exec(
                    *docker_cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                _stdout, _stderr = await proc.communicate()
                log.info(
                    "k6_runner.docker_finished",
                    run_id=str(test_run_id),
                    exit_code=proc.returncode,
                )
                # Callback to mark run complete
                import httpx

                async with httpx.AsyncClient() as client:
                    await client.post(
                        f"{settings.api_base_url}/v1/internal/runs/{test_run_id}/complete",
                        json={"exit_code": proc.returncode or 0},
                        timeout=10,
                    )
            except Exception as exc:
                log.error("k6_runner.docker_error", run_id=str(test_run_id), error=str(exc))
            finally:
                try:
                    os.unlink(script_path)
                except OSError:
                    pass

        _task = asyncio.create_task(_run_docker())
        _background_tasks.add(_task)
        _task.add_done_callback(_background_tasks.discard)

        return RunnerLaunchResult(
            runner_id=f"docker-{test_run_id}",
            started_at=datetime.now(tz=UTC),
            region="local",
        )
