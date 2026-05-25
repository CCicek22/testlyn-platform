"""Shared helpers for tool implementations.

Tools receive a `tool_context: ToolContext` parameter so they can read the
user's Firebase token from session state. The token is seeded by the FastAPI
handler before invoking the runner — see ``main.chat_stream``.
"""

from __future__ import annotations

import re
from typing import Any

from google.adk.agents.context import Context as ToolContext

from testlyn_api.chat.tools.testlyn_client import TestlynAPIError, TestlynClient

_UUID_RE = re.compile(
    r"^[a-f0-9]{8}-[a-f0-9]{4}-4[a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}$"
)
_SCHEMA_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")


def _uuid_error(value: str, field_name: str) -> dict[str, Any] | None:
    """Return a structured tool error if ``value`` is not a UUID-4, else None.

    Tools call this at entry and ``return`` the result if non-None. Returning an
    error (rather than raising) is deliberate: the LLM regularly hallucinates a
    non-UUID arg — e.g. passing a target hostname as ``project_id`` — and a
    raised exception bubbles past the tool's ``try/except TestlynAPIError``,
    through the ADK runner, to the chat route's catch-all, aborting the whole
    SSE stream as a useless "internal error". A structured ``{"ok": False}``
    instead reaches the model as a normal tool result it can read and recover
    from (ask the user, list projects, etc.).
    """
    if not _UUID_RE.match(value.lower()):
        return {"ok": False, "error": f"invalid {field_name}: must be a UUID-4"}
    return None


def _schema_name_error(value: str) -> dict[str, Any] | None:
    """Return a structured tool error if ``value`` is not a valid schema name,
    else None. Same graceful-vs-raise rationale as :func:`_uuid_error`.
    """
    if not _SCHEMA_NAME_RE.match(value):
        return {
            "ok": False,
            "error": "invalid schema_name: must match ^[a-zA-Z0-9_-]{1,64}$",
        }
    return None


# Session-state key the chat handler seeds with the verified Firebase token.
# Tools never accept the token as an LLM-visible argument.
# Uses ADK's "user:" scope prefix so the value is persisted by the session
# service (not just held on a per-invocation deepcopy) and is shared across
# all sessions for the same user, mirroring Firebase ID-token lifetime.
SESSION_KEY_USER_TOKEN = "user:_user_token"

# Session-state key holding the UI's currently-selected project, seeded by the
# chat handler from the request each turn. Session-scoped (no "user:" prefix):
# the active project is per-chat, not a durable user attribute. Tools use it as
# a fallback so the user need not paste a UUID — e.g. "run a load test on
# example.com" resolves to the active project.
SESSION_KEY_PROJECT_ID = "active_project_id"
SESSION_KEY_ORG_ID = "active_org_id"


def get_user_token(tool_context: ToolContext) -> str:
    token = tool_context.state.get(SESSION_KEY_USER_TOKEN)  # type: ignore[arg-type]
    if not token or not isinstance(token, str):
        raise PermissionError("user token missing from session state")
    return token


def get_active_project_id(tool_context: ToolContext) -> str | None:
    """Return the UI-selected project id seeded into the session, or None."""
    value = tool_context.state.get(SESSION_KEY_PROJECT_ID)  # type: ignore[arg-type]
    return value if isinstance(value, str) and value else None


def get_active_org_id(tool_context: ToolContext) -> str | None:
    """Return the UI-selected org id seeded into the session, or None."""
    value = tool_context.state.get(SESSION_KEY_ORG_ID)  # type: ignore[arg-type]
    return value if isinstance(value, str) and value else None


def client_for(tool_context: ToolContext) -> TestlynClient:
    return TestlynClient(user_token=get_user_token(tool_context))


def err(exc: TestlynAPIError) -> dict[str, Any]:
    """Convert an API error into a structured tool result the LLM can read."""
    return {"ok": False, "status": exc.status_code, "error": exc.body}


def ok(data: Any) -> dict[str, Any]:
    return {"ok": True, "data": data}
