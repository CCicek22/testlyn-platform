"""Tools for knowledge search (org documents, passages with citations)."""

from __future__ import annotations

from typing import Any

from google.adk.agents.context import Context as ToolContext

from testlyn_api.chat.tools._helpers import (
    _uuid_error,
    client_for,
    err,
    get_active_org_id,
    get_active_project_id,
    ok,
)
from testlyn_api.chat.tools.testlyn_client import TestlynAPIError


async def search_knowledge(
    query: str,
    tool_context: ToolContext,
    project_id: str | None = None,
    top_k: int = 5,
) -> dict[str, Any]:
    """Search the organisation's knowledge documents for passages matching a question.

    Args:
        query: The question or keywords to search for.
        project_id: Optional UUID of a project. Defaults to the UI-selected
            project; org-wide documents are always included.
        top_k: Number of passages to return (1 to 20, default 5).
    """
    org_id = get_active_org_id(tool_context)
    if not org_id or _uuid_error(org_id, "org_id") is not None:
        return {
            "ok": False,
            "error": "no active organisation for this chat; ask the user to pick one",
        }
    text = query.strip()
    if not text:
        return {"ok": False, "error": "query must not be empty"}

    scope = project_id or get_active_project_id(tool_context)
    if scope is not None and (e := _uuid_error(scope, "project_id")) is not None:
        return e

    body: dict[str, Any] = {"query": text, "top_k": min(max(top_k, 1), 20)}
    if scope is not None:
        body["project_id"] = scope
    async with client_for(tool_context) as client:
        try:
            data = await client.post(f"/v1/orgs/{org_id}/knowledge/search", json=body)
        except TestlynAPIError as exc:
            return err(exc)
    return ok(data)
