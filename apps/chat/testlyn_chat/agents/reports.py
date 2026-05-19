"""Reports / insights sub-agent (cross-product)."""

from __future__ import annotations

from google.adk.agents import Agent

from testlyn_chat.config import get_settings
from testlyn_chat.tools import report_tools

_INSTRUCTION = """\
You are the Testlyn reports specialist.

Scope:
- List recent runs across any product
- Fetch detail for a specific run
- Fetch latest daily AI insights snapshot for an org
- Resolve a signed URL to a PDF report for a run

When summarising insights, lead with the headline finding, then the
supporting metric, then the recommended next step.
"""


def build_reports_agent() -> Agent:
    s = get_settings()
    return Agent(
        name="reports_agent",
        model=s.gemini_model,
        description=(
            "Cross-product reports + insights: lists runs, fetches detail, "
            "summarises daily AI insights, returns signed PDF report URLs."
        ),
        instruction=_INSTRUCTION,
        tools=[
            report_tools.list_runs,
            report_tools.get_run_detail,
            report_tools.get_insights_latest,
            report_tools.get_report_url,
        ],
    )
