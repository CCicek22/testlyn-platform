from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_INTERNAL_TOKEN = "s3cr3t-internal-token"


@pytest.mark.asyncio
async def test_enqueue_cloud_tasks_uses_shared_secret_header(monkeypatch) -> None:
    """_enqueue_cloud_tasks must build a Task carrying X-Internal-Token and no OIDC."""
    from testlyn_api import core
    from testlyn_api.config import get_settings

    cloud = get_settings().model_copy(
        update={"run_mode": "cloud", "dev_auth_bypass": False, "internal_token": _INTERNAL_TOKEN}
    )
    # tasks.py imports get_settings into its own namespace at module load, so
    # patch the name where it is used (not testlyn_api.config).
    monkeypatch.setattr("testlyn_api.core.tasks.get_settings", lambda: cloud)

    run_id = uuid.uuid4()

    # Mock the Cloud Tasks client: capture the task passed to create_task.
    captured: dict = {}

    mock_client = MagicMock()
    mock_client.queue_path.return_value = "projects/p/locations/us-central1/queues/q"

    async def _create_task(request):  # noqa: ANN001
        captured["task"] = request["task"]
        resp = MagicMock()
        resp.name = "projects/p/locations/us-central1/queues/q/tasks/t1"
        return resp

    mock_client.create_task = AsyncMock(side_effect=_create_task)

    with (
        patch("google.auth.default", return_value=(None, "test-project")),
        patch(
            "google.cloud.tasks_v2.CloudTasksAsyncClient",
            return_value=mock_client,
        ),
    ):
        await core.tasks._enqueue_cloud_tasks(run_id)

    task = captured["task"]
    headers = dict(task.http_request.headers)
    assert headers.get("X-Internal-Token") == _INTERNAL_TOKEN
    assert headers.get("Content-Type") == "application/json"

    # OIDC must NOT be set — internal calls use the shared secret only.
    # Unset oneof field on the proto reports an empty service_account_email.
    assert not task.http_request.oidc_token.service_account_email
