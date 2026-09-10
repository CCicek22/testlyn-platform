from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from httpx import ASGITransport, AsyncClient

from testlyn_api.config import Settings
from testlyn_api.main import app


def test_cors_allowed_origins_fallback_when_empty() -> None:
    """Property falls back to [web_base_url] when raw is empty."""
    s = Settings(
        cors_allowed_origins_raw="", web_base_url="https://dev.testlyn.example.com"
    )
    assert s.cors_allowed_origins == ["https://dev.testlyn.example.com"]


def test_cors_allowed_origins_fallback_when_only_commas_or_whitespace() -> None:
    """Property falls back to [web_base_url] when raw has only empty elements."""
    s = Settings(
        cors_allowed_origins_raw="  , ,   ",
        web_base_url="https://dev.testlyn.example.com",
    )
    assert s.cors_allowed_origins == ["https://dev.testlyn.example.com"]


def test_cors_allowed_origins_parse_strip_dedup_preserve_order() -> None:
    """Property splits on comma, strips whitespace, drops empties, and dedupes preserving order."""
    raw = " https://dev.testlyn.example.com , https://testlyn.example.com , https://dev.testlyn.example.com , "
    s = Settings(cors_allowed_origins_raw=raw)
    assert s.cors_allowed_origins == [
        "https://dev.testlyn.example.com",
        "https://testlyn.example.com",
    ]


@pytest.mark.asyncio
async def test_cors_preflight_asgi_allowed_and_disallowed() -> None:
    """ASGI-level preflight test: OPTIONS /v1/me returns 200 for allowed origins, 400 for disallowed."""
    test_app = FastAPI()
    test_settings = Settings(
        cors_allowed_origins_raw="https://dev.testlyn.example.com,https://testlyn.example.com",
        web_base_url="https://dev.testlyn.example.com",
    )
    test_app.add_middleware(
        CORSMiddleware,
        allow_origins=test_settings.cors_allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @test_app.get("/v1/me")
    async def me() -> dict[str, str]:
        return {"status": "ok"}

    async with AsyncClient(
        transport=ASGITransport(app=test_app), base_url="http://testserver"
    ) as client:
        # Preflight from apex origin -> allowed
        resp_apex = await client.options(
            "/v1/me",
            headers={
                "Origin": "https://testlyn.example.com",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "authorization",
            },
        )
        assert resp_apex.status_code == 200
        assert (
            resp_apex.headers.get("access-control-allow-origin")
            == "https://testlyn.example.com"
        )
        assert resp_apex.headers.get("access-control-allow-credentials") == "true"

        # Preflight from dev origin -> allowed
        resp_dev = await client.options(
            "/v1/me",
            headers={
                "Origin": "https://dev.testlyn.example.com",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "authorization",
            },
        )
        assert resp_dev.status_code == 200
        assert (
            resp_dev.headers.get("access-control-allow-origin")
            == "https://dev.testlyn.example.com"
        )

        # Preflight from unknown origin -> rejected with 400 Disallowed CORS origin
        resp_bad = await client.options(
            "/v1/me",
            headers={
                "Origin": "https://malicious.example.com",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "authorization",
            },
        )
        assert resp_bad.status_code == 400
        assert "access-control-allow-origin" not in resp_bad.headers


@pytest.mark.asyncio
async def test_main_app_cors_preflight_uses_configured_origins() -> None:
    """Verify the main FastAPI app responds to preflight matching its configured settings."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        # In test environment, CORS_ALLOWED_ORIGINS_RAW defaults to empty -> web_base_url (http://localhost:3000)
        resp = await client.options(
            "/v1/me",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "authorization",
            },
        )
        assert resp.status_code == 200
        assert (
            resp.headers.get("access-control-allow-origin") == "http://localhost:3000"
        )

        # Disallowed origin on main app
        resp_blocked = await client.options(
            "/v1/me",
            headers={
                "Origin": "https://disallowed.example.com",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "authorization",
            },
        )
        assert resp_blocked.status_code == 400


@pytest.mark.asyncio
async def test_main_app_honours_configured_apex_origin(monkeypatch) -> None:
    """Guard the wiring itself.

    In the test environment ``cors_allowed_origins`` and ``[web_base_url]`` both
    resolve to http://localhost:3000, so every other test in this file stays
    green even if ``main.py`` is reverted to the single-origin list. This one
    sets the env var and rebuilds the module, so it fails if the CORS allowlist
    stops reading CORS_ALLOWED_ORIGINS_RAW.

    Reloading ``main`` re-runs its module-level ``structlog.configure()``, which
    would otherwise clobber the log capture the rest of the suite relies on, so
    the structlog config is snapshotted and restored around the reload.
    """
    import importlib

    import structlog

    import testlyn_api.config as config_mod
    import testlyn_api.main as main_mod

    structlog_config = structlog.get_config()
    monkeypatch.setenv(
        "CORS_ALLOWED_ORIGINS_RAW",
        "http://localhost:3000,https://testlyn.example.com",
    )
    config_mod.get_settings.cache_clear()
    try:
        reloaded = importlib.reload(main_mod)
        async with AsyncClient(
            transport=ASGITransport(app=reloaded.app), base_url="http://testserver"
        ) as client:
            resp = await client.options(
                "/v1/me",
                headers={
                    "Origin": "https://testlyn.example.com",
                    "Access-Control-Request-Method": "GET",
                    "Access-Control-Request-Headers": "authorization",
                },
            )
        assert resp.status_code == 200, (
            "main.py's CORSMiddleware is not reading settings.cors_allowed_origins"
        )
        assert (
            resp.headers.get("access-control-allow-origin")
            == "https://testlyn.example.com"
        )
    finally:
        monkeypatch.delenv("CORS_ALLOWED_ORIGINS_RAW", raising=False)
        config_mod.get_settings.cache_clear()
        importlib.reload(main_mod)
        structlog.configure(**structlog_config)
