"""
Cloud Tasks handlers for the a11y product.

Queue: testlyn-runs-a11y
Handler: POST /v1/internal/a11y/runs/:run_id/complete

This module mirrors the pattern used by core/tasks.py for the load product.
The internal router (routers/internal.py) should register complete_a11y_run
once the a11y product is fully wired (Phase 2 completion step).

TODO(W2C): register the internal completion endpoint in routers/internal.py.
"""

from __future__ import annotations

import uuid

import structlog

from testlyn_api.config import get_settings

log = structlog.get_logger(__name__)


async def enqueue_a11y_run(run_id: uuid.UUID) -> None:
    """
    Dispatch an a11y audit run to the testlyn-runs-a11y Cloud Tasks queue.

    Cloud mode: submits a Cloud Tasks task that POSTs to
    /v1/internal/a11y/runs/{run_id}/start with OIDC auth.

    Docker mode: no-op (a11y runner returns a stub result directly).
    """
    settings = get_settings()

    if settings.run_mode == "docker":
        log.info("a11y.tasks.enqueue_noop_docker", run_id=str(run_id))
        return

    await _enqueue_cloud_tasks(run_id)


async def _enqueue_cloud_tasks(run_id: uuid.UUID) -> None:
    import json

    import google.auth
    from google.cloud import tasks_v2

    settings = get_settings()
    _, project = google.auth.default()
    project_id = project or settings.gcp_project_id

    client = tasks_v2.CloudTasksAsyncClient()
    # Separate queue for a11y jobs to avoid head-of-line blocking with load tests
    queue_name = "testlyn-runs-a11y"
    parent = client.queue_path(project_id, settings.gcp_region, queue_name)

    url = f"{settings.api_base_url}/v1/internal/a11y/runs/{run_id}/start"

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
    log.info("a11y.tasks.enqueued", run_id=str(run_id), task_name=response.name)
