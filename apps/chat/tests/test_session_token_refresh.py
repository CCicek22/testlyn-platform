"""Regression test for the deepcopy-discard bug.

`BaseSessionService.get_session()` returns a deepcopy of the stored session,
so direct mutation of `session.state[...]` does NOT write through. The chat
handler must persist token refreshes via `append_event` + state_delta, which
the service applies to its canonical copy. If anyone reverts the handler to
direct mutation, this test fails.
"""

from __future__ import annotations

import pytest
from google.adk.events import Event, EventActions
from google.adk.sessions import InMemorySessionService

from testlyn_chat.tools._helpers import SESSION_KEY_USER_TOKEN


@pytest.mark.asyncio
async def test_direct_state_mutation_does_not_persist() -> None:
    """Demonstrates the bug we are guarding against — if this ever starts
    failing (i.e. direct mutation DOES persist), we can simplify the handler.
    """
    svc = InMemorySessionService()
    await svc.create_session(
        app_name="t", user_id="u", session_id="s", state={SESSION_KEY_USER_TOKEN: "old"}
    )

    snapshot = await svc.get_session(app_name="t", user_id="u", session_id="s")
    assert snapshot is not None
    snapshot.state[SESSION_KEY_USER_TOKEN] = "new"  # direct mutation on the copy

    fresh = await svc.get_session(app_name="t", user_id="u", session_id="s")
    assert fresh is not None
    assert fresh.state[SESSION_KEY_USER_TOKEN] == "old", (
        "Direct mutation unexpectedly persisted — handler can be simplified"
    )


@pytest.mark.asyncio
async def test_append_event_with_state_delta_writes_through() -> None:
    """The pattern the chat handler uses for token refresh."""
    svc = InMemorySessionService()
    existing = await svc.create_session(
        app_name="t", user_id="u", session_id="s", state={SESSION_KEY_USER_TOKEN: "old"}
    )

    await svc.append_event(
        session=existing,
        event=Event(
            author="system",
            actions=EventActions(state_delta={SESSION_KEY_USER_TOKEN: "new"}),
        ),
    )

    fresh = await svc.get_session(app_name="t", user_id="u", session_id="s")
    assert fresh is not None
    assert fresh.state[SESSION_KEY_USER_TOKEN] == "new"


@pytest.mark.asyncio
async def test_chat_handler_refreshes_token_through_store(monkeypatch) -> None:
    """End-to-end: drive the handler twice with different bearer tokens and
    assert the session-store value reflects the latest.

    We stub the LLM/runner side — the test only exercises the seeding /
    refresh code path in `chat_stream`, which is what the bug fix targets.
    """
    from testlyn_chat import main as chat_main
    from testlyn_chat.session.store import get_session_service

    # Reset singletons so this test gets a clean slate.
    chat_main._runner = None
    get_session_service.cache_clear()
    session_service = get_session_service()

    # Stub out Firebase verify so we accept any "Bearer <token>" header and
    # return the token as the uid for predictable user_id resolution.
    def fake_verify(token: str):
        return {"uid": "user-1", "sub": "user-1"} if token else None

    monkeypatch.setattr(chat_main, "verify_token", fake_verify, raising=False)
    # The dependency reads via the top-level import in auth.py — patch there too.
    from testlyn_chat import auth as chat_auth

    monkeypatch.setattr(chat_auth, "verify_token", fake_verify)

    # Stub the runner so we don't need Vertex creds. We only need it to be a
    # no-op async generator that yields nothing.
    class _NoopRunner:
        async def run_async(self, **_kwargs):
            if False:  # pragma: no cover — make this an async generator
                yield None
            return

    monkeypatch.setattr(chat_main, "get_runner", lambda: _NoopRunner())

    from fastapi.testclient import TestClient

    client = TestClient(chat_main.app)

    # Turn 1 — establish session with token "tok-A".
    r1 = client.post(
        "/chat/stream",
        json={"message": "hi", "session_id": "sess-A"},
        headers={"Authorization": "Bearer tok-A"},
    )
    assert r1.status_code == 200
    # Consume the SSE body so the streaming response (and the request scope's
    # finalisers) run to completion.
    _ = r1.text

    stored = await session_service.get_session(
        app_name="testlyn-chat", user_id="user-1", session_id="sess-A"
    )
    assert stored is not None
    assert stored.state[SESSION_KEY_USER_TOKEN] == "tok-A"

    # Turn 2 — same session, refreshed token. The store MUST now hold "tok-B".
    r2 = client.post(
        "/chat/stream",
        json={"message": "still here", "session_id": "sess-A"},
        headers={"Authorization": "Bearer tok-B"},
    )
    assert r2.status_code == 200
    _ = r2.text

    refreshed = await session_service.get_session(
        app_name="testlyn-chat", user_id="user-1", session_id="sess-A"
    )
    assert refreshed is not None
    assert refreshed.state[SESSION_KEY_USER_TOKEN] == "tok-B", (
        "Token refresh did not write through to the session store — "
        "the deepcopy-discard bug is back."
    )
