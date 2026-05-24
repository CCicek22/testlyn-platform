"""Unit tests for the chat -> testlyn-api HTTP wrapper."""

from __future__ import annotations

import httpx
import pytest

from testlyn_api.chat.tools.testlyn_client import TestlynAPIError, TestlynClient


@pytest.mark.asyncio
async def test_get_returns_json_on_2xx() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer fake-token"
        assert request.url.path == "/v1/runs"
        return httpx.Response(200, json=[{"id": "abc"}])

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://api.test",
        headers={"Authorization": "Bearer fake-token"},
    ) as raw:
        client = TestlynClient(user_token="fake-token", client=raw)
        data = await client.get("/v1/runs")

    assert data == [{"id": "abc"}]


@pytest.mark.asyncio
async def test_post_serialises_json_body() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = request.content.decode()
        return httpx.Response(201, json={"id": "run-1"})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://api.test",
        headers={"Authorization": "Bearer fake-token"},
    ) as raw:
        client = TestlynClient(user_token="fake-token", client=raw)
        data = await client.post("/v1/tests/123/runs", json={"foo": "bar"})

    assert data == {"id": "run-1"}
    assert "foo" in captured["body"]


@pytest.mark.asyncio
async def test_error_response_raises_testlyn_api_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"detail": "missing"})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://api.test",
        headers={"Authorization": "Bearer x"},
    ) as raw:
        client = TestlynClient(user_token="x", client=raw)
        with pytest.raises(TestlynAPIError) as excinfo:
            await client.get("/v1/runs/missing")

    assert excinfo.value.status_code == 404
    assert excinfo.value.body == {"detail": "missing"}


@pytest.mark.asyncio
async def test_transport_error_wraps_to_testlyn_api_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://api.test",
        headers={"Authorization": "Bearer x"},
    ) as raw:
        client = TestlynClient(user_token="x", client=raw)
        with pytest.raises(TestlynAPIError) as excinfo:
            await client.get("/v1/runs")

    assert excinfo.value.status_code == 0


@pytest.mark.asyncio
async def test_204_returns_none() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(204)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://api.test",
        headers={"Authorization": "Bearer x"},
    ) as raw:
        client = TestlynClient(user_token="x", client=raw)
        result = await client.delete("/v1/something")

    assert result is None
