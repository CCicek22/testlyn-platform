"""Shared helpers for tool implementations.

Tools receive a `tool_context: ToolContext` parameter so they can read the
user's Firebase token from session state. The token is seeded by the FastAPI
handler before invoking the runner — see ``main.chat_stream``.
"""

from __future__ import annotations

import re
from typing import Any

from google.adk.agents.context import Context as ToolContext

from testlyn_chat.tools.testlyn_client import TestlynAPIError, TestlynClient

_UUID_RE = re.compile(r"^[a-f0-9]{8}-[a-f0-9]{4}-4[a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}$")
_SCHEMA_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")


def _validate_uuid(value: str, field_name: str) -> str:
    if not _UUID_RE.match(value.lower()):
        raise ValueError(f"invalid {field_name}: must be a UUID-4")
    return value


def _validate_schema_name(value: str) -> str:
    if not _SCHEMA_NAME_RE.match(value):
        raise ValueError("invalid schema_name: must match ^[a-zA-Z0-9_-]{1,64}$")
    return value

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
