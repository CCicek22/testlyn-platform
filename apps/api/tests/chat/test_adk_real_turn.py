"""A real ADK turn with a fake model: no network, no stubbed runner.

The other chat tests stub ``get_runner``. This one drives the real ``Runner``,
session service, tool-calling loop and state handling, so an ADK upgrade that
changes any of them fails here.
"""

from collections.abc import AsyncGenerator

from google.adk import Agent, Runner
from google.adk.agents.context import Context
from google.adk.events import Event, EventActions
from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.adk.sessions import InMemorySessionService
from google.genai import types as genai_types

from testlyn_api.chat.tools._helpers import SESSION_KEY_USER_TOKEN

APP = "adk-real-turn"


def read_token(tool_context: Context) -> str:
    """Return the user token held in session state."""
    return f"token={tool_context.state.get(SESSION_KEY_USER_TOKEN)}"


class FakeLlm(BaseLlm):
    """Calls ``read_token`` once, then answers with plain text."""

    model: str = "fake"

    async def generate_content_async(
        self, llm_request: LlmRequest, stream: bool = False
    ) -> AsyncGenerator[LlmResponse, None]:
        last = llm_request.contents[-1]
        if any(p.function_response for p in (last.parts or [])):
            part = genai_types.Part.from_text(text="done")
        else:
            part = genai_types.Part.from_function_call(name="read_token", args={})
        yield LlmResponse(content=genai_types.Content(role="model", parts=[part]))


async def _run_turn(runner: Runner) -> tuple[list[dict], list[str]]:
    message = genai_types.Content(
        role="user", parts=[genai_types.Part.from_text(text="hi")]
    )
    events = [
        e
        async for e in runner.run_async(
            user_id="u", session_id="s", new_message=message
        )
    ]
    parts = [p for e in events if e.content for p in (e.content.parts or [])]
    tool_results = [p.function_response.response for p in parts if p.function_response]
    texts = [p.text for p in parts if p.text]
    return tool_results, texts


async def test_tool_reads_session_state_and_sees_a_refreshed_token() -> None:
    sessions = InMemorySessionService()
    agent = Agent(name="root", model=FakeLlm(), instruction="x", tools=[read_token])
    runner = Runner(app_name=APP, agent=agent, session_service=sessions)

    # First turn: the session is created with the user's token, as the chat route does.
    await sessions.create_session(
        app_name=APP,
        user_id="u",
        session_id="s",
        state={SESSION_KEY_USER_TOKEN: "tok1"},
    )
    tool_results, texts = await _run_turn(runner)
    assert tool_results == [{"result": "token=tok1"}]
    assert texts == ["done"]

    # Later turn: the route refreshes the token with a state_delta event before running.
    session = await sessions.get_session(app_name=APP, user_id="u", session_id="s")
    await sessions.append_event(
        session=session,
        event=Event(
            author="system",
            actions=EventActions(state_delta={SESSION_KEY_USER_TOKEN: "tok2"}),
        ),
    )
    tool_results, texts = await _run_turn(runner)
    assert tool_results == [{"result": "token=tok2"}]
    assert texts == ["done"]
