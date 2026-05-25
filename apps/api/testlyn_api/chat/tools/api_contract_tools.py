"""Tools for the API-contract (OpenAPI diff) sub-agent."""

from __future__ import annotations

from typing import Any

from google.adk.agents.context import Context as ToolContext

from testlyn_api.chat.tools._helpers import _uuid_error, client_for, err, ok
from testlyn_api.chat.tools.testlyn_client import TestlynAPIError


async def list_api_contract_runs(
    tool_context: ToolContext,
    limit: int = 20,
) -> dict[str, Any]:
    """List recent API contract checks.

    Args:
        limit: Max number of runs to return (default 20).
    """
    async with client_for(tool_context) as client:
        try:
            data = await client.get(
                "/v1/runs", params={"limit": limit, "product": "api_contract"}
            )
        except TestlynAPIError as exc:
            return err(exc)
    return ok(data)


async def get_contract_diff(
    run_id: str,
    tool_context: ToolContext,
) -> dict[str, Any]:
    """Fetch the OpenAPI breaking-change diff for a run.

    Args:
        run_id: UUID of the contract run.
    """
    if (e := _uuid_error(run_id, "run_id")) is not None:
        return e
    # TODO: endpoint TBD — placeholder path.
    async with client_for(tool_context) as client:
        try:
            data = await client.get(f"/v1/products/api-contract/runs/{run_id}/diff")
        except TestlynAPIError as exc:
            return err(exc)
    return ok(data)
