"""Tools for the organisation-admin sub-agent (orgs, projects, billing)."""

from __future__ import annotations

from typing import Any

from google.adk.agents.context import Context as ToolContext

from testlyn_api.chat.tools._helpers import _validate_uuid, client_for, err, ok
from testlyn_api.chat.tools.testlyn_client import TestlynAPIError


async def list_projects(
    org_id: str,
    tool_context: ToolContext,
) -> dict[str, Any]:
    """List projects in an organisation.

    Args:
        org_id: UUID of the organisation.
    """
    _validate_uuid(org_id, "org_id")
    async with client_for(tool_context) as client:
        try:
            data = await client.get(f"/v1/orgs/{org_id}/projects")
        except TestlynAPIError as exc:
            return err(exc)
    return ok(data)


async def get_org(
    org_id: str,
    tool_context: ToolContext,
) -> dict[str, Any]:
    """Fetch org metadata (name, slug, plan).

    Args:
        org_id: UUID of the organisation.
    """
    _validate_uuid(org_id, "org_id")
    async with client_for(tool_context) as client:
        try:
            data = await client.get(f"/v1/orgs/{org_id}")
        except TestlynAPIError as exc:
            return err(exc)
    return ok(data)


async def list_org_members(
    org_id: str,
    tool_context: ToolContext,
) -> dict[str, Any]:
    """List members of an organisation.

    Args:
        org_id: UUID of the organisation.
    """
    _validate_uuid(org_id, "org_id")
    # TODO: confirm endpoint — likely /v1/orgs/{id}/members.
    async with client_for(tool_context) as client:
        try:
            data = await client.get(f"/v1/orgs/{org_id}/members")
        except TestlynAPIError as exc:
            return err(exc)
    return ok(data)


async def get_billing_summary(
    org_id: str,
    tool_context: ToolContext,
) -> dict[str, Any]:
    """Fetch the current billing-period usage + plan tier.

    Args:
        org_id: UUID of the organisation.
    """
    _validate_uuid(org_id, "org_id")
    # TODO: confirm endpoint when billing routes finalise.
    async with client_for(tool_context) as client:
        try:
            data = await client.get(f"/v1/orgs/{org_id}/billing")
        except TestlynAPIError as exc:
            return err(exc)
    return ok(data)
