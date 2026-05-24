"""Coordinator agent construction smoke test.

Building the agent graph exercises the ADK 2.0 imports, the Pydantic
validation of every Agent definition, and the model-id wiring. We don't
invoke the LLM here — that's gated behind Vertex AI creds.
"""

from __future__ import annotations

import pytest

from testlyn_api.chat.agents import build_coordinator_agent


@pytest.fixture
def coordinator():
    return build_coordinator_agent()


def test_coordinator_builds_with_eight_sub_agents(coordinator) -> None:
    assert coordinator.name == "testlyn_coordinator"
    sub_names = {a.name for a in coordinator.sub_agents}
    assert sub_names == {
        "load_agent",
        "functional_agent",
        "a11y_agent",
        "api_contract_agent",
        "security_agent",
        "synthetic_data_agent",
        "org_admin_agent",
        "reports_agent",
    }


def test_every_sub_agent_has_tools(coordinator) -> None:
    for sub in coordinator.sub_agents:
        assert sub.tools, f"{sub.name} has no tools"


def test_every_agent_uses_configured_model(coordinator) -> None:
    from testlyn_api.config import get_settings

    expected = get_settings().chat_gemini_model
    assert coordinator.model == expected
    for sub in coordinator.sub_agents:
        assert sub.model == expected
