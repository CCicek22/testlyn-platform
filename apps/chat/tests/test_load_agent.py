"""Unit tests for load-product tools.

We test the thin httpx wrappers directly — invoking via the LLM is covered
by the integration suite. Each tool gets called with a stubbed
ToolContext-shaped object so we don't need to spin a full ADK Runner.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import httpx
import pytest

from testlyn_chat.tools import load_tools
from testlyn_chat.tools._helpers import SESSION_KEY_USER_TOKEN
from testlyn_chat.tools.testlyn_client import TestlynClient


@dataclass
class _FakeState:
    data: dict[str, Any] = field(default_factory=dict)

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)


@dataclass
class _FakeToolContext:
    state: _FakeState = field(default_factory=_FakeState)


def _ctx_with_token(token: str = "fake-token") -> _FakeToolContext:
    return _FakeToolContext(state=_FakeState({SESSION_KEY_USER_TOKEN: token}))


def _patched_client(monkeypatch: pytest.MonkeyPatch, transport: httpx.MockTransport) -> None:
    """Force TestlynClient to use a MockTransport-backed httpx.AsyncClient."""
    orig_init = TestlynClient.__init__

    def patched_init(self: TestlynClient, *, user_token: str, **kwargs: Any) -> None:
        raw = httpx.AsyncClient(
            transport=transport,
            base_url="http://api.test",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        orig_init(self, user_token=user_token, client=raw)

    monkeypatch.setattr(TestlynClient, "__init__", patched_init)


@pytest.mark.asyncio
async def test_run_load_test_returns_ok_envelope(monkeypatch: pytest.MonkeyPatch) -> None:
    called: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        called["path"] = request.url.path
        called["method"] = request.method
        return httpx.Response(201, json={"id": "run-xyz", "status": "queued"})

    _patched_client(monkeypatch, httpx.MockTransport(handler))

    tid = "11111111-1111-4111-8111-111111111111"
    result = await load_tools.run_load_test(
        test_id=tid,
        tool_context=_ctx_with_token(),  # type: ignore[arg-type]
    )

    assert result == {
        "ok": True,
        "data": {"id": "run-xyz", "status": "queued"},
    }
    assert called["method"] == "POST"
    assert called["path"] == f"/v1/tests/{tid}/runs"


@pytest.mark.asyncio
async def test_list_load_runs_filters_by_product(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["params"] = dict(request.url.params)
        return httpx.Response(200, json=[{"id": "r1"}, {"id": "r2"}])

    _patched_client(monkeypatch, httpx.MockTransport(handler))

    result = await load_tools.list_load_runs(
        tool_context=_ctx_with_token(),  # type: ignore[arg-type]
        limit=5,
        status="succeeded",
    )

    assert result["ok"] is True
    assert len(result["data"]) == 2
    assert captured["params"]["product"] == "load"
    assert captured["params"]["status"] == "succeeded"
    assert captured["params"]["limit"] == "5"


@pytest.mark.asyncio
async def test_get_run_summary_surfaces_404_cleanly(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"detail": "Run not found"})

    _patched_client(monkeypatch, httpx.MockTransport(handler))

    result = await load_tools.get_run_summary(
        run_id="11111111-1111-4111-8111-111111111111",
        tool_context=_ctx_with_token(),  # type: ignore[arg-type]
    )

    assert result == {"ok": False, "status": 404, "error": {"detail": "Run not found"}}


@pytest.mark.asyncio
async def test_get_run_summary_rejects_invalid_uuid() -> None:
    with pytest.raises(ValueError, match="invalid run_id"):
        await load_tools.get_run_summary(
            run_id="nope",
            tool_context=_ctx_with_token(),  # type: ignore[arg-type]
        )


@pytest.mark.asyncio
async def test_missing_user_token_raises() -> None:
    empty_ctx = _FakeToolContext()  # no token in state
    with pytest.raises(PermissionError):
        await load_tools.list_load_runs(
            tool_context=empty_ctx,  # type: ignore[arg-type]
        )
