"""Synthetic-data generation sub-agent — stub."""

from __future__ import annotations

from google.adk.agents import Agent

from testlyn_chat.config import get_settings
from testlyn_chat.tools import synthetic_data_tools

_INSTRUCTION = """\
You are the Testlyn synthetic-data specialist.

Scope:
- List recent generation jobs
- Trigger a new generation job given a project, schema name, and row count

Confirm row counts >100k before triggering — costs add up.
"""


def build_synthetic_data_agent() -> Agent:
    s = get_settings()
    return Agent(
        name="synthetic_data_agent",
        model=s.gemini_model,
        description="Specialist for synthetic test-data generation.",
        instruction=_INSTRUCTION,
        tools=[
            synthetic_data_tools.list_synthetic_jobs,
            synthetic_data_tools.generate_synthetic_dataset,
        ],
    )
