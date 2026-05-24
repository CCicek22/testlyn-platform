from __future__ import annotations

import pytest
from httpx import AsyncClient

_VALID_STATUS = {"operational", "degraded", "outage", "maintenance"}
_EXPECTED_COMPONENT_IDS = {"api", "web", "engine", "bq", "auth", "storage"}


@pytest.mark.asyncio
async def test_public_status_returns_200_no_auth(client: AsyncClient) -> None:
    # No Authorization header — endpoint is public.
    resp = await client.get("/v1/public/status")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_public_status_schema_shape(client: AsyncClient) -> None:
    resp = await client.get("/v1/public/status")
    body = resp.json()

    assert set(body.keys()) == {"overall", "components", "incidents", "fetched_at"}
    assert body["overall"] in _VALID_STATUS
    assert isinstance(body["fetched_at"], str)

    assert isinstance(body["incidents"], list)
    assert body["incidents"] == []

    component_ids = {c["id"] for c in body["components"]}
    assert component_ids == _EXPECTED_COMPONENT_IDS
    for comp in body["components"]:
        assert set(comp.keys()) <= {"id", "name", "status", "uptime_90d"}
        assert {"id", "name", "status"} <= set(comp.keys())
        assert comp["status"] in _VALID_STATUS
        # uptime_90d is omitted — we do not fabricate uptime percentages.
        assert "uptime_90d" not in comp


@pytest.mark.asyncio
async def test_public_status_overall_operational_when_all_up(client: AsyncClient) -> None:
    resp = await client.get("/v1/public/status")
    body = resp.json()
    assert body["overall"] == "operational"
    assert all(c["status"] == "operational" for c in body["components"])
