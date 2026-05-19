"""API-contract (OpenAPI diff) sub-agent — stub."""

from __future__ import annotations

from google.adk.agents import Agent

from testlyn_chat.config import get_settings
from testlyn_chat.tools import api_contract_tools

_INSTRUCTION = """\
You are the Testlyn API-contract specialist (OpenAPI breaking-change diffs).

Scope:
- List recent contract checks
- Surface breaking changes between two OpenAPI specs (removed paths,
  required-becoming-optional, response-shape drift, etc.)

Be precise — call out the exact path, method, and field in each finding.
"""


def build_api_contract_agent() -> Agent:
    s = get_settings()
    return Agent(
        name="api_contract_agent",
        model=s.gemini_model,
        description="Specialist for OpenAPI contract diff and breaking-change detection.",
        instruction=_INSTRUCTION,
        tools=[
            api_contract_tools.list_api_contract_runs,
            api_contract_tools.get_contract_diff,
        ],
    )
