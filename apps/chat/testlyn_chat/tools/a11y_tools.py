"""Tools for the accessibility (axe-core) sub-agent."""

from __future__ import annotations

from typing import Any

from google.adk.agents.context import Context as ToolContext

from testlyn_chat.tools._helpers import client_for, err, ok
from testlyn_chat.tools.testlyn_client import TestlynAPIError


async def list_a11y_runs(
    tool_context: ToolContext,
    limit: int = 20,
) -> dict[str, Any]:
    """List recent accessibility audit runs.

    Args:
        limit: Max number of runs to return (default 20).
    """
    async with client_for(tool_context) as client:
        try:
            data = await client.get(
                "/v1/runs", params={"limit": limit, "product": "a11y"}
            )
        except TestlynAPIError as exc:
            return err(exc)
    return ok(data)


async def get_a11y_violations(
    run_id: str,
    tool_context: ToolContext,
) -> dict[str, Any]:
    """Fetch axe-core violations for a completed a11y run.

    Args:
        run_id: UUID of the a11y run.
    """
    # TODO: endpoint TBD — likely /v1/products/a11y/runs/{id}/violations.
    async with client_for(tool_context) as client:
        try:
            data = await client.get(f"/v1/products/a11y/runs/{run_id}/violations")
        except TestlynAPIError as exc:
            return err(exc)
    return ok(data)
