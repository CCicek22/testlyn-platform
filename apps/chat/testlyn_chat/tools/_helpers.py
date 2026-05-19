"""Shared helpers for tool implementations.

Tools receive a `tool_context: ToolContext` parameter so they can read the
user's Firebase token from session state. The token is seeded by the FastAPI
handler before invoking the runner — see ``main.chat_stream``.
"""

from __future__ import annotations

from typing import Any

from google.adk.agents.context import Context as ToolContext

from testlyn_chat.tools.testlyn_client import TestlynAPIError, TestlynClient

# Session-state key the chat handler seeds with the verified Firebase token.
# Tools never accept the token as an LLM-visible argument.
# Uses ADK's "user:" scope prefix so the value is persisted by the session
# service (not just held on a per-invocation deepcopy) and is shared across
# all sessions for the same user, mirroring Firebase ID-token lifetime.
SESSION_KEY_USER_TOKEN = "user:_user_token"


def get_user_token(tool_context: ToolContext) -> str:
    token = tool_context.state.get(SESSION_KEY_USER_TOKEN)  # type: ignore[arg-type]
    if not token or not isinstance(token, str):
        raise PermissionError("user token missing from session state")
    return token


def client_for(tool_context: ToolContext) -> TestlynClient:
    return TestlynClient(user_token=get_user_token(tool_context))


def err(exc: TestlynAPIError) -> dict[str, Any]:
    """Convert an API error into a structured tool result the LLM can read."""
    return {"ok": False, "status": exc.status_code, "error": exc.body}


def ok(data: Any) -> dict[str, Any]:
    return {"ok": True, "data": data}
