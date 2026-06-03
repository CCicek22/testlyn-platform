"""In-process chat router for testlyn-api.

Ported from the standalone testlyn-chat service. The coordinator agent + its
product sub-agents run in the api process; their tools call back into the api's
own /v1/* endpoints over loopback HTTP carrying the END-USER's Firebase bearer
token (Option A — loopback), so the API's existing auth, RBAC, audit, and
rate-limit guarantees still apply.

SSE contract (frozen — coordinate with the web app before changing):
- Request body: ``{"message": str, "session_id": str | null}``
- Request header: ``Authorization: Bearer <firebase_id_token>``
- Response: ``text/event-stream`` with these named events:
    event: token         data: {"text": "..."}
    event: tool_call     data: {"tool": "...", "args": {...}}
    event: tool_result   data: {"tool": "...", "ok": bool, "result_preview": "..."}
    event: agent_switch  data: {"to": "load_agent"}
    event: done          data: {"session_id": "..."}
"""

from __future__ import annotations

import json
import uuid
from typing import Any, AsyncGenerator

import structlog
from fastapi import APIRouter, Request
from google.adk import Runner
from google.adk.events import Event, EventActions
from google.genai import types as genai_types
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from testlyn_api.chat.agents import build_coordinator_agent
from testlyn_api.chat.session.store import get_session_service
from testlyn_api.chat.tools._helpers import (
    SESSION_KEY_ORG_ID,
    SESSION_KEY_PROJECT_ID,
    SESSION_KEY_USER_TOKEN,
)
from testlyn_api.chat.tools.testlyn_client import TestlynAPIError
from testlyn_api.config import get_settings
from testlyn_api.deps import CurrentUserDep

log = structlog.get_logger(__name__)

router = APIRouter()


# ---- Runner singleton -------------------------------------------------------
# Building the agent tree is non-trivial; we do it once per process.
_runner: Runner | None = None


def get_runner() -> Runner:
    global _runner
    if _runner is None:
        settings = get_settings()
        _runner = Runner(
            app_name=settings.chat_app_name,
            agent=build_coordinator_agent(),
            session_service=get_session_service(),
            auto_create_session=True,
        )
    return _runner


# ---- Schemas ----------------------------------------------------------------
class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    session_id: str | None = Field(
        default=None,
        max_length=64,
        pattern=r"^[a-zA-Z0-9_-]+$",
    )
    # The project/org the user has selected in the UI. Seeded into ADK session
    # state so tools can act on the active project without the user pasting a
    # UUID (e.g. "run a load test on example.com"). Tools validate these, so we
    # only length-bound here.
    project_id: str | None = Field(default=None, max_length=64)
    org_id: str | None = Field(default=None, max_length=64)


