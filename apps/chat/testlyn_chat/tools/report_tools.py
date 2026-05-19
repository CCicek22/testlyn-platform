"""Tools for the reports / insights sub-agent."""

from __future__ import annotations

from typing import Any

from google.adk.agents.context import Context as ToolContext

from testlyn_chat.tools._helpers import _validate_uuid, client_for, err, ok
from testlyn_chat.tools.testlyn_client import TestlynAPIError


async def list_runs(
    tool_context: ToolContext,
    limit: int = 20,
    product: str | None = None,
) -> dict[str, Any]:
    """List recent test runs across all products.

    Args:
        limit: Max number of runs to return (default 20).
        product: Optional product filter (load, functional, a11y, ...).
    """
    params: dict[str, Any] = {"limit": limit}
    if product:
        params["product"] = product
    async with client_for(tool_context) as client:
        try:
            data = await client.get("/v1/runs", params=params)
        except TestlynAPIError as exc:
            return err(exc)
    return ok(data)


async def get_run_detail(
    run_id: str,
    tool_context: ToolContext,
) -> dict[str, Any]:
    """Fetch full detail for a single run (any product).

    Args:
        run_id: UUID of the run.
    """
    _validate_uuid(run_id, "run_id")
    async with client_for(tool_context) as client:
        try:
            data = await client.get(f"/v1/runs/{run_id}")
        except TestlynAPIError as exc:
            return err(exc)
    return ok(data)


async def get_insights_latest(
    org_id: str,
    tool_context: ToolContext,
) -> dict[str, Any]:
    """Fetch the latest daily AI insights snapshot for an organisation.

    Args:
        org_id: UUID of the organisation.
    """
    _validate_uuid(org_id, "org_id")
    async with client_for(tool_context) as client:
        try:
            data = await client.get(f"/v1/orgs/{org_id}/insights/latest")
        except TestlynAPIError as exc:
            return err(exc)
    return ok(data)


async def get_report_url(
    run_id: str,
    tool_context: ToolContext,
) -> dict[str, Any]:
    """Get a signed URL to the PDF report for a run.

    Args:
        run_id: UUID of the run.
    """
    _validate_uuid(run_id, "run_id")
    # TODO: endpoint TBD — placeholder until report-builder exposes a URL endpoint.
    async with client_for(tool_context) as client:
        try:
            data = await client.get(f"/v1/runs/{run_id}/report")
        except TestlynAPIError as exc:
            return err(exc)
    return ok(data)
