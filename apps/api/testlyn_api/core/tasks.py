from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any

import httpx
import structlog

from testlyn_api.config import get_settings

log = structlog.get_logger(__name__)

_background_tasks: set[Any] = set()

# Per-attempt timeout and retry budget for the internal POST. The endpoint
# is local (same container in compose), so a short timeout + 3 attempts is
# plenty; we don't want to keep the test loop / dev shell waiting if the
# API is unreachable.
_POST_TIMEOUT_S = 2.0
_POST_ATTEMPTS = 3
_POST_BACKOFF_S = 0.2


async def _post_internal(url: str, payload: dict[str, Any]) -> None:
    """POST JSON to an internal endpoint with bounded retries.

    Shared between core/tasks.py (docker enqueue) and core/runner_dispatcher.py
    (docker dispatch). Replaces the previous shell-out to ``curl``, which both
    required ``curl`` in the image and gave us no structured error handling.
    """
    last_exc: Exception | None = None
    async with httpx.AsyncClient(timeout=_POST_TIMEOUT_S) as client:
        for attempt in range(1, _POST_ATTEMPTS + 1):
            try:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                return
            except (httpx.HTTPError, httpx.TimeoutException) as exc:
                last_exc = exc
                if attempt < _POST_ATTEMPTS:
                    await asyncio.sleep(_POST_BACKOFF_S * attempt)
    assert last_exc is not None
    raise last_exc


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

    # Internal endpoints are gated by a shared secret (X-Internal-Token), not
    # OIDC. The Cloud Tasks task carries the secret in the header; the API
    # verifies it in _verify_internal_token.
    if not settings.internal_token:
        log.warning("tasks.internal_token_unset", run_id=str(run_id))

    task = tasks_v2.Task(
        http_request=tasks_v2.HttpRequest(
            http_method=tasks_v2.HttpMethod.POST,
            url=url,
            headers={
                "Content-Type": "application/json",
                "X-Internal-Token": settings.internal_token,
            },
            body=json.dumps({"run_id": str(run_id)}).encode(),
        )
    )

    response = await client.create_task(request={"parent": parent, "task": task})
    log.info("tasks.enqueued", run_id=str(run_id), task_name=response.name)


async def _enqueue_docker(run_id: uuid.UUID) -> None:
    """
    Local dev mode: invoke the internal start endpoint directly via httpx so
    we don't block the request handler. Fire-and-forget — the task is tracked
    in ``_background_tasks`` so the GC won't reap it mid-flight.
    """
    settings = get_settings()
    url = f"{settings.api_base_url}/v1/internal/runs/{run_id}/start"

    async def _call() -> None:
        try:
            await _post_internal(url, {"run_id": str(run_id)})
            log.info("tasks.docker_call_ok", run_id=str(run_id))
        except Exception as exc:  # noqa: BLE001 — log + drop, fire-and-forget
            log.warning(
                "tasks.docker_call_failed",
                run_id=str(run_id),
                error=str(exc),
            )

    task = asyncio.create_task(_call())
    # Keep reference to avoid GC before completion
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
