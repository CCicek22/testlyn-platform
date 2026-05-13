from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

# fakeredis must be imported before service to allow patching
import fakeredis.aioredis as fakeredis_async
import pytest


@pytest.fixture(autouse=True)
def patch_redis(monkeypatch):
    """Replace the real Redis client with a fakeredis instance for all gemini tests."""
    fake = fakeredis_async.FakeRedis(decode_responses=True)

    def _get_fake_redis():
        return fake

    monkeypatch.setattr("testlyn_api.core.cache._client", None)
    with patch("testlyn_api.core.cache.get_redis", return_value=fake):
        yield fake


class TestSummarizeRun:
    async def test_returns_canned_on_missing_creds(self, patch_redis):
        """When google.auth.default raises DefaultCredentialsError, return canned text."""
        import google.auth.exceptions

        with patch("google.auth.default", side_effect=google.auth.exceptions.DefaultCredentialsError()):
            from testlyn_api.services import gemini

            result = await gemini.summarize_run(
                "run-123",
                {"p95": 500, "errors": 0},
                sample_size_hint=1000,
            )

        assert "Vertex AI" in result
        assert "credentials" in result.lower() or "creds" in result.lower()

    async def test_logs_warning_on_missing_creds(self, patch_redis, caplog):
        """structured warning must be emitted when creds missing."""
        import google.auth.exceptions
        import structlog.testing

        with structlog.testing.capture_logs() as logs:
            with patch("google.auth.default", side_effect=google.auth.exceptions.DefaultCredentialsError()):
                from testlyn_api.services import gemini

                await gemini.summarize_run("run-999", {}, sample_size_hint=0)

        events = [entry.get("event") for entry in logs]
        assert "vertex_creds_missing" in events

    async def test_calls_vertex_and_returns_text(self, patch_redis):
        """Happy path: aiplatform client called and text returned."""
        mock_response = MagicMock()
        mock_response.text = "Three paragraphs of insight."

        mock_model = MagicMock()
        mock_model.generate_content_async = AsyncMock(return_value=mock_response)

        mock_credentials = MagicMock()

        with (
            patch("google.auth.default", return_value=(mock_credentials, "proj")),
            patch("google.cloud.aiplatform.init"),
            patch("vertexai.generative_models.GenerativeModel", return_value=mock_model),
        ):
            from importlib import reload

            from testlyn_api.services import gemini

            reload(gemini)

            result = await gemini.summarize_run(
                "run-abc",
                {"p95": 200},
                sample_size_hint=500,
            )

        assert result == "Three paragraphs of insight."

    async def test_result_cached_on_second_call(self, patch_redis):
        """Second call with same inputs should NOT call vertex again."""
        mock_response = MagicMock()
        mock_response.text = "Cached insight."

        mock_model = MagicMock()
        mock_model.generate_content_async = AsyncMock(return_value=mock_response)
        mock_credentials = MagicMock()

        with (
            patch("google.auth.default", return_value=(mock_credentials, "proj")),
            patch("google.cloud.aiplatform.init"),
            patch("vertexai.generative_models.GenerativeModel", return_value=mock_model),
        ):
            from importlib import reload

            from testlyn_api.services import gemini

            reload(gemini)

            await gemini.summarize_run("run-cache", {"p95": 100}, sample_size_hint=50)
            await gemini.summarize_run("run-cache", {"p95": 100}, sample_size_hint=50)

        assert mock_model.generate_content_async.call_count == 1


class TestExplainBottleneck:
    async def test_returns_canned_on_missing_creds(self, patch_redis):
        import google.auth.exceptions

        with patch("google.auth.default", side_effect=google.auth.exceptions.DefaultCredentialsError()):
            from testlyn_api.services import gemini

            result = await gemini.explain_bottleneck({"p99_ms": 5000})

        assert "Vertex AI" in result
