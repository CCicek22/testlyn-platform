"""Regression tests for the ADK session deepcopy-discard behaviour.

`BaseSessionService.get_session()` returns a deepcopy of the stored session,
so direct mutation of `session.state[...]` does NOT write through. The chat
handler must persist token refreshes via `append_event` + state_delta, which
the service applies to its canonical copy. These tests pin that contract so a
revert to direct mutation is caught.
"""

from __future__ import annotations

import pytest
from google.adk.events import Event, EventActions
from google.adk.sessions import InMemorySessionService

from testlyn_api.chat.tools._helpers import SESSION_KEY_USER_TOKEN


@pytest.mark.asyncio
async def test_direct_state_mutation_does_not_persist() -> None:
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
