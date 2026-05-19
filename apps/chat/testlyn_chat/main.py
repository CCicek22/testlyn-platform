"""FastAPI entrypoint for the Testlyn chat service.

Endpoints
---------
GET  /health         — liveness for Cloud Run health checks (NOT /healthz;
                       GFE intercepts /healthz on Cloud Run, returning a 200
                       before the request reaches the container).
POST /chat/stream    — SSE stream of agent events for a single user turn.

SSE contract (frozen — coordinate with `frontend` teammate before changing):
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
import structlog.stdlib
from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from google.adk import Runner
from google.adk.events import Event, EventActions
from google.genai import types as genai_types
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from testlyn_chat.agents import build_coordinator_agent
from testlyn_chat.auth import get_current_user
from testlyn_chat.config import get_settings
from testlyn_chat.session.store import get_session_service
from testlyn_chat.tools._helpers import SESSION_KEY_USER_TOKEN

structlog.configure(
    processors=[
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

log = structlog.get_logger(__name__)


app = FastAPI(
    title="Testlyn Chat",
    version="0.1.0",
    docs_url="/docs",
    redoc_url=None,
)

settings = get_settings()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.web_base_url],
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


# ---- Runner singleton -------------------------------------------------------
# Building the agent tree is non-trivial; we do it once per process.
_runner: Runner | None = None


def get_runner() -> Runner:
    global _runner
    if _runner is None:
        _runner = Runner(
            app_name=settings.app_name,
            agent=build_coordinator_agent(),
            session_service=get_session_service(),
            auto_create_session=True,
        )
    return _runner


# ---- Schemas ----------------------------------------------------------------
class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    session_id: str | None = None


# ---- Endpoints --------------------------------------------------------------
@app.get("/health")
async def health() -> dict[str, str]:
    """Liveness probe — does not touch upstream API or model."""
    return {"status": "ok", "service": settings.app_name}


@app.post("/chat/stream")
async def chat_stream(
    body: ChatRequest,
    request: Request,
    claims: dict[str, Any] = Depends(get_current_user),
) -> EventSourceResponse:
    """Stream a single user turn through the coordinator agent as SSE."""
    user_token: str = request.state.user_token
    user_id: str = claims.get("uid") or claims.get("sub") or "unknown"
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
    existing = await session_service.get_session(
        app_name=settings.app_name, user_id=user_id, session_id=session_id
    )
    if existing is None:
        existing = await session_service.create_session(
            app_name=settings.app_name,
            user_id=user_id,
            session_id=session_id,
            state={SESSION_KEY_USER_TOKEN: user_token},
        )
    else:
        # Refresh the token each turn — IDs expire after 1 hour, the client
        # rotates.
        await session_service.append_event(
            session=existing,
            event=Event(
                author="system",
                actions=EventActions(
                    state_delta={SESSION_KEY_USER_TOKEN: user_token}
                ),
            ),
        )

    new_message = genai_types.Content(
        role="user",
        parts=[genai_types.Part.from_text(text=body.message)],
    )

    async def event_stream() -> AsyncGenerator[dict[str, str], None]:
        last_author: str | None = None
        try:
            async for event in runner.run_async(
                user_id=user_id,
                session_id=session_id,
                new_message=new_message,
            ):
                # 1. Agent-switch events when the coordinator transfers to a sub.
                if event.author and event.author != last_author and event.author != "user":
                    last_author = event.author
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
                text = _extract_text(event)
                if text:
                    yield {
                        "event": "token",
                        "data": json.dumps({"text": text}),
                    }
        except Exception as exc:  # noqa: BLE001
            log.exception("chat_stream.failed", error=str(exc))
            yield {
                "event": "error",
                "data": json.dumps({"error": str(exc)}),
            }
        finally:
            yield {
                "event": "done",
                "data": json.dumps({"session_id": session_id}),
            }

    return EventSourceResponse(event_stream())


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
