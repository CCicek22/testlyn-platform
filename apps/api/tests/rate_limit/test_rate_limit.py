"""Tests for RateLimiter and RateLimitMiddleware."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient

from testlyn_api.core.rate_limit import (
    TIER_RPM,
    RateLimiter,
    RateLimitMiddleware,
    _InMemoryBucket,
)


# --------------------------------------------------------------------------- #
# _InMemoryBucket                                                               #
# --------------------------------------------------------------------------- #
class TestInMemoryBucket:
    def test_allows_up_to_limit(self) -> None:
        bucket = _InMemoryBucket()
        limit = 5
        for _ in range(limit):
            allowed, _ = bucket.check("k", limit)
            assert allowed

    def test_blocks_over_limit(self) -> None:
        bucket = _InMemoryBucket()
        limit = 3
        for _ in range(limit):
            bucket.check("k", limit)
        allowed, remaining = bucket.check("k", limit)
        assert not allowed
        assert remaining == 0

    def test_different_keys_independent(self) -> None:
        bucket = _InMemoryBucket()
        limit = 2
        # exhaust key A
        for _ in range(limit):
            bucket.check("A", limit)
        # key B should still pass
        allowed, _ = bucket.check("B", limit)
        assert allowed

    def test_remaining_decreases(self) -> None:
        bucket = _InMemoryBucket()
        _, r0 = bucket.check("x", 10)
        _, r1 = bucket.check("x", 10)
        assert r1 < r0


# --------------------------------------------------------------------------- #
# RateLimiter (unit, mocked Redis)                                             #
# --------------------------------------------------------------------------- #
class TestRateLimiter:
    @pytest.mark.asyncio
    async def test_falls_back_to_in_memory_when_redis_unavailable(self) -> None:
        limiter = RateLimiter()
        with patch.object(limiter, "_get_redis", new=AsyncMock(return_value=None)):
            allowed, remaining = await limiter.check("org-abc", "free")
        assert allowed  # first call always allowed

    @pytest.mark.asyncio
    async def test_redis_success_path(self) -> None:
        limiter = RateLimiter()
        mock_redis = AsyncMock()
        mock_redis.evalsha = AsyncMock(return_value=[1, 59])
        limiter._redis = mock_redis
        limiter._script_sha = "fake-sha"
        allowed, remaining = await limiter.check("org-xyz", "free")
        assert allowed
        assert remaining == 59

    @pytest.mark.asyncio
    async def test_redis_denied(self) -> None:
        limiter = RateLimiter()
        mock_redis = AsyncMock()
        mock_redis.evalsha = AsyncMock(return_value=[0, 0])
        limiter._redis = mock_redis
        limiter._script_sha = "fake-sha"
        allowed, remaining = await limiter.check("org-xyz", "pro")
        assert not allowed
        assert remaining == 0

    @pytest.mark.asyncio
    async def test_tier_limits_values(self) -> None:
        assert TIER_RPM["free"] == 60
        assert TIER_RPM["hobby"] == 600
        assert TIER_RPM["pro"] == 6_000
        assert TIER_RPM["business"] == 60_000

    @pytest.mark.asyncio
    async def test_unknown_plan_defaults_to_free(self) -> None:
        limiter = RateLimiter()
        with patch.object(limiter, "_get_redis", new=AsyncMock(return_value=None)):
            allowed, _ = await limiter.check("org-1", "enterprise_plus_unknown")
        assert allowed  # first call should pass at free tier


# --------------------------------------------------------------------------- #
# RateLimitMiddleware integration                                               #
# --------------------------------------------------------------------------- #
def _make_app(mock_limiter: RateLimiter | None = None) -> FastAPI:
    app = FastAPI()
    app.add_middleware(RateLimitMiddleware, limiter=mock_limiter)

    @app.get("/v1/tests")
    async def list_tests() -> dict:
        return {"items": []}

    @app.get("/healthz")
    async def health() -> dict:
        return {"status": "ok"}

    return app


@pytest.mark.asyncio
async def test_non_v1_route_not_rate_limited() -> None:
    limiter = MagicMock(spec=RateLimiter)
    app = _make_app(limiter)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/healthz")
    assert resp.status_code == 200
    limiter.check.assert_not_called()


@pytest.mark.asyncio
async def test_v1_route_passes_when_allowed() -> None:
    limiter = AsyncMock(spec=RateLimiter)
    limiter.check = AsyncMock(return_value=(True, 59))
    app = _make_app(limiter)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/v1/tests")
    assert resp.status_code == 200
    assert resp.headers["X-RateLimit-Limit"] == "60"
    assert resp.headers["X-RateLimit-Remaining"] == "59"


@pytest.mark.asyncio
async def test_v1_route_429_when_denied() -> None:
    limiter = AsyncMock(spec=RateLimiter)
    limiter.check = AsyncMock(return_value=(False, 0))
    app = _make_app(limiter)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/v1/tests")
    assert resp.status_code == 429
    assert "Retry-After" in resp.headers
    assert resp.headers["X-RateLimit-Remaining"] == "0"


@pytest.mark.asyncio
async def test_x_api_key_header_used_as_identity() -> None:
    """Middleware should use X-Api-Key prefix as the rate-limit key."""
    calls: list[str] = []

    class TrackingLimiter(RateLimiter):
        async def check(self, org_id: str, plan: str) -> tuple[bool, int]:
            calls.append(org_id)
            return True, 59

    app = _make_app(TrackingLimiter())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.get("/v1/tests", headers={"X-Api-Key": "testkey1234567890"})

    assert len(calls) == 1
    assert calls[0].startswith("apikey:")
