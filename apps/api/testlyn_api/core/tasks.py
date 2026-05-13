from __future__ import annotations

import json
import subprocess
import uuid
from typing import Any

import structlog

from testlyn_api.config import get_settings

log = structlog.get_logger(__name__)

_background_tasks: set[Any] = set()


async def enqueue_run(run_id: uuid.UUID) -> None:
    """
    Dispatch a test run.

    Cloud mode: submits a Cloud Tasks task that POSTs to
    /v1/internal/runs/{run_id}/start with OIDC auth.

    Docker mode (RUN_MODE=docker): calls the internal start handler directly
    by invoking docker run in a subprocess (fire-and-forget).
    """
    settings = get_settings()

    if settings.run_mode == "docker":
        await _enqueue_docker(run_id)
    else:
        await _enqueue_cloud_tasks(run_id)


async def _enqueue_cloud_tasks(run_id: uuid.UUID) -> None:
    import google.auth
    from google.cloud import tasks_v2

    settings = get_settings()
    _, project = google.auth.default()
    project_id = project or settings.gcp_project_id

    client = tasks_v2.CloudTasksAsyncClient()
    parent = client.queue_path(project_id, settings.gcp_region, settings.cloud_tasks_queue)

    url = f"{settings.api_base_url}/v1/internal/runs/{run_id}/start"

    task = tasks_v2.Task(
        http_request=tasks_v2.HttpRequest(
            http_method=tasks_v2.HttpMethod.POST,
            url=url,
            oidc_token=tasks_v2.OidcToken(
                service_account_email=f"testlyn-api@{project_id}.iam.gserviceaccount.com",
                audience=url,
            ),
            headers={"Content-Type": "application/json"},
            body=json.dumps({"run_id": str(run_id)}).encode(),
        )
    )

    response = await client.create_task(request={"parent": parent, "task": task})
    log.info("tasks.enqueued", run_id=str(run_id), task_name=response.name)


async def _enqueue_docker(run_id: uuid.UUID) -> None:
    """
    Local dev mode: invoke the internal start endpoint directly via an async
    subprocess so we don't block the request handler.
    """
    import asyncio

    settings = get_settings()
    url = f"{settings.api_base_url}/v1/internal/runs/{run_id}/start"

    async def _call() -> None:
        proc = await asyncio.create_subprocess_exec(
            "curl",
            "-s",
            "-X",
            "POST",
            url,
            "-H",
            "Content-Type: application/json",
            "-d",
            json.dumps({"run_id": str(run_id)}),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        _stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            log.warning(
                "tasks.docker_call_failed",
                run_id=str(run_id),
                stderr=stderr.decode(),
            )
        else:
            log.info("tasks.docker_call_ok", run_id=str(run_id))

    task = asyncio.create_task(_call())
    # Keep reference to avoid GC before completion
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
