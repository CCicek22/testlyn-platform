"""Security (DAST / ZAP) sub-agent — stub."""

from __future__ import annotations

from google.adk.agents import Agent

from testlyn_api.config import get_settings
from testlyn_api.chat.tools import security_tools

_INSTRUCTION = """\
You are the Testlyn security specialist (DAST scans, OWASP top 10).

Scope:
- List recent security scans
- Summarise findings by severity (critical / high / medium / low / info)
- Reference CVE ids and OWASP categories where applicable

NEVER suggest exploit techniques — only summarise defender-relevant detail.
"""


def build_security_agent() -> Agent:
    s = get_settings()
    return Agent(
        name="security_agent",
        model=s.chat_gemini_model,
        description="Specialist for DAST security scans and OWASP findings.",
        instruction=_INSTRUCTION,
        tools=[
            security_tools.list_security_runs,
            security_tools.get_security_findings,
        ],
    )
