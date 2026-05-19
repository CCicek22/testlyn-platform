"""Functional (E2E / Playwright) sub-agent — stub."""

from __future__ import annotations

from google.adk.agents import Agent

from testlyn_chat.config import get_settings
from testlyn_chat.tools import functional_tools

_INSTRUCTION = """\
You are the Testlyn functional-testing specialist (Playwright E2E flows).

Scope:
- List functional tests in a project
- Trigger functional test runs

This product is still under development — many endpoints are not yet wired.
If a tool returns a 404 or "not implemented" error, tell the user honestly
and let the coordinator know.
"""


def build_functional_agent() -> Agent:
    s = get_settings()
    return Agent(
        name="functional_agent",
        model=s.gemini_model,
        description="Specialist for Playwright E2E functional tests.",
        instruction=_INSTRUCTION,
        tools=[
            functional_tools.list_functional_tests,
            functional_tools.run_functional_test,
        ],
    )
