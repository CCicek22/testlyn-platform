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


def _fake_settings() -> SimpleNamespace:
    return SimpleNamespace(
        run_mode="cloud",
        gcp_project_id="test-project",
        gcp_region="us-central1",
        gcp_bq_dataset="testlyn_metrics",
        gcs_scripts_bucket="testlyn-prod-scripts",
        api_base_url="http://testserver",
        internal_token="secret-tok",
    )


def _override_env(req: run_v2.RunJobRequest) -> dict[str, str]:
    co = req.overrides.container_overrides[0]
    return {e.name: e.value for e in co.env}


@pytest.mark.asyncio
async def test_launch_cloud_passes_overrides_inside_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(k6_runner, "get_settings", _fake_settings)
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
    # Pre-uploaded script_uri is passed through unchanged.
    assert _override_env(req)["SCRIPT_GCS_URI"] == "gs://bucket/script.js"
    assert result.region == "us-central1"
    assert result.runner_id  # execution name propagated


class _FakeBlob:
    def __init__(self, store: dict[str, Any], name: str) -> None:
        self._store = store
        self._name = name

    def upload_from_string(self, data: str, content_type: str | None = None) -> None:
        self._store[self._name] = (data, content_type)


class _FakeBucket:
    def __init__(self, store: dict[str, Any]) -> None:
        self._store = store

    def blob(self, name: str) -> _FakeBlob:
        return _FakeBlob(self._store, name)


class _FakeStorageClient:
    uploaded: dict[str, Any] = {}

    def __init__(self, *_a: Any, **_k: Any) -> None:
        pass

    def bucket(self, _name: str) -> _FakeBucket:
        return _FakeBucket(type(self).uploaded)


@pytest.mark.asyncio
async def test_launch_cloud_uploads_inline_script_when_no_uri(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A test with only an inline script (no script_uri) must be uploaded to the
    scripts bucket and the resulting gs:// URI passed as SCRIPT_GCS_URI — the
    engine entrypoint hard-requires a non-empty SCRIPT_GCS_URI."""
    from google.cloud import storage

    monkeypatch.setattr(k6_runner, "get_settings", _fake_settings)
    monkeypatch.setattr(run_v2, "JobsAsyncClient", _FakeJobsAsyncClient)
    _FakeStorageClient.uploaded = {}
    monkeypatch.setattr(storage, "Client", _FakeStorageClient)

    run_id = uuid.uuid4()
    inline = "import http from 'k6/http'; export default () => http.get('https://x/');"

    result = await k6_runner.K6Runner()._launch_cloud(
        test_run_id=run_id,
        script_uri="",  # no pre-uploaded script
        vus=50,
        duration_seconds=15,
        env={"ORG_ID": "org-123", "SCRIPT_INLINE": inline},
    )

    blob_name = f"inline/{run_id}.js"
    assert blob_name in _FakeStorageClient.uploaded, "inline script not uploaded"
    assert _FakeStorageClient.uploaded[blob_name][0] == inline

    req = _FakeJobsAsyncClient.last_request
    assert _override_env(req)["SCRIPT_GCS_URI"] == (
        f"gs://testlyn-prod-scripts/{blob_name}"
    )
    assert result.runner_id


@pytest.mark.asyncio
async def test_launch_cloud_raises_when_no_script_at_all(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(k6_runner, "get_settings", _fake_settings)
    monkeypatch.setattr(run_v2, "JobsAsyncClient", _FakeJobsAsyncClient)

    with pytest.raises(ValueError, match="neither script_uri nor"):
        await k6_runner.K6Runner()._launch_cloud(
            test_run_id=uuid.uuid4(),
            script_uri="",
            vus=1,
            duration_seconds=1,
            env={"ORG_ID": "org-123"},
        )
