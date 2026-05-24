"""Accessibility (axe-core) sub-agent — stub."""

from __future__ import annotations

from google.adk.agents import Agent

from testlyn_api.config import get_settings
from testlyn_api.chat.tools import a11y_tools

_INSTRUCTION = """\
You are the Testlyn accessibility specialist (axe-core audits).

Scope:
- List recent accessibility runs
- Surface axe-core violations grouped by severity (critical/serious/moderate/minor)

Always cite WCAG criteria when violations include them. If a tool errors,
relay the upstream message verbatim.
"""


def build_a11y_agent() -> Agent:
    s = get_settings()
    return Agent(
        name="a11y_agent",
        model=s.chat_gemini_model,
        description="Specialist for accessibility audits (axe-core, WCAG 2.x).",
        instruction=_INSTRUCTION,
        tools=[
            a11y_tools.list_a11y_runs,
            a11y_tools.get_a11y_violations,
        ],
    )
