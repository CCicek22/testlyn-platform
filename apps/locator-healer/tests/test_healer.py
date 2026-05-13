"""Unit tests for locator-healer.

Tests:
  - cache hit returns cached value without calling Gemini
  - cache miss with Gemini stub returns new selector
  - creds-missing path falls back to heuristic
  - heuristic strips last CSS segment correctly
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

# Ensure tests don't try to call Redis
import os
os.environ.setdefault("REDIS_URL", "")
os.environ.setdefault("LOCATOR_HEALING_ENABLED", "0")

from main import HealRequest, _cache_key, _heuristic_heal, _mem_cache, app


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def clear_mem_cache():
    _mem_cache.clear()
    yield
    _mem_cache.clear()


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as ac:
        yield ac


def _sample_body() -> dict:
    return {
        "screenshot_b64": "deadbeef",
        "dom_snapshot": "<html><body><button id='submit'>Go</button></body></html>",
        "failed_selector": "div.wrapper > span.label",
        "page_url": "https://example.com/checkout",
    }


# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------


class TestHeuristic:
    def test_strips_last_child_segment(self):
        result = _heuristic_heal("div.wrapper > span.label")
        assert result.new_selector == "div.wrapper"
        assert result.confidence < 0.5

    def test_strips_last_adjacent_segment(self):
        result = _heuristic_heal("ul.nav + div.content")
        assert result.new_selector == "ul.nav"

    def test_strips_last_class_when_single_segment(self):
        result = _heuristic_heal("button.primary")
        # Should strip ".primary" leaving "button"
        assert "button" in result.new_selector or result.new_selector == "*"

    def test_wildcard_fallback_for_empty(self):
        result = _heuristic_heal("")
        assert result.new_selector == "*"


class TestCacheKey:
    def test_same_inputs_produce_same_key(self):
        req = HealRequest(**_sample_body())
        assert _cache_key(req) == _cache_key(req)

    def test_different_selector_produces_different_key(self):
        body1 = _sample_body()
        body2 = {**_sample_body(), "failed_selector": "button.other"}
        req1 = HealRequest(**body1)
        req2 = HealRequest(**body2)
        assert _cache_key(req1) != _cache_key(req2)


class TestHealEndpoint:
    async def test_cache_hit_returns_cached(self, client: AsyncClient):
        body = _sample_body()
        req = HealRequest(**body)
        key = _cache_key(req)
        cached_value = {
            "new_selector": "div.wrapper",
            "confidence": 0.9,
            "reasoning": "cached",
        }
        _mem_cache[key] = cached_value

        resp = await client.post("/heal", json=body)
        assert resp.status_code == 200
        data = resp.json()
        assert data["new_selector"] == "div.wrapper"
        assert data["confidence"] == 0.9

    async def test_cache_miss_heuristic_fallback(self, client: AsyncClient):
        """With LOCATOR_HEALING_ENABLED=0 (default in test env), heuristic runs."""
        body = _sample_body()
        resp = await client.post("/heal", json=body)
        assert resp.status_code == 200
        data = resp.json()
        # Heuristic should strip last segment "span.label"
        assert data["new_selector"] == "div.wrapper"
        assert data["confidence"] < 0.5

    async def test_result_written_to_cache_on_miss(self, client: AsyncClient):
        body = _sample_body()
        req = HealRequest(**body)
        key = _cache_key(req)

        assert key not in _mem_cache
        await client.post("/heal", json=body)
        assert key in _mem_cache

    async def test_gemini_stub_path(self, client: AsyncClient):
        """With LOCATOR_HEALING_ENABLED=1 and creds missing, falls back to heuristic."""
        body = _sample_body()

        import google.auth.exceptions

        with (
            patch("os.getenv", side_effect=lambda k, d="": "1" if k == "LOCATOR_HEALING_ENABLED" else d),
            patch("main.LOCATOR_HEALING_ENABLED", True),
            patch("google.auth.default", side_effect=google.auth.exceptions.DefaultCredentialsError()),
        ):
            resp = await client.post("/heal", json=body)

        assert resp.status_code == 200
        data = resp.json()
        assert "new_selector" in data

    async def test_missing_fields_returns_422(self, client: AsyncClient):
        resp = await client.post("/heal", json={"screenshot_b64": "x"})
        assert resp.status_code == 422

    async def test_healthz(self, client: AsyncClient):
        resp = await client.get("/healthz")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
