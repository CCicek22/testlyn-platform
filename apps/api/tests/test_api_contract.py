from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

# ---------------------------------------------------------------------------
# ApiContractRunner — Protocol conformance
# ---------------------------------------------------------------------------


class TestApiContractRunnerProtocol:
    def test_implements_runner_protocol(self) -> None:
        from testlyn_api.core.runner import Runner
        from testlyn_api.products.api_contract.runner import ApiContractRunner

        runner = ApiContractRunner()
        assert isinstance(runner, Runner)

    def test_product_discriminator(self) -> None:
        from testlyn_api.products.api_contract.runner import ApiContractRunner

        assert ApiContractRunner.product == "api_contract"

    @pytest.mark.asyncio
    async def test_launch_docker_no_binary_returns_stub(self) -> None:
        """With no schemathesis binary, returns a stub runner_id."""
        from unittest.mock import patch

        from testlyn_api.products.api_contract.runner import ApiContractRunner

        runner = ApiContractRunner()
        run_id = uuid.uuid4()

        with patch("shutil.which", return_value=None):
            result = await runner.launch(
                test_run_id=run_id,
                script_uri="",
                vus=1,
                duration_seconds=300,
                env={
                    "OPENAPI_URL": "https://petstore3.swagger.io/api/v3/openapi.json",
                    "TARGET_URL": "https://petstore3.swagger.io",
                },
            )

        assert result.runner_id.startswith("contract-stub-")
        assert result.region == "local"

    @pytest.mark.asyncio
    async def test_cancel_docker_noop(self) -> None:
        from testlyn_api.products.api_contract.runner import ApiContractRunner

        runner = ApiContractRunner()
        await runner.cancel(runner_id="contract-stub-abc")

    @pytest.mark.asyncio
    async def test_status_docker_returns_running(self) -> None:
        from testlyn_api.products.api_contract.runner import ApiContractRunner

        runner = ApiContractRunner()
        status = await runner.status(runner_id="contract-stub-abc")
        assert status.state == "running"


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class TestContractScanSchemas:
    def test_default_hypothesis_settings(self) -> None:
        from testlyn_api.products.api_contract.schemas import ContractScanRequest

        req = ContractScanRequest(
            org_id=uuid.uuid4(),
            openapi_url="https://example.com/openapi.json",
            target_url="https://example.com",
        )
        assert req.hypothesis_settings.max_examples == 50
        assert req.hypothesis_settings.derandomize is False

    def test_response_product_literal(self) -> None:
        from testlyn_api.products.api_contract.schemas import ContractScanResponse

        resp = ContractScanResponse(scan_id=uuid.uuid4())
        assert resp.product == "api_contract"
        assert resp.drift_count == 0

    def test_drift_finding(self) -> None:
        from testlyn_api.products.api_contract.schemas import DriftFinding

        f = DriftFinding(
            method="GET",
            path="/pets",
            status_code=500,
            failure_reason="Server error not in spec",
        )
        assert f.method == "GET"
        assert f.response_snippet is None

    def test_max_examples_bounds(self) -> None:
        from pydantic import ValidationError
        from testlyn_api.products.api_contract.schemas import HypothesisSettings

        with pytest.raises(ValidationError):
            HypothesisSettings(max_examples=0)
        with pytest.raises(ValidationError):
            HypothesisSettings(max_examples=2000)


# ---------------------------------------------------------------------------
# API route
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scan_returns_202(client: AsyncClient, dev_org_id: uuid.UUID) -> None:
    from unittest.mock import patch

    with patch("shutil.which", return_value=None):
        response = await client.post(
            "/v1/products/api-contract/scan",
            json={
                "org_id": str(dev_org_id),
                "openapi_url": "https://petstore3.swagger.io/api/v3/openapi.json",
                "target_url": "https://petstore3.swagger.io",
            },
        )
    assert response.status_code == 202
    data = response.json()
    assert data["product"] == "api_contract"
    # A real TestRun row is created and transitioned on launch now.
    assert data["status"] == "running"
    assert data["drift_count"] == 0
    assert "scan_id" in data
    # stub mode includes message
    assert data["message"] is not None
    assert "schemathesis" in data["message"]


@pytest.mark.asyncio
async def test_scan_custom_hypothesis(client: AsyncClient, dev_org_id: uuid.UUID) -> None:
    from unittest.mock import patch

    with patch("shutil.which", return_value=None):
        response = await client.post(
            "/v1/products/api-contract/scan",
            json={
                "org_id": str(dev_org_id),
                "openapi_url": "https://example.com/openapi.json",
                "target_url": "https://example.com",
                "hypothesis_settings": {
                    "max_examples": 100,
                    "derandomize": True,
                },
            },
        )
    assert response.status_code == 202
    assert response.json()["status"] == "running"


# ---------------------------------------------------------------------------
# Cloud launch env (review finding: INTERNAL_TOKEN was missing → callbacks 403)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_launch_cloud_env_includes_internal_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from types import SimpleNamespace

    from google.cloud import run_v2

    from testlyn_api.products.api_contract import runner as runner_mod

    class _FakeOp:
        metadata = SimpleNamespace(name="projects/p/locations/r/jobs/j/executions/e")

    captured: dict = {}

    class _FakeJobs:
        def __init__(self, *a, **k):  # noqa: ANN002, ANN003
            pass

        async def run_job(self, request=None, **_k):  # noqa: ANN001, ANN003
            captured["request"] = request
            return _FakeOp()

    monkeypatch.setattr(
        runner_mod,
        "get_settings",
        lambda: SimpleNamespace(
            run_mode="cloud",
            gcp_project_id="test-project",
            gcp_region="us-central1",
            api_base_url="http://testserver",
            internal_token="secret-tok",
        ),
    )
    monkeypatch.setattr(run_v2, "JobsAsyncClient", _FakeJobs)

    from testlyn_api.products.api_contract.runner import ApiContractRunner

    await ApiContractRunner()._launch_cloud(
        test_run_id=uuid.uuid4(),
        env={"TARGET_URL": "https://example.com"},
    )

    co = captured["request"].overrides.container_overrides[0]
    env = {e.name: e.value for e in co.env}
    assert env["INTERNAL_TOKEN"] == "secret-tok"
    assert "CALLBACK_URL" in env
