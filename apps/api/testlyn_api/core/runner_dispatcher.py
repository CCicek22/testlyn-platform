from __future__ import annotations

import json
import uuid
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from testlyn_api.config import get_settings
from testlyn_api.models.runner_registry import RunnerRegistry

log = structlog.get_logger(__name__)


class RunnerDispatcher:
    """
    Routes a test run to the correct product queue / docker runner.

    Cloud mode: enqueues to Cloud Tasks queue `testlyn-runs-{product}`.
    Docker mode (RUN_MODE=docker): delegates to the existing docker-based
    internal start path (same curl mechanism as enqueue_run).
    """

    async def dispatch(
        self,
        *,
        test_run_id: uuid.UUID,
        product: str,
        session: AsyncSession,
        extra: dict[str, Any] | None = None,
    ) -> str:
        """
        Dispatch a test run.

        Returns the queue name (cloud) or 'docker' (docker mode) for
        observability / logging.
        """
        settings = get_settings()

        runner_row = await self._lookup_runner(product, session)
        image_uri = runner_row.image_uri if runner_row else None

        log.info(
            "dispatcher.dispatch",
            run_id=str(test_run_id),
            product=product,
            image_uri=image_uri,
            run_mode=settings.run_mode,
        )

        if settings.run_mode == "docker":
            await self._dispatch_docker(test_run_id)
            return "docker"

        queue_name = f"testlyn-runs-{product}"
        await self._dispatch_cloud_tasks(
            test_run_id=test_run_id,
            product=product,
            queue_name=queue_name,
            image_uri=image_uri,
            extra=extra or {},
        )
        return queue_name

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    async def _lookup_runner(
        self, product: str, session: AsyncSession
    ) -> RunnerRegistry | None:
        result = await session.execute(
            select(RunnerRegistry).where(RunnerRegistry.product == product)
        )
        return result.scalar_one_or_none()

    async def _dispatch_docker(self, test_run_id: uuid.UUID) -> None:
        """Fire-and-forget curl to the internal start endpoint (docker mode)."""
        import asyncio
        import subprocess

        settings = get_settings()
        url = f"{settings.api_base_url}/v1/internal/runs/{test_run_id}/start"

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
                json.dumps({"run_id": str(test_run_id)}),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            _stdout, stderr = await proc.communicate()
            if proc.returncode != 0:
                log.warning(
                    "dispatcher.docker_call_failed",
                    run_id=str(test_run_id),
                    stderr=stderr.decode(),
                )
            else:
                log.info("dispatcher.docker_call_ok", run_id=str(test_run_id))

        task = asyncio.create_task(_call())
        # Keep reference to avoid premature GC
        _BACKGROUND_TASKS.add(task)
        task.add_done_callback(_BACKGROUND_TASKS.discard)

    async def _dispatch_cloud_tasks(
        self,
        *,
        test_run_id: uuid.UUID,
        product: str,
        queue_name: str,
        image_uri: str | None,
        extra: dict[str, Any],
    ) -> None:
        import google.auth
        from google.cloud import tasks_v2

        settings = get_settings()
        _, project = google.auth.default()
        project_id = project or settings.gcp_project_id

        client = tasks_v2.CloudTasksAsyncClient()
        parent = client.queue_path(project_id, settings.gcp_region, queue_name)

        url = f"{settings.api_base_url}/v1/internal/runs/{test_run_id}/start"

        payload: dict[str, Any] = {
            "run_id": str(test_run_id),
            "product": product,
        }
        if image_uri:
            payload["image_uri"] = image_uri
        payload.update(extra)

        task = tasks_v2.Task(
            http_request=tasks_v2.HttpRequest(
                http_method=tasks_v2.HttpMethod.POST,
                url=url,
                oidc_token=tasks_v2.OidcToken(
                    service_account_email=f"testlyn-api@{project_id}.iam.gserviceaccount.com",
                    audience=url,
                ),
                headers={"Content-Type": "application/json"},
                body=json.dumps(payload).encode(),
            )
        )

        response = await client.create_task(request={"parent": parent, "task": task})
        log.info(
            "dispatcher.cloud_tasks_enqueued",
            run_id=str(test_run_id),
            queue=queue_name,
            task_name=response.name,
        )


_BACKGROUND_TASKS: set[Any] = set()
