"""Unit tests for load-product chat tools.

We test the thin httpx wrappers directly — invoking via the LLM is covered
by the integration suite. Each tool gets called with a stubbed
ToolContext-shaped object so we don't need to spin a full ADK Runner.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import httpx
import pytest

from testlyn_api.chat.tools import load_tools, org_tools
from testlyn_api.chat.tools._helpers import (
    SESSION_KEY_PROJECT_ID,
    SESSION_KEY_USER_TOKEN,
)
from testlyn_api.chat.tools.testlyn_client import TestlynClient

_PROJECT_UUID = "22e6855a-7768-4a81-9baf-090303783781"


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


def _ctx_with_active_project(project_id: str = _PROJECT_UUID) -> _FakeToolContext:
    return _FakeToolContext(
        state=_FakeState(
            {SESSION_KEY_USER_TOKEN: "fake-token", SESSION_KEY_PROJECT_ID: project_id}
        )
    )


def _patched_client(
    monkeypatch: pytest.MonkeyPatch, transport: httpx.MockTransport
) -> None:
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
async def test_run_load_test_returns_ok_envelope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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
async def test_list_load_runs_filters_by_product(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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
async def test_get_run_summary_surfaces_404_cleanly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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
    # A non-UUID arg must return a structured {"ok": False} error, NOT raise.
    # A raised exception would bubble past the chat route and abort the whole
    # SSE stream as "internal error" (the live bug).
    result = await load_tools.get_run_summary(
        run_id="nope",
        tool_context=_ctx_with_token(),  # type: ignore[arg-type]
    )
    assert result["ok"] is False
    assert "run_id" in result["error"]


@pytest.mark.asyncio
async def test_list_load_tests_bad_project_id_returns_graceful_error() -> None:
    # Reproduces the operator's live chat crash: the LLM passed a target
    # hostname as project_id ("campus.example.com"). Validation must short-circuit
    # to a graceful error BEFORE touching the http client — so this works even
    # with no token in the context.
    result = await load_tools.list_load_tests(
        project_id="campus.example.com",
        tool_context=_FakeToolContext(),  # type: ignore[arg-type]  # no token needed
    )
    assert result == {"ok": False, "error": "invalid project_id: must be a UUID-4"}


@pytest.mark.asyncio
async def test_missing_user_token_raises() -> None:
    empty_ctx = _FakeToolContext()  # no token in state
    with pytest.raises(PermissionError):
        await load_tools.list_load_runs(
            tool_context=empty_ctx,  # type: ignore[arg-type]
        )


@pytest.mark.asyncio
async def test_create_load_test_creates_test_and_launches_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The operator's "run a 50 VU load test on <url>" path: one tool creates
    the test (with a generated k6 script) and immediately launches a run."""
    calls: list[tuple[str, str, dict[str, Any]]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else {}
        calls.append((request.method, request.url.path, body))
        if request.url.path == f"/v1/projects/{_PROJECT_UUID}/tests":
            return httpx.Response(201, json={"id": "test-abc", "name": body["name"]})
        if request.url.path == "/v1/tests/test-abc/runs":
            return httpx.Response(201, json={"id": "run-xyz", "status": "queued"})
        return httpx.Response(404, json={"detail": "unexpected path"})

    _patched_client(monkeypatch, httpx.MockTransport(handler))

    result = await load_tools.create_load_test(
        target_url="campus.example.com/",
        vus=50,
        tool_context=_ctx_with_active_project(),  # type: ignore[arg-type]
    )

    assert result["ok"] is True
    assert result["data"]["run"] == {"id": "run-xyz", "status": "queued"}
    # test created under the active project, then run launched
    assert calls[0][1] == f"/v1/projects/{_PROJECT_UUID}/tests"
    assert calls[1] == ("POST", "/v1/tests/test-abc/runs", {})
    test_body = calls[0][2]
    assert test_body["product"] == "load"
    assert test_body["config"] == {"vus": 50, "duration_seconds": 30}
    # scheme defaulted to https; URL safely embedded in the k6 script
    assert "https://campus.example.com/" in test_body["script_inline"]


@pytest.mark.asyncio
async def test_create_load_test_uses_explicit_project_over_active(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    explicit = "11111111-1111-4111-8111-111111111111"
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/tests"):
            seen["tests_path"] = request.url.path
            return httpx.Response(201, json={"id": "t1"})
        return httpx.Response(201, json={"id": "r1", "status": "queued"})

    _patched_client(monkeypatch, httpx.MockTransport(handler))

    result = await load_tools.create_load_test(
        target_url="https://example.com",
        vus=10,
        tool_context=_ctx_with_active_project(),  # active is _PROJECT_UUID
        duration_seconds=60,
        project_id=explicit,  # type: ignore[arg-type]
    )
    assert result["ok"] is True
    assert seen["tests_path"] == f"/v1/projects/{explicit}/tests"


@pytest.mark.asyncio
async def test_create_load_test_no_project_returns_graceful_error() -> None:
    # No explicit project and none seeded → graceful error, no exception.
    result = await load_tools.create_load_test(
        target_url="example.com",
        vus=5,
        tool_context=_ctx_with_token(),  # type: ignore[arg-type]
    )
    assert result["ok"] is False
    assert "project" in result["error"]


@pytest.mark.asyncio
async def test_create_load_test_rejects_bad_url() -> None:
    result = await load_tools.create_load_test(
        target_url="   ",
        vus=5,
        tool_context=_ctx_with_active_project(),  # type: ignore[arg-type]
    )
    assert result["ok"] is False
    assert "target_url" in result["error"]


@pytest.mark.asyncio
async def test_list_load_tests_defaults_to_active_project(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        return httpx.Response(200, json=[{"id": "t1", "product": "load"}])

    _patched_client(monkeypatch, httpx.MockTransport(handler))

    result = await load_tools.list_load_tests(
        tool_context=_ctx_with_active_project(),  # type: ignore[arg-type]
    )
    assert result["ok"] is True
    assert captured["path"] == f"/v1/projects/{_PROJECT_UUID}/tests"


@pytest.mark.asyncio
async def test_list_orgs_returns_memberships(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/me"
        return httpx.Response(
            200, json={"id": "u1", "memberships": [{"org_id": "o1", "role": "owner"}]}
        )

    _patched_client(monkeypatch, httpx.MockTransport(handler))

    result = await org_tools.list_orgs(
        tool_context=_ctx_with_token(),  # type: ignore[arg-type]
    )
    assert result == {"ok": True, "data": [{"org_id": "o1", "role": "owner"}]}
