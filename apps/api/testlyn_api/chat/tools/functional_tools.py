"""Tools for the functional-testing sub-agent (Playwright E2E flows).

Phase 1 status: stub. The functional product router exists at
``/v1/products/functional`` in testlyn-api but its run-create endpoint is
still under development. Tools below call the documented surface; missing
endpoints surface as 404s through TestlynAPIError, which the LLM relays.
"""

from __future__ import annotations

from typing import Any

from google.adk.agents.context import Context as ToolContext

from testlyn_api.chat.tools._helpers import _uuid_error, client_for, err, ok
from testlyn_api.chat.tools.testlyn_client import TestlynAPIError


async def list_functional_tests(
    project_id: str,
    tool_context: ToolContext,
) -> dict[str, Any]:
    """List functional (Playwright) tests in a project.

    Args:
        project_id: UUID of the project.
    """
    if (e := _uuid_error(project_id, "project_id")) is not None:
        return e
    async with client_for(tool_context) as client:
        try:
            data = await client.get(f"/v1/projects/{project_id}/tests")
        except TestlynAPIError as exc:
            return err(exc)
    if isinstance(data, list):
        data = [t for t in data if t.get("product") == "functional"]
    return ok(data)


async def run_functional_test(
    test_id: str,
    tool_context: ToolContext,
) -> dict[str, Any]:
    """Trigger a functional test run.

    Args:
        test_id: UUID of the test.
    """
    if (e := _uuid_error(test_id, "test_id")) is not None:
        return e
    # TODO: confirm body shape once /v1/products/functional/runs is finalised.
    async with client_for(tool_context) as client:
        try:
            data = await client.post(f"/v1/tests/{test_id}/runs", json={})
        except TestlynAPIError as exc:
            return err(exc)
    return ok(data)
