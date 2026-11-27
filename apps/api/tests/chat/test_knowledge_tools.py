"""Unit tests for the knowledge search chat tool (httpx MockTransport, no LLM)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import httpx
import pytest

from testlyn_api.chat.agents.reports import build_reports_agent
from testlyn_api.chat.tools import knowledge_tools
from testlyn_api.chat.tools._helpers import (
    SESSION_KEY_ORG_ID,
    SESSION_KEY_PROJECT_ID,
    SESSION_KEY_USER_TOKEN,
)
from testlyn_api.chat.tools.testlyn_client import TestlynClient

_ORG = "22e6855a-7768-4a81-9baf-090303783781"
_PROJECT = "3f1c2b7e-8d0a-4c1e-9b2a-7e6d5c4b3a21"
_OTHER_PROJECT = "9d8c7b6a-5f4e-4d3c-8b2a-1a0f9e8d7c6b"


@dataclass
class _FakeState:
    data: dict[str, Any] = field(default_factory=dict)

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)


@dataclass
class _FakeToolContext:
    state: _FakeState = field(default_factory=_FakeState)


def _ctx(**extra: str) -> _FakeToolContext:
    state = {SESSION_KEY_USER_TOKEN: "fake-token", **extra}
    return _FakeToolContext(state=_FakeState(state))


def _patched_client(
    monkeypatch: pytest.MonkeyPatch, transport: httpx.MockTransport
) -> None:
    orig_init = TestlynClient.__init__

    def patched_init(self: TestlynClient, *, user_token: str, **kwargs: Any) -> None:
        raw = httpx.AsyncClient(
            transport=transport,
            base_url="http://api.test",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        orig_init(self, user_token=user_token, client=raw)

    monkeypatch.setattr(TestlynClient, "__init__", patched_init)


def _recording_transport(
    calls: list[dict[str, Any]], response: httpx.Response | None = None
) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(
            {
                "method": request.method,
                "path": request.url.path,
                "body": json.loads(request.content) if request.content else None,
            }
        )
        return response or httpx.Response(
            200, json={"results": [], "mode": "hybrid", "reranked": False}
        )

    return httpx.MockTransport(handler)


async def test_posts_query_to_active_org_search_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, Any]] = []
    _patched_client(monkeypatch, _recording_transport(calls))

    result = await knowledge_tools.search_knowledge(
        "how do I roll back",
        tool_context=_ctx(**{SESSION_KEY_ORG_ID: _ORG}),  # type: ignore[arg-type]
    )

    assert result["ok"] is True
    assert result["data"]["reranked"] is False
    assert calls == [
        {
            "method": "POST",
            "path": f"/v1/orgs/{_ORG}/knowledge/search",
            "body": {"query": "how do I roll back", "top_k": 5},
        }
    ]


async def test_explicit_project_wins_over_active_project(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, Any]] = []
    _patched_client(monkeypatch, _recording_transport(calls))

    await knowledge_tools.search_knowledge(
        "q",
        project_id=_OTHER_PROJECT,
        tool_context=_ctx(  # type: ignore[arg-type]
            **{SESSION_KEY_ORG_ID: _ORG, SESSION_KEY_PROJECT_ID: _PROJECT}
        ),
    )

    assert calls[0]["body"]["project_id"] == _OTHER_PROJECT


async def test_active_project_is_used_when_none_given(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, Any]] = []
    _patched_client(monkeypatch, _recording_transport(calls))

    await knowledge_tools.search_knowledge(
        "q",
        tool_context=_ctx(  # type: ignore[arg-type]
            **{SESSION_KEY_ORG_ID: _ORG, SESSION_KEY_PROJECT_ID: _PROJECT}
        ),
    )

    assert calls[0]["body"]["project_id"] == _PROJECT


async def test_no_project_means_org_wide(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []
    _patched_client(monkeypatch, _recording_transport(calls))

    await knowledge_tools.search_knowledge(
        "q", tool_context=_ctx(**{SESSION_KEY_ORG_ID: _ORG})  # type: ignore[arg-type]
    )

    assert "project_id" not in calls[0]["body"]


async def test_top_k_is_clamped_to_api_range(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []
    _patched_client(monkeypatch, _recording_transport(calls))
    ctx = _ctx(**{SESSION_KEY_ORG_ID: _ORG})

    await knowledge_tools.search_knowledge("q", top_k=99, tool_context=ctx)  # type: ignore[arg-type]
    await knowledge_tools.search_knowledge("q", top_k=0, tool_context=ctx)  # type: ignore[arg-type]

    assert [c["body"]["top_k"] for c in calls] == [20, 1]


async def test_missing_org_returns_error_without_calling_api(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, Any]] = []
    _patched_client(monkeypatch, _recording_transport(calls))

    result = await knowledge_tools.search_knowledge(
        "q", tool_context=_ctx()  # type: ignore[arg-type]
    )

    assert result["ok"] is False
    assert "org" in result["error"]
    assert calls == []


async def test_empty_query_returns_error_without_calling_api(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, Any]] = []
    _patched_client(monkeypatch, _recording_transport(calls))

    result = await knowledge_tools.search_knowledge(
        "   ", tool_context=_ctx(**{SESSION_KEY_ORG_ID: _ORG})  # type: ignore[arg-type]
    )

    assert result["ok"] is False
    assert calls == []


async def test_invalid_project_id_returns_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, Any]] = []
    _patched_client(monkeypatch, _recording_transport(calls))

    result = await knowledge_tools.search_knowledge(
        "q",
        project_id="my-project",
        tool_context=_ctx(**{SESSION_KEY_ORG_ID: _ORG}),  # type: ignore[arg-type]
    )

    assert result["ok"] is False
    assert "project_id" in result["error"]
    assert calls == []


async def test_api_error_is_returned_as_structured_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, Any]] = []
    _patched_client(
        monkeypatch,
        _recording_transport(
            calls, httpx.Response(404, json={"detail": "Project not found"})
        ),
    )

    result = await knowledge_tools.search_knowledge(
        "q",
        project_id=_PROJECT,
        tool_context=_ctx(**{SESSION_KEY_ORG_ID: _ORG}),  # type: ignore[arg-type]
    )

    assert result["ok"] is False
    assert result["status"] == 404


def test_reports_agent_can_search_knowledge_and_is_told_to_cite() -> None:
    agent = build_reports_agent()

    assert knowledge_tools.search_knowledge in agent.tools
    assert "search_knowledge" in agent.instruction
    assert "cite" in agent.instruction.lower()
