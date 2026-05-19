"""Tools for the synthetic-data generation sub-agent."""

from __future__ import annotations

from typing import Any

from google.adk.agents.context import Context as ToolContext

from testlyn_chat.tools._helpers import _validate_schema_name, _validate_uuid, client_for, err, ok
from testlyn_chat.tools.testlyn_client import TestlynAPIError


async def list_synthetic_jobs(
    tool_context: ToolContext,
    limit: int = 20,
) -> dict[str, Any]:
    """List recent synthetic-data generation jobs.

    Args:
        limit: Max number of jobs to return (default 20).
    """
    # TODO: confirm path once /v1/products/synthetic-data list endpoint lands.
    async with client_for(tool_context) as client:
        try:
            data = await client.get(
                "/v1/products/synthetic-data/jobs", params={"limit": limit}
            )
        except TestlynAPIError as exc:
            return err(exc)
    return ok(data)


async def generate_synthetic_dataset(
    project_id: str,
    schema_name: str,
    row_count: int,
    tool_context: ToolContext,
) -> dict[str, Any]:
    """Kick off a synthetic-data generation job.

    Args:
        project_id: UUID of the owning project.
        schema_name: Name of an existing schema definition.
        row_count: Number of synthetic rows to produce.
    """
    _validate_uuid(project_id, "project_id")
    _validate_schema_name(schema_name)
    # TODO: confirm payload once endpoint contract is final.
    async with client_for(tool_context) as client:
        try:
            data = await client.post(
                "/v1/products/synthetic-data/jobs",
                json={
                    "project_id": project_id,
                    "schema_name": schema_name,
                    "row_count": row_count,
                },
            )
        except TestlynAPIError as exc:
            return err(exc)
    return ok(data)
