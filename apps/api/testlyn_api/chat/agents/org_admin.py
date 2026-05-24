"""Organisation-admin sub-agent (orgs, members, billing)."""

from __future__ import annotations

from google.adk.agents import Agent

from testlyn_api.config import get_settings
from testlyn_api.chat.tools import org_tools

_INSTRUCTION = """\
You are the Testlyn organisation-admin specialist.

Scope:
- Look up org details and projects
- List org members
- Summarise billing (current plan, usage this period)

Never expose billing details for an org the caller is not a member of —
upstream API enforces this; if you get a 403, relay it cleanly.
"""


def build_org_admin_agent() -> Agent:
    s = get_settings()
    return Agent(
        name="org_admin_agent",
        model=s.chat_gemini_model,
        description="Specialist for organisation, project, member, and billing queries.",
        instruction=_INSTRUCTION,
        tools=[
            org_tools.get_org,
            org_tools.list_projects,
            org_tools.list_org_members,
            org_tools.get_billing_summary,
        ],
    )
