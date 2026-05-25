"""Tools for the load-testing sub-agent.

Each function below is wrapped into a `FunctionTool` by ADK via the agent's
`tools=[...]` field. The docstring becomes the LLM-visible description, so
keep them concise and action-oriented.
"""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlparse

from google.adk.agents.context import Context as ToolContext

from testlyn_api.chat.tools._helpers import (
    _uuid_error,
    client_for,
    err,
    get_active_project_id,
    ok,
)
from testlyn_api.chat.tools.testlyn_client import TestlynAPIError


def _resolve_project(
    project_id: str, tool_context: ToolContext
) -> tuple[str | None, dict[str, Any] | None]:
    """Resolve which project to act on: an explicit valid UUID wins, else the
    UI-selected project seeded into the chat session. Returns
    ``(project_id, None)`` on success or ``(None, error_dict)`` so the caller
    can ``return`` the error gracefully.
    """
    if project_id and _uuid_error(project_id, "project_id") is None:
        return project_id, None
    active = get_active_project_id(tool_context)
    if active and _uuid_error(active, "project_id") is None:
        return active, None
    if project_id:
        # Provided but not a UUID, and no usable active project to fall back on.
        return None, _uuid_error(project_id, "project_id")
    return None, {
        "ok": False,
        "error": (
            "no project specified and no active project for this chat; "
            "call list_orgs then list_projects, or ask the user to pick one"
        ),
    }


def _normalize_url(target_url: str) -> str | None:
    """Normalise a user-supplied target into an http(s) URL, or None if it has
    no usable host. Defaults a missing scheme to https.
    """
    url = target_url.strip()
    if not url:
        return None
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    if not urlparse(url).netloc:
        return None
    return url


def _build_k6_script(target_url: str) -> str:
    """A minimal k6 GET-loop script for ``target_url``. The URL is embedded via
    json.dumps so it is safely quoted into the JS string.
    """
    return (
        'import http from "k6/http";\n'
        'import { sleep } from "k6";\n'
        "export default function () {\n"
        f"  http.get({json.dumps(target_url)});\n"
        "  sleep(1);\n"
        "}\n"
    )


async def list_load_tests(
    tool_context: ToolContext,
    project_id: str = "",
) -> dict[str, Any]:
    """List load tests under a project.

    Args:
        project_id: UUID of the project. Optional — defaults to the project the
            user has selected in the UI for this chat.
    """
    resolved, error = _resolve_project(project_id, tool_context)
    if error is not None:
        return error
    async with client_for(tool_context) as client:
        try:
            data = await client.get(f"/v1/projects/{resolved}/tests")
        except TestlynAPIError as exc:
            return err(exc)
    # Filter to load product only — coordinator may route here from a mixed list.
    if isinstance(data, list):
        data = [t for t in data if t.get("product") == "load"]
    return ok(data)


async def create_load_test(
    target_url: str,
    vus: int,
    tool_context: ToolContext,
    duration_seconds: int = 30,
    project_id: str = "",
) -> dict[str, Any]:
    """Create a load test for a URL and immediately launch a run.

    Use this for requests like "run a 50 VU load test on example.com". Builds a
    simple k6 GET script for the target, creates the test under the project, and
    starts a run. Returns the created test and the launched run.

    Args:
        target_url: URL to load test (scheme optional; defaults to https).
        vus: Number of concurrent virtual users.
        duration_seconds: How long to run, in seconds (default 30).
        project_id: UUID of the project. Optional — defaults to the project the
            user has selected in the UI for this chat.
    """
    url = _normalize_url(target_url)
    if url is None:
        return {"ok": False, "error": f"invalid target_url: {target_url!r}"}
    if vus <= 0:
        return {"ok": False, "error": "vus must be a positive integer"}
    if duration_seconds <= 0:
        return {"ok": False, "error": "duration_seconds must be a positive integer"}
    resolved, error = _resolve_project(project_id, tool_context)
    if error is not None:
        return error
    payload = {
        "name": f"{vus}vu {url}"[:200],
        "product": "load",
        "script_inline": _build_k6_script(url),
        "config": {"vus": vus, "duration_seconds": duration_seconds},
    }
    async with client_for(tool_context) as client:
        try:
            test = await client.post(f"/v1/projects/{resolved}/tests", json=payload)
            run = await client.post(f"/v1/tests/{test['id']}/runs", json={})
        except TestlynAPIError as exc:
            return err(exc)
    return ok({"test": test, "run": run})


async def run_load_test(
    test_id: str,
    tool_context: ToolContext,
) -> dict[str, Any]:
    """Trigger a new run of an existing load test.

    Args:
        test_id: UUID of the load test to run.
    """
    if (e := _uuid_error(test_id, "test_id")) is not None:
        return e
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
    if (e := _uuid_error(run_id, "run_id")) is not None:
        return e
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
    if (e := _uuid_error(run_id, "run_id")) is not None:
        return e
    async with client_for(tool_context) as client:
        try:
            data = await client.post(f"/v1/runs/{run_id}/cancel")
        except TestlynAPIError as exc:
            return err(exc)
    return ok(data)
