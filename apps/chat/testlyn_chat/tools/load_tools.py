"""Tools for the load-testing sub-agent.

Each function below is wrapped into a `FunctionTool` by ADK via the agent's
`tools=[...]` field. The docstring becomes the LLM-visible description, so
keep them concise and action-oriented.
"""

from __future__ import annotations

from typing import Any

from google.adk.agents.context import Context as ToolContext

from testlyn_chat.tools._helpers import client_for, err, ok
from testlyn_chat.tools.testlyn_client import TestlynAPIError


async def list_load_tests(
    project_id: str,
    tool_context: ToolContext,
) -> dict[str, Any]:
    """List load tests under a project.

    Args:
        project_id: UUID of the project.
    """
    async with client_for(tool_context) as client:
        try:
            data = await client.get(f"/v1/projects/{project_id}/tests")
        except TestlynAPIError as exc:
            return err(exc)
    # Filter to load product only — coordinator may route here from a mixed list.
    if isinstance(data, list):
        data = [t for t in data if t.get("product") == "load"]
    return ok(data)


async def run_load_test(
    test_id: str,
    tool_context: ToolContext,
) -> dict[str, Any]:
    """Trigger a new run of an existing load test.

    Args:
        test_id: UUID of the load test to run.
    """
    async with client_for(tool_context) as client:
        try:
            data = await client.post(f"/v1/tests/{test_id}/runs", json={})
        except TestlynAPIError as exc:
            return err(exc)
    return ok(data)


async def list_load_runs(
    tool_context: ToolContext,
    limit: int = 20,
    status: str | None = None,
) -> dict[str, Any]:
    """List recent load-test runs visible to the caller.

    Args:
        limit: Max number of runs to return (default 20).
        status: Optional status filter: pending, running, succeeded, failed, cancelled.
    """
    params: dict[str, Any] = {"limit": limit, "product": "load"}
    if status:
        params["status"] = status
    async with client_for(tool_context) as client:
        try:
            data = await client.get("/v1/runs", params=params)
        except TestlynAPIError as exc:
            return err(exc)
    return ok(data)


async def get_run_summary(
    run_id: str,
    tool_context: ToolContext,
) -> dict[str, Any]:
    """Fetch the summary metrics for a completed load run (p95, RPS, errors).

    Args:
        run_id: UUID of the run.
    """
    async with client_for(tool_context) as client:
        try:
            data = await client.get(f"/v1/runs/{run_id}/summary")
        except TestlynAPIError as exc:
            return err(exc)
    return ok(data)


async def cancel_run(
    run_id: str,
    tool_context: ToolContext,
) -> dict[str, Any]:
    """Cancel a queued or in-flight load run.

    Args:
        run_id: UUID of the run.
    """
    async with client_for(tool_context) as client:
        try:
            data = await client.post(f"/v1/runs/{run_id}/cancel")
        except TestlynAPIError as exc:
            return err(exc)
    return ok(data)
