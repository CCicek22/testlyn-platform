"""Load-testing sub-agent.

Handles user intents like "kick off a load test", "show me my last load
runs", "what was the p95 of run X". Delegates back to the coordinator when
the request shifts to another product domain.
"""

from __future__ import annotations

from google.adk.agents import Agent

from testlyn_chat.config import get_settings
from testlyn_chat.tools import load_tools

_INSTRUCTION = """\
You are the Testlyn load-testing specialist.

Scope:
- Trigger load test runs (k6-powered)
- List load tests and runs
- Summarise run metrics (RPS, p50/p95/p99, error rate)
- Cancel in-flight runs

Behaviour:
- Always confirm destructive actions (cancel, repeated runs) before calling tools.
- Quote real numbers from `get_run_summary`; never invent metrics.
- If the user asks about anything outside load testing (functional, a11y,
  security, billing, etc.), say so and let the coordinator route them.
- When a tool returns `{"ok": false}`, surface the upstream error verbatim —
  don't fabricate a workaround.
"""


def build_load_agent() -> Agent:
    s = get_settings()
    return Agent(
        name="load_agent",
        model=s.gemini_model,
        description=(
            "Specialist for load testing: triggers k6 runs, lists runs, "
            "summarises p50/p95/p99 latency and error rates."
        ),
        instruction=_INSTRUCTION,
        tools=[
            load_tools.list_load_tests,
            load_tools.run_load_test,
            load_tools.list_load_runs,
            load_tools.get_run_summary,
            load_tools.cancel_run,
        ],
    )
