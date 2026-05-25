"""Internal-token gate parity for non-load workers (finding #7).

The /v1/internal/* endpoints require X-Internal-Token in cloud mode. The load
engine injects it into the job override and echoes it on the callback; the
a11y / Playwright runners + their entrypoints, and the RunnerDispatcher Cloud
Tasks path, must do the same so completed runs are actually marked done.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from google.cloud import run_v2

_INTERNAL_TOKEN = "s3cr3t-internal-token"

_ROOT = Path(__file__).resolve().parents[3]
_ENGINE_A11Y = _ROOT / "apps" / "engine-a11y" / "entrypoint.sh"
_ENGINE_PW = _ROOT / "apps" / "engine-playwright" / "entrypoint.sh"


def _fake_settings() -> SimpleNamespace:
    return SimpleNamespace(
        run_mode="cloud",
        gcp_project_id="test-project",
        gcp_region="us-central1",
        gcp_bq_dataset="testlyn_metrics",
        api_base_url="http://testserver",
        internal_token=_INTERNAL_TOKEN,
    )


class _CapturingJobsAsyncClient:
    """Captures the container-override env passed to run_job.

    NOTE: the non-load runners currently call ``run_job(name=, overrides=)`` with
    flattened kwargs, which the *real* gapic client rejects (it has no
    ``overrides`` parameter — see tests/products/load/test_k6_runner_cloud.py and
    the k6 PR #42 fix). That flattened-call bug is pre-existing and tracked
    separately; this fake accepts both call shapes so the test asserts only the
    INTERNAL_TOKEN injection (finding #7), independent of that bug.
    """

    last_overrides: Any = None

    def __init__(self, *a: Any, **k: Any) -> None:
        pass

    async def run_job(  # noqa: ANN001, ANN201
        self, request=None, *, name=None, overrides=None, retry=None, timeout=None, metadata=()
    ):
        if request is not None:
            overrides = request.overrides
        type(self).last_overrides = overrides
        op = MagicMock()
        op.metadata = SimpleNamespace(name="proj/loc/jobs/j/executions/e1")
        return op


def _override_env(overrides: Any) -> dict[str, str]:
    co = overrides.container_overrides[0]
    return {e.name: e.value for e in co.env}


# ─── runner override injection ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_a11y_runner_injects_internal_token(monkeypatch: pytest.MonkeyPatch) -> None:
    from testlyn_api.products.a11y import runner as a11y_runner

    monkeypatch.setattr(a11y_runner, "get_settings", _fake_settings)
    monkeypatch.setattr(run_v2, "JobsAsyncClient", _CapturingJobsAsyncClient)

    await a11y_runner.A11yRunner()._launch_cloud(
        test_run_id=uuid.uuid4(),
        script_uri="gs://bucket/audit-config.json",
        env={"ORG_ID": "org-1", "AUDIT_URLS": "https://example.com"},
    )

    env = _override_env(_CapturingJobsAsyncClient.last_overrides)
    assert env["INTERNAL_TOKEN"] == _INTERNAL_TOKEN


@pytest.mark.asyncio
async def test_playwright_runner_injects_internal_token(monkeypatch: pytest.MonkeyPatch) -> None:
    from testlyn_api.products.functional import runner as fn_runner

    monkeypatch.setattr(fn_runner, "get_settings", _fake_settings)
    monkeypatch.setattr(run_v2, "JobsAsyncClient", _CapturingJobsAsyncClient)

    await fn_runner.PlaywrightRunner()._launch_cloud(
        test_run_id=uuid.uuid4(),
        script_uri="gs://bucket/test.spec.ts",
        env={"ORG_ID": "org-1"},
    )

    env = _override_env(_CapturingJobsAsyncClient.last_overrides)
    assert env["INTERNAL_TOKEN"] == _INTERNAL_TOKEN


# ─── dispatcher Cloud Tasks header ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_runner_dispatcher_uses_internal_token_header(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """_dispatch_cloud_tasks must carry X-Internal-Token and NOT use OIDC."""
    from testlyn_api.config import get_settings
    from testlyn_api.core import runner_dispatcher

    cloud = get_settings().model_copy(
        update={"run_mode": "cloud", "dev_auth_bypass": False, "internal_token": _INTERNAL_TOKEN}
    )
    monkeypatch.setattr(runner_dispatcher, "get_settings", lambda: cloud)

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
        patch("google.cloud.tasks_v2.CloudTasksAsyncClient", return_value=mock_client),
    ):
        await runner_dispatcher.RunnerDispatcher()._dispatch_cloud_tasks(
            test_run_id=uuid.uuid4(),
            product="a11y",
            queue_name="testlyn-runs-a11y",
            image_uri=None,
            extra={},
        )

    task = captured["task"]
    headers = dict(task.http_request.headers)
    assert headers.get("X-Internal-Token") == _INTERNAL_TOKEN
    assert headers.get("Content-Type") == "application/json"
    # OIDC must NOT be set — internal calls use the shared secret only.
    assert not task.http_request.oidc_token.service_account_email


# ─── engine entrypoint callback contract ─────────────────────────────────────────


def test_engine_a11y_entrypoint_sends_internal_token() -> None:
    content = _ENGINE_A11Y.read_text()
    assert "X-Internal-Token: ${INTERNAL_TOKEN}" in content


def test_engine_playwright_entrypoint_sends_internal_token() -> None:
    content = _ENGINE_PW.read_text()
    assert "X-Internal-Token: ${INTERNAL_TOKEN}" in content
