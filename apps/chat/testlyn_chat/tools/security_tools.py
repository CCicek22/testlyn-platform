"""Tools for the security (DAST/ZAP) sub-agent."""

from __future__ import annotations

from typing import Any

from google.adk.agents.context import Context as ToolContext

from testlyn_chat.tools._helpers import client_for, err, ok
from testlyn_chat.tools.testlyn_client import TestlynAPIError


async def list_security_runs(
    tool_context: ToolContext,
    limit: int = 20,
) -> dict[str, Any]:
    """List recent security scans.

    Args:
        limit: Max number of runs to return (default 20).
    """
    async with client_for(tool_context) as client:
        try:
            data = await client.get(
                "/v1/runs", params={"limit": limit, "product": "security"}
            )
        except TestlynAPIError as exc:
            return err(exc)
    return ok(data)


async def get_security_findings(
    run_id: str,
    tool_context: ToolContext,
) -> dict[str, Any]:
    """Fetch security findings (CVEs / OWASP) for a scan.

    Args:
        run_id: UUID of the security run.
    """
    # TODO: endpoint TBD.
    async with client_for(tool_context) as client:
        try:
            data = await client.get(f"/v1/products/security/runs/{run_id}/findings")
        except TestlynAPIError as exc:
            return err(exc)
    return ok(data)
