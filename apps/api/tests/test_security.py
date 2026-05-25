from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

# ---------------------------------------------------------------------------
# SecurityRunner — Protocol conformance
# ---------------------------------------------------------------------------


class TestSecurityRunnerProtocol:
    def test_implements_runner_protocol(self) -> None:
        from testlyn_api.core.runner import Runner
        from testlyn_api.products.security.runner import SecurityRunner

        runner = SecurityRunner()
        assert isinstance(runner, Runner)

    def test_product_discriminator(self) -> None:
        from testlyn_api.products.security.runner import SecurityRunner

        assert SecurityRunner.product == "security"

    @pytest.mark.asyncio
    async def test_launch_docker_no_zap_returns_stub(self) -> None:
        """With no ZAP binary, returns a stub runner_id."""
        from unittest.mock import patch

        from testlyn_api.products.security.runner import SecurityRunner

        runner = SecurityRunner()
        run_id = uuid.uuid4()

        with patch("shutil.which", return_value=None):
            result = await runner.launch(
                test_run_id=run_id,
                script_uri="",
                vus=1,
                duration_seconds=600,
                env={
                    "TARGET_URL": "https://example.com",
                    "SCAN_KIND": "baseline",
                },
            )

        assert result.runner_id.startswith("security-stub-")
        assert result.region == "local"

    @pytest.mark.asyncio
    async def test_launch_subprocess_uses_nonpredictable_temp_path(self) -> None:
        """Report path must NOT be the predictable /tmp/zap-<id>.json (bandit B108)."""
        from unittest.mock import AsyncMock, patch

        from testlyn_api.products.security import runner as runner_mod
        from testlyn_api.products.security.runner import SecurityRunner

        runner = SecurityRunner()
        run_id = uuid.uuid4()

        fake_proc = AsyncMock()
        fake_proc.communicate.return_value = (b"", b"")
        fake_proc.returncode = 0

        with (
            patch("shutil.which", return_value="/usr/local/bin/zap-baseline.py"),
            patch(
                "asyncio.create_subprocess_exec", AsyncMock(return_value=fake_proc)
            ) as mock_exec,
            patch.object(runner_mod.log, "info") as mock_info,
            patch("httpx.AsyncClient"),
        ):
            result = await runner.launch(
                test_run_id=run_id,
                script_uri="",
                vus=1,
                duration_seconds=60,
                env={"TARGET_URL": "https://example.com", "SCAN_KIND": "baseline"},
            )
            # Let the fire-and-forget background callback run to completion so
            # the captured subprocess invocation is the real one the runner built.
            for task in list(runner_mod._background_tasks):
                await task

        # Recover the cmd from the subprocess_launch log (report path follows -J).
        captured_cmd: list[str] = []
        for call in mock_info.call_args_list:
            if call.args and call.args[0] == "security_runner.subprocess_launch":
                captured_cmd = call.kwargs["cmd"]
                break

        assert captured_cmd, "expected subprocess_launch log with cmd"
        report_path = captured_cmd[captured_cmd.index("-J") + 1]
        assert report_path != f"/tmp/zap-{run_id}.json"
        assert report_path.endswith(".json")
        assert f"zap-{run_id}" in report_path
        # The same path was passed to the subprocess.
        assert report_path in mock_exec.call_args.args
        assert result.region == "local"

    @pytest.mark.asyncio
    async def test_cancel_docker_noop(self) -> None:
        from testlyn_api.products.security.runner import SecurityRunner

        runner = SecurityRunner()
        await runner.cancel(runner_id="security-stub-abc")

    @pytest.mark.asyncio
    async def test_status_docker_returns_running(self) -> None:
        from testlyn_api.products.security.runner import SecurityRunner

        runner = SecurityRunner()
        status = await runner.status(runner_id="security-stub-abc")
        assert status.state == "running"


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class TestZapScanSchemas:
    def test_defaults(self) -> None:
        from testlyn_api.products.security.schemas import ZapScanRequest

        req = ZapScanRequest(
            org_id=uuid.uuid4(),
            target_url="https://example.com",
        )
        assert req.scan_kind == "baseline"
        assert req.auth_recipe_id is None

    def test_scan_kind_literal(self) -> None:
        from pydantic import ValidationError
        from testlyn_api.products.security.schemas import ZapScanRequest

        with pytest.raises(ValidationError):
            ZapScanRequest(
                org_id=uuid.uuid4(),
                target_url="https://example.com",
                scan_kind="aggressive",  # invalid
            )

    def test_response_product_literal(self) -> None:
        from testlyn_api.products.security.schemas import SecurityScanResponse

        resp = SecurityScanResponse(scan_id=uuid.uuid4())
        assert resp.product == "security"
        assert resp.findings_count == 0
        assert resp.findings == []

    @pytest.mark.parametrize("risk", ["high", "medium", "low", "informational"])
    def test_finding_risk_literals(self, risk: str) -> None:
        from testlyn_api.products.security.schemas import ZapFinding

        f = ZapFinding(
            plugin_id="10038",
            alert="Content Security Policy",
            risk=risk,
            confidence="medium",
            url="https://example.com",
            description="CSP not set",
        )
        assert f.risk == risk

    def test_finding_invalid_risk(self) -> None:
        from pydantic import ValidationError
        from testlyn_api.products.security.schemas import ZapFinding

        with pytest.raises(ValidationError):
            ZapFinding(
                plugin_id="1",
                alert="x",
                risk="critical",  # not a valid literal
                confidence="high",
                url="https://example.com",
                description="x",
            )


# ---------------------------------------------------------------------------
# API route
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scan_baseline_returns_202(client: AsyncClient, dev_org_id: uuid.UUID) -> None:
    from unittest.mock import patch

    with patch("shutil.which", return_value=None):
        response = await client.post(
            "/v1/products/security/scan",
            json={
                "org_id": str(dev_org_id),
                "target_url": "https://example.com",
                "scan_kind": "baseline",
            },
        )
    assert response.status_code == 202
    data = response.json()
    assert data["product"] == "security"
    assert data["status"] == "queued"
    assert data["scan_kind"] == "baseline"
    assert data["findings_count"] == 0
    assert "scan_id" in data
    assert data["message"] is not None
    assert "ZAP" in data["message"]


@pytest.mark.asyncio
async def test_scan_full_kind(client: AsyncClient, dev_org_id: uuid.UUID) -> None:
    from unittest.mock import patch

    with patch("shutil.which", return_value=None):
        response = await client.post(
            "/v1/products/security/scan",
            json={
                "org_id": str(dev_org_id),
                "target_url": "https://example.com",
                "scan_kind": "full",
            },
        )
    assert response.status_code == 202
    assert response.json()["scan_kind"] == "full"


@pytest.mark.asyncio
async def test_scan_with_auth_recipe(client: AsyncClient, dev_org_id: uuid.UUID) -> None:
    from unittest.mock import patch

    recipe_id = str(uuid.uuid4())
    with patch("shutil.which", return_value=None):
        response = await client.post(
            "/v1/products/security/scan",
            json={
                "org_id": str(dev_org_id),
                "target_url": "https://example.com",
                "auth_recipe_id": recipe_id,
                "scan_kind": "full",
            },
        )
    assert response.status_code == 202
    data = response.json()
    assert data["status"] == "queued"
