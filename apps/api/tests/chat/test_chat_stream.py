"""Integration tests for the in-process /chat/stream SSE endpoint.

These drive the route through the api's real auth dependency (dev bypass in
the test env) and a stubbed ADK runner, so they are hermetic — no live Vertex
call, no real Gemini. They assert:
  1. the SSE event sequence (token ... -> done) for a normal turn,
  2. the user's bearer token is seeded into ADK session state and refreshed
     across turns (the deepcopy-discard regression guard),
  3. missing auth is rejected with 401.
"""

from __future__ import annotations

import json
from typing import Any, AsyncGenerator

import pytest
from httpx import AsyncClient

from testlyn_api.chat import routes as chat_routes
from testlyn_api.chat.session.store import get_session_service
from testlyn_api.chat.tools._helpers import SESSION_KEY_USER_TOKEN

# dev_auth_bypass resolves the deterministic dev user; user_id in the route is
# firebase_uid or str(id). Bypass leaves firebase_uid None, so user_id is the
# dev user's UUID string.
_DEV_USER_ID = "00000000-0000-0000-0000-d3eff3e10101"


def _parse_sse(body: str) -> list[tuple[str, dict[str, Any]]]:
    """Parse an SSE body into a list of (event, data) tuples."""
    events: list[tuple[str, dict[str, Any]]] = []
    event_name: str | None = None
    for line in body.splitlines():
        if line.startswith("event:"):
            event_name = line.split(":", 1)[1].strip()
        elif line.startswith("data:") and event_name is not None:
            raw = line.split(":", 1)[1].strip()
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                payload = {"_raw": raw}
            events.append((event_name, payload))
            event_name = None
    return events


class _FakeEvent:
    """Minimal stand-in for an ADK Event carrying one text part."""

    def __init__(self, text: str, author: str = "load_agent") -> None:
        self.author = author

        class _Part:
            def __init__(self, t: str) -> None:
                self.text = t

        class _Content:
            def __init__(self, t: str) -> None:
                self.parts = [_Part(t)]

        self.content = _Content(text)

    def get_function_calls(self) -> list[Any]:
        return []

    def get_function_responses(self) -> list[Any]:
        return []


class _StubRunner:
    """Async-generator runner that emits a couple of text events."""

    def __init__(self, chunks: list[str]) -> None:
        self._chunks = chunks

    async def run_async(self, **_kwargs: Any) -> AsyncGenerator[_FakeEvent, None]:
        for chunk in self._chunks:
            yield _FakeEvent(chunk)


@pytest.fixture(autouse=True)
def _reset_chat_singletons() -> None:
    """Fresh session service + runner per test."""
    chat_routes._runner = None
    get_session_service.cache_clear()


@pytest.mark.asyncio
async def test_chat_stream_emits_token_then_done(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        chat_routes, "get_runner", lambda: _StubRunner(["hello ", "world"])
    )

    resp = await client.post(
        "/chat/stream",
        json={"message": "hi", "session_id": "sess-Aa1"},
        headers={"Authorization": "Bearer tok-A"},
    )
    assert resp.status_code == 200

    events = _parse_sse(resp.text)
    names = [name for name, _ in events]

    # First a (best-effort) agent_switch, then token(s), ending with done.
    assert "token" in names
    assert names[-1] == "done"

    tokens = [data["text"] for name, data in events if name == "token"]
    assert "".join(tokens) == "hello world"

    done = next(data for name, data in events if name == "done")
    assert done["session_id"] == "sess-Aa1"


@pytest.mark.asyncio
async def test_chat_stream_seeds_and_refreshes_token(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The bearer token must be written through the session store each turn.

    Guards the deepcopy-discard bug: get_session() returns a copy, so the
    handler persists via append_event + state_delta.
    """
    monkeypatch.setattr(chat_routes, "get_runner", lambda: _StubRunner(["ok"]))
    session_service = get_session_service()
    sid = "sess-Bb2"

    r1 = await client.post(
        "/chat/stream",
        json={"message": "hi", "session_id": sid},
        headers={"Authorization": "Bearer tok-A"},
    )
    assert r1.status_code == 200

    stored = await session_service.get_session(
        app_name="testlyn-chat", user_id=_DEV_USER_ID, session_id=sid
    )
    assert stored is not None
    assert stored.state[SESSION_KEY_USER_TOKEN] == "tok-A"

    r2 = await client.post(
        "/chat/stream",
        json={"message": "again", "session_id": sid},
        headers={"Authorization": "Bearer tok-B"},
    )
    assert r2.status_code == 200

    refreshed = await session_service.get_session(
        app_name="testlyn-chat", user_id=_DEV_USER_ID, session_id=sid
    )
    assert refreshed is not None
    assert refreshed.state[SESSION_KEY_USER_TOKEN] == "tok-B", (
        "Token refresh did not write through to the session store — "
        "the deepcopy-discard bug is back."
    )


@pytest.mark.asyncio
async def test_chat_stream_requires_auth(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without dev bypass and without a bearer token the route returns 401."""
    monkeypatch.setenv("DEV_AUTH_BYPASS", "false")
    from testlyn_api import config as cfg_module

    cfg_module.get_settings.cache_clear()
    try:
        resp = await client.post("/chat/stream", json={"message": "hi"})
        assert resp.status_code == 401
    finally:
        cfg_module.get_settings.cache_clear()
