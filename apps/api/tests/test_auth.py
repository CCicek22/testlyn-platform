from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_me_no_auth_bypass_returns_401(client: AsyncClient, monkeypatch) -> None:
    """Without bypass, missing auth header returns 401."""

    monkeypatch.setenv("DEV_AUTH_BYPASS", "false")

    # Reset settings cache so it picks up new env
    from testlyn_api import config as cfg_module

    cfg_module.get_settings.cache_clear()

    response = await client.get("/v1/me")
    assert response.status_code == 401

    # Restore
    cfg_module.get_settings.cache_clear()


@pytest.mark.asyncio
async def test_me_with_dev_bypass_returns_200(client: AsyncClient) -> None:
    response = await client.get("/v1/me")
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "dev@testlyn.io"
    assert "memberships" in data


@pytest.mark.asyncio
async def test_me_idempotent(client: AsyncClient) -> None:
    """Second call to /v1/me with bypass should not error (seed is idempotent)."""
    r1 = await client.get("/v1/me")
    r2 = await client.get("/v1/me")
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r1.json()["id"] == r2.json()["id"]
