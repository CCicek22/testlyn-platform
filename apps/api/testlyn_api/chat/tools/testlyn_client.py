"""Thin async httpx wrapper around testlyn-api `/v1/*`.

The chat service NEVER owns business logic — every tool call boils down to
one or more HTTP calls into testlyn-api with the user's Firebase token. This
preserves the API's existing auth, audit, rate-limit, and quota guarantees.

Usage:
    client = TestlynClient(user_token=...)
    runs = await client.get("/v1/runs", params={"limit": 10})
    await client.aclose()

Prefer the async-context-manager form in tools:
    async with TestlynClient(user_token=token) as client:
        ...
"""

from __future__ import annotations

from typing import Any

import httpx
import structlog

from testlyn_api.config import get_settings

log = structlog.get_logger(__name__)


class TestlynAPIError(Exception):
    """Raised when testlyn-api returns a non-2xx response.

    Attributes:
        status_code: HTTP status from upstream.
        body: Parsed JSON body (if any), else the raw text.
    """

    __test__ = False  # pytest: not a test class

    def __init__(
        self, status_code: int, body: Any, *, message: str | None = None
    ) -> None:
        self.status_code = status_code
        self.body = body
        super().__init__(message or f"testlyn-api {status_code}: {body}")


class TestlynClient:
    """User-scoped HTTP client for testlyn-api.

    `user_token` MUST be a valid Firebase ID token belonging to the end user
    making the chat request — never a service-account credential. All upstream
    calls are made on the user's behalf so per-org RBAC + audit log fire.
    """

    __test__ = False  # pytest: not a test class

    def __init__(
        self,
        *,
        user_token: str,
        base_url: str | None = None,
        timeout: float | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        settings = get_settings()
        self._base_url = (base_url or settings.chat_api_base).rstrip("/")
        self._user_token = user_token
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            base_url=self._base_url,
            timeout=httpx.Timeout(
                timeout or settings.chat_upstream_timeout_s,
                connect=settings.chat_upstream_connect_timeout_s,
            ),
            headers={
                "Authorization": f"Bearer {user_token}",
                "Accept": "application/json",
                "User-Agent": "testlyn-api-chat/0.1.0",
            },
        )

    async def __aenter__(self) -> TestlynClient:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    # ---- Verb helpers -------------------------------------------------------

    async def get(self, path: str, *, params: dict[str, Any] | None = None) -> Any:
        return await self._request("GET", path, params=params)

    async def post(
        self,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> Any:
        return await self._request("POST", path, json=json, params=params)

    async def patch(self, path: str, *, json: dict[str, Any] | None = None) -> Any:
        return await self._request("PATCH", path, json=json)

    async def delete(self, path: str) -> Any:
        return await self._request("DELETE", path)

    # ---- Core ---------------------------------------------------------------

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> Any:
        try:
            resp = await self._client.request(method, path, json=json, params=params)
        except httpx.HTTPError as exc:
            log.warning(
                "testlyn_client.transport_error",
                method=method,
                path=path,
                error=str(exc),
            )
            raise TestlynAPIError(0, None, message=f"transport: {exc}") from exc

        if resp.status_code >= 400:
            body: Any
            try:
                body = resp.json()
            except ValueError:
                body = resp.text
            log.info(
                "testlyn_client.error_response",
                method=method,
                path=path,
                status=resp.status_code,
            )
            raise TestlynAPIError(resp.status_code, body)

        if resp.status_code == 204 or not resp.content:
            return None
        try:
            return resp.json()
        except ValueError:
            return resp.text
