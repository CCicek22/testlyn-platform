"""OpenAPI docs gate (EXPOSE_DOCS / settings.expose_docs)."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from testlyn_api.config import Settings
from testlyn_api.main import _docs_kwargs


def _build_app(*, expose_docs: bool) -> FastAPI:
    """Build a FastAPI using the SAME gating as main.py (real _docs_kwargs)."""
    settings = Settings(expose_docs=expose_docs)
    return FastAPI(title="t", version="0", **_docs_kwargs(settings))


@pytest.mark.asyncio
async def test_docs_disabled_when_expose_docs_false() -> None:
    app = _build_app(expose_docs=False)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        assert (await client.get("/openapi.json")).status_code == 404
        assert (await client.get("/docs")).status_code == 404
        assert (await client.get("/redoc")).status_code == 404


@pytest.mark.asyncio
async def test_docs_enabled_when_expose_docs_true() -> None:
    app = _build_app(expose_docs=True)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        assert (await client.get("/docs")).status_code == 200
        assert (await client.get("/openapi.json")).status_code == 200


def test_docs_kwargs_true_keeps_urls() -> None:
    kw = _docs_kwargs(Settings(expose_docs=True))
    assert kw["docs_url"] == "/docs"
    assert kw["redoc_url"] == "/redoc"
    assert "openapi_url" not in kw  # default openapi_url preserved


def test_docs_kwargs_false_nulls_all_three() -> None:
    kw = _docs_kwargs(Settings(expose_docs=False))
    assert kw == {"docs_url": None, "redoc_url": None, "openapi_url": None}
