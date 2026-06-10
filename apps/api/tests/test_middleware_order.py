"""Middleware ordering: CORS must be OUTERMOST.

Starlette runs the LAST ``add_middleware`` as the outermost layer. If the
rate-limit / IP-allowlist middleware sit outside CORS, their 429/403 responses
lack CORS headers and the browser surfaces an opaque network error instead of
the real status.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.middleware.cors import CORSMiddleware
from httpx import AsyncClient

from testlyn_api.main import app


def test_cors_is_outermost_middleware() -> None:
    # Starlette: last add_middleware → index 0 in user_middleware → outermost.
    assert app.user_middleware[0].cls is CORSMiddleware


@pytest.mark.asyncio
async def test_ip_allowlist_403_carries_cors_headers(
    client: AsyncClient, dev_org_id
) -> None:
    """A middleware-generated 403 must still pass through CORS (outermost)."""
    from testlyn_api.core.ip_allowlist import invalidate_cache

    invalidate_cache(str(dev_org_id))
    with (
        patch(
            "testlyn_api.core.token_verify.verify_token",
            new=AsyncMock(return_value={"uid": "member-uid", "email": "m@x.com"}),
        ),
        patch(
            "testlyn_api.core.org_context.resolve_org_and_plan",
            new=AsyncMock(return_value=(str(dev_org_id), "pro")),
        ),
        patch(
            "testlyn_api.core.ip_allowlist._load_cidrs",
            new=AsyncMock(return_value=["10.0.0.0/8"]),
        ),
    ):
        resp = await client.get(
            "/v1/tests",
            headers={
                "Authorization": "Bearer fake.jwt.token",
                "X-Forwarded-For": "1.2.3.4",  # outside 10.0.0.0/8 → denied
                "Origin": "http://localhost:3000",  # settings.web_base_url in tests
            },
        )

    assert resp.status_code == 403
    assert resp.headers.get("access-control-allow-origin") == "http://localhost:3000"