# ---- Endpoints --------------------------------------------------------------
@router.post("/chat/stream")
async def chat_stream(
    body: ChatRequest,
    request: Request,
    current_user: CurrentUserDep,
) -> EventSourceResponse:
    """Stream a single user turn through the coordinator agent as SSE."""
    settings = get_settings()
    # CurrentUser does not expose the raw bearer; read it from the header so we
    # can seed it into ADK session state for the tools to forward upstream.
    user_token = (
        request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
    )
    user_id = current_user.firebase_uid or str(current_user.id)
    session_id = body.session_id or str(uuid.uuid4())

    runner = get_runner()
    session_service = get_session_service()

    # Ensure session exists + the user's current Firebase token is persisted
    # in session state where tools can read it.
    #
    # IMPORTANT: BaseSessionService.get_session() returns a deepcopy of the
    # stored session (see InMemorySessionService._get_session_impl). Mutating
    # `existing.state` directly would NOT write through to the store, so
    # subsequent turns would read stale tokens and every upstream call would
    # 401 within the hour. We must persist via `append_event` + state_delta,
    # which the service applies to its canonical copy.
    # Seed/refresh per-turn state: the bearer token (rotates hourly) plus the
    # UI's selected project/org so tools can act on the active project.
    state_seed: dict[str, str] = {SESSION_KEY_USER_TOKEN: user_token}
    if body.project_id:
        state_seed[SESSION_KEY_PROJECT_ID] = body.project_id
    if body.org_id:
        state_seed[SESSION_KEY_ORG_ID] = body.org_id

    existing = await session_service.get_session(
        app_name=settings.chat_app_name, user_id=user_id, session_id=session_id
    )
    if existing is None:
        existing = await session_service.create_session(
            app_name=settings.chat_app_name,
            user_id=user_id,
            session_id=session_id,
            state=state_seed,
        )
    else:
        # Refresh each turn — IDs expire after 1 hour, the client rotates; and
        # the user may have switched the active project mid-conversation.
        await session_service.append_event(
            session=existing,
            event=Event(
                author="system",
                actions=EventActions(state_delta=state_seed),
            ),
        )

    new_message = genai_types.Content(
        role="user",
        parts=[genai_types.Part.from_text(text=body.message)],
    )

    async def event_stream() -> AsyncGenerator[dict[str, str], None]:
        last_author: str | None = None
        errored = False
        # When the runner streams partial text deltas (StreamingMode.SSE), ADK
        # also emits a final non-partial event carrying the FULL aggregated text
        # of the turn. Emitting both would duplicate the assistant reply on the
        # client. Track whether we've streamed partial text for the current
        # author so we can drop that trailing aggregate. Inert under the default
        # StreamingMode.NONE (no partials → nothing suppressed).
        streamed_partial = False
        try:
            async for event in runner.run_async(
                user_id=user_id,
                session_id=session_id,
                new_message=new_message,
            ):
                # 1. Agent-switch events when the coordinator transfers to a sub.
                if (
                    event.author
                    and event.author != last_author
                    and event.author != "user"
                ):
                    last_author = event.author
                    streamed_partial = False
                    yield {
                        "event": "agent_switch",
                        "data": json.dumps({"to": event.author}),
                    }

                # 2. Tool calls + results — model invocations produce function_call
                #    parts, tool runs produce function_response parts.
                for call in event.get_function_calls():
                    yield {
                        "event": "tool_call",
                        "data": json.dumps(
                            {"tool": call.name, "args": dict(call.args or {})}
                        ),
                    }
                for resp in event.get_function_responses():
                    yield {
                        "event": "tool_result",
                        "data": json.dumps(
                            {
                                "tool": resp.name,
                                "ok": _is_ok(resp.response),
                                "result_preview": _preview(resp.response),
                            }
                        ),
                    }

                # 3. Token / text streaming from the model.
                is_partial = bool(getattr(event, "partial", False))
                text = _extract_text(event)
                if text:
                    # Drop the trailing full-text aggregate that follows a
                    # partial stream (SSE mode) — it duplicates what we already
                    # sent as deltas. Always emit when no partials were streamed
                    # (NONE mode: the single event IS the reply).
                    if not is_partial and streamed_partial:
                        streamed_partial = False
                    else:
                        if is_partial:
                            streamed_partial = True
                        yield {
                            "event": "token",
                            "data": json.dumps({"text": text}),
                        }
        except TestlynAPIError as exc:
            errored = True
            log.exception("chat_stream.upstream_failed", status=exc.status_code)
            yield {
                "event": "error",
                "data": json.dumps(
                    {"error": f"upstream error (status {exc.status_code})"}
                ),
            }
        except PermissionError:
            errored = True
            log.exception("chat_stream.unauthenticated")
            yield {
                "event": "error",
                "data": json.dumps({"error": "authentication required"}),
            }
        except Exception:  # noqa: BLE001
            errored = True
            log.exception("chat_stream.failed")
            yield {
                "event": "error",
                "data": json.dumps({"error": "internal error"}),
            }
        finally:
            if not errored:
                yield {
                    "event": "done",
                    "data": json.dumps({"session_id": session_id}),
                }

    return EventSourceResponse(event_stream(), ping=20)


# ---- Event helpers ----------------------------------------------------------
def _extract_text(event: Event) -> str | None:
    """Return any text content on this event, or None.

    We stream partial events as they arrive — the frontend re-assembles. We
    skip events that are pure tool-call carriers (those produce no user-facing
    text).
    """
    if event.content is None or not event.content.parts:
        return None
    chunks: list[str] = []
    for part in event.content.parts:
        text = getattr(part, "text", None)
        if text:
            chunks.append(text)
    return "".join(chunks) if chunks else None


def _is_ok(response: Any) -> bool:
    """Best-effort 'did the tool succeed?' flag.

    Our tools return ``{"ok": bool, ...}``. Other tools (ADK built-ins) may
    not — default to True so we don't mislabel.
    """
    if isinstance(response, dict) and "ok" in response:
        return bool(response["ok"])
    return True


def _preview(response: Any, *, max_len: int = 240) -> str:
    if response is None:
        return ""
    try:
        s = json.dumps(response, default=str)
    except (TypeError, ValueError):
        s = repr(response)
    return s if len(s) <= max_len else s[:max_len] + "…"
