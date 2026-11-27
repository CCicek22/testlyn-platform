"""Top-level coordinator agent.

Routes user messages to the right product specialist via ADK's built-in
transfer_to_agent mechanism (driven by the `sub_agents=` list). Handles
small talk, scope clarification, and high-level cross-product questions
that don't fit any single specialist.
"""

from __future__ import annotations

from google.adk.agents import Agent

from testlyn_api.chat.agents.a11y import build_a11y_agent
from testlyn_api.chat.agents.api_contract import build_api_contract_agent
from testlyn_api.chat.agents.functional import build_functional_agent
from testlyn_api.chat.agents.load import build_load_agent
from testlyn_api.chat.agents.org_admin import build_org_admin_agent
from testlyn_api.chat.agents.reports import build_reports_agent
from testlyn_api.chat.agents.security import build_security_agent
from testlyn_api.chat.agents.synthetic_data import build_synthetic_data_agent
from testlyn_api.config import get_settings

_INSTRUCTION = """\
You are the Testlyn assistant. Your job is to route the user's request to
the right specialist sub-agent, OR answer directly when the question is
about the platform itself.

Specialists available:
- load_agent: load tests (k6), run triggers, p95/RPS summaries, cancel runs
- functional_agent: Playwright E2E flows (stub — many endpoints WIP)
- a11y_agent: accessibility audits (axe-core, WCAG)
- api_contract_agent: OpenAPI contract diffs and breaking-change detection
- security_agent: DAST / OWASP scans
- synthetic_data_agent: synthetic test-data generation
- org_admin_agent: organisations, projects, members, billing
- reports_agent: cross-product run lists, run detail, daily AI insights,
  PDF report URLs, search of the org's knowledge documents

Routing rules:
1. If the user names a product domain or asks for an action that clearly
   belongs to one specialist, transfer to that specialist immediately.
2. If the question is meta ("what can you do?", "which plan am I on?"),
   answer directly or hand to org_admin_agent for billing.
3. Never invent run IDs, project IDs, or metrics — always have a specialist
   call a tool first.
4. If a specialist returns an error, the user sees it as-is; don't paper
   over upstream failures.

Tone: terse, dev-to-dev, no marketing language. Reference actual numbers.
"""


def build_coordinator_agent() -> Agent:
    s = get_settings()
    return Agent(
        name="testlyn_coordinator",
        model=s.chat_gemini_model,
        description="Top-level Testlyn assistant. Routes to product specialists.",
        instruction=_INSTRUCTION,
        sub_agents=[
            build_load_agent(),
            build_functional_agent(),
            build_a11y_agent(),
            build_api_contract_agent(),
            build_security_agent(),
            build_synthetic_data_agent(),
            build_org_admin_agent(),
            build_reports_agent(),
        ],
    )
