"""Regression test for the Cloud Run Job dispatch in K6Runner._launch_cloud.

Guards against the `JobsAsyncClient.run_job() got an unexpected keyword
argument 'overrides'` failure: google-cloud-run's run_job() only accepts
(request, name, retry, timeout, metadata) — `overrides` must travel inside a
RunJobRequest, not as a flattened kwarg. The fake client below mirrors the real
signature so passing `overrides=` directly would raise TypeError.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any

import pytest
from google.cloud import run_v2

from testlyn_api.products.load import k6_runner


class _FakeOp:
    def __init__(self) -> None:
        self.metadata = SimpleNamespace(name="projects/p/locations/us-central1/jobs/testlyn-engine/executions/exec-1")


class _FakeJobsAsyncClient:
    """Mirrors run_v2.JobsAsyncClient.run_job's real signature."""

    last_request: Any = None

    def __init__(self, *_a: Any, **_k: Any) -> None:
        pass

    async def run_job(
        self, request=None, *, name=None, retry=None, timeout=None, metadata=()
    ):  # noqa: ANN001, ANN201 - mirror gapic signature exactly
        type(self).last_request = request
        # The old buggy call site passed overrides=... which isn't a param here;
        # if that regressed, Python raises TypeError before reaching this body.
        assert name is None, "run_job must be called with request=, not flattened name="
        return _FakeOp()


@pytest.mark.asyncio
async def test_launch_cloud_passes_overrides_inside_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        k6_runner,
        "get_settings",
        lambda: SimpleNamespace(
            run_mode="cloud",
            gcp_project_id="test-project",
            gcp_region="us-central1",
            gcp_bq_dataset="testlyn_metrics",
            api_base_url="http://testserver",
            internal_token="secret-tok",
        ),
    )
    monkeypatch.setattr(run_v2, "JobsAsyncClient", _FakeJobsAsyncClient)

    result = await k6_runner.K6Runner()._launch_cloud(
        test_run_id=uuid.uuid4(),
        script_uri="gs://bucket/script.js",
        vus=50,
        duration_seconds=15,
        env={"ORG_ID": "org-123"},
    )

    req = _FakeJobsAsyncClient.last_request
    assert isinstance(req, run_v2.RunJobRequest)
    assert req.name.endswith("/jobs/testlyn-engine")
    assert req.overrides.container_overrides, "overrides must carry container env"
    assert result.region == "us-central1"
    assert result.runner_id  # execution name propagated
