"""Tests for the functional product — PlaywrightRunner, schemas, routes, reports, steps."""

from __future__ import annotations

import uuid
from unittest.mock import patch

# ---------------------------------------------------------------------------
# PlaywrightRunner
# ---------------------------------------------------------------------------


class TestPlaywrightRunnerProtocolCompliance:
    def test_implements_runner_protocol(self):
        from testlyn_api.core.runner import Runner
        from testlyn_api.products.functional.runner import PlaywrightRunner

        assert isinstance(PlaywrightRunner(), Runner)

    def test_product_attribute(self):
        from testlyn_api.products.functional.runner import PlaywrightRunner

        assert PlaywrightRunner.product == "functional"

    async def test_launch_docker_returns_launch_result(self):
        import os

        os.environ["RUN_MODE"] = "docker"
        # invalidate settings cache
        from testlyn_api import config

        config.get_settings.cache_clear()

        from testlyn_api.products.functional.runner import PlaywrightRunner

        runner = PlaywrightRunner()
        run_id = uuid.uuid4()
        result = await runner.launch(
            test_run_id=run_id,
            script_uri="gs://bucket/script.ts",
            vus=1,
            duration_seconds=30,
            env={},
        )
        assert result.runner_id == f"docker-pw-{run_id}"
        assert result.region == "local"

        os.environ["RUN_MODE"] = "docker"  # keep consistent
        config.get_settings.cache_clear()

    async def test_cancel_docker_is_noop(self, caplog):
        import os

        os.environ["RUN_MODE"] = "docker"
        from testlyn_api import config

        config.get_settings.cache_clear()
        from testlyn_api.products.functional.runner import PlaywrightRunner

        runner = PlaywrightRunner()
        # Should not raise
        await runner.cancel(runner_id="docker-pw-abc")

    async def test_status_docker_returns_running(self):
        import os

        os.environ["RUN_MODE"] = "docker"
        from testlyn_api import config

        config.get_settings.cache_clear()
        from testlyn_api.products.functional.runner import PlaywrightRunner

        runner = PlaywrightRunner()
        status = await runner.status(runner_id="docker-pw-abc")
        assert status.state == "running"


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class TestSchemas:
    def test_functional_test_config_defaults(self):
        from testlyn_api.products.functional.schemas import FunctionalTestConfig

        cfg = FunctionalTestConfig(target_url="https://example.com", script_ts="// ts")
        assert cfg.viewport == {"width": 1280, "height": 720}
        assert cfg.timeouts["navigation"] == 30_000

    def test_generate_request_all_optional(self):
        from testlyn_api.products.functional.schemas import FunctionalGenerateRequest

        req = FunctionalGenerateRequest()
        assert req.prompt is None
        assert req.target_url is None

    def test_generate_response_model(self):
        from testlyn_api.products.functional.schemas import FunctionalGenerateResponse

        resp = FunctionalGenerateResponse(
            script_ts="import { test } from '@playwright/test';",
            locator_strategies=["data-testid", "ARIA"],
        )
        assert len(resp.locator_strategies) == 2
        assert resp.product == "functional"


# ---------------------------------------------------------------------------
# Steps
# ---------------------------------------------------------------------------


class TestSteps:
    def test_login_fragment_contains_selectors(self):
        from testlyn_api.products.functional.steps.login import fragment

        code = fragment()
        assert "email" in code
        assert "password" in code
        assert "await page.fill" in code

    def test_checkout_fragment(self):
        from testlyn_api.products.functional.steps.checkout import fragment

        code = fragment()
        assert "checkout" in code.lower()
        assert "await page.click" in code

    def test_form_submit_with_fields(self):
        from testlyn_api.products.functional.steps.form_submit import fragment

        code = fragment(fields={"#name": "Alice", "#email": "alice@example.com"})
        assert "#name" in code
        assert "Alice" in code

    def test_payment_fragment_has_card(self):
        from testlyn_api.products.functional.steps.payment import fragment

        code = fragment()
        assert "4242424242424242" in code


# ---------------------------------------------------------------------------
# Reports stub
# ---------------------------------------------------------------------------


class TestReports:
    async def test_build_functional_report_returns_gcs_uri(self):
        from testlyn_api.products.functional.reports import build_functional_report

        run_id = uuid.uuid4()
        result = await build_functional_report(run_id)
        assert str(run_id) in result.gcs_uri
        assert result.gcs_uri.startswith("gs://")
        assert result.page_count >= 1


# ---------------------------------------------------------------------------
# Gemini adapter — creds missing fallback
# ---------------------------------------------------------------------------


class TestFunctionalGemini:
    async def test_returns_template_on_missing_creds(self):
        import google.auth.exceptions

        with patch(
            "google.auth.default",
            side_effect=google.auth.exceptions.DefaultCredentialsError(),
        ):
            from testlyn_api.products.functional import _gemini

            script, strategies = await _gemini.generate_playwright_script(
                prompt="Test the homepage",
                prd_file=None,
                target_url="https://example.com",
            )

        assert "playwright" in script.lower() or "NOTE" in script
        assert isinstance(strategies, list)
        assert len(strategies) > 0

    async def test_returns_template_on_generic_exception(self):
        """Any unexpected exception from Vertex AI returns the fallback template."""
        with patch("google.auth.default", side_effect=RuntimeError("unexpected")):
            from testlyn_api.products.functional import _gemini

            script, strategies = await _gemini.generate_playwright_script(
                prompt=None,
                prd_file=None,
                target_url="https://example.com",
            )

        assert "NOTE" in script or "playwright" in script.lower()
        assert isinstance(strategies, list)


# ---------------------------------------------------------------------------
# Routes — /generate (integration via TestClient)
# ---------------------------------------------------------------------------


class TestGenerateRoute:
    async def test_generate_requires_at_least_one_field(self, client):
        resp = await client.post("/v1/products/functional/generate", json={})
        assert resp.status_code == 422

    async def test_generate_returns_script_on_target_url(self, client):
        import google.auth.exceptions

        with patch(
            "google.auth.default",
            side_effect=google.auth.exceptions.DefaultCredentialsError(),
        ):
            resp = await client.post(
                "/v1/products/functional/generate",
                json={"target_url": "https://example.com"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert "script_ts" in data
        assert isinstance(data["locator_strategies"], list)

    async def test_generate_with_prompt(self, client):
        import google.auth.exceptions

        with patch(
            "google.auth.default",
            side_effect=google.auth.exceptions.DefaultCredentialsError(),
        ):
            resp = await client.post(
                "/v1/products/functional/generate",
                json={"prompt": "Test the login flow", "target_url": "https://app.example.com"},
            )

        assert resp.status_code == 200
