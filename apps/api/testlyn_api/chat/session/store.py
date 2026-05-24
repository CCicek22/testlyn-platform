"""Session-service factory.

ADK 2.0 ships an in-memory + a SQL + a Vertex session service. For Phase 1
we use in-memory (dev) and a singleton instance per process. Production
Redis-backed persistence will be wired when the chat product graduates.
"""

from __future__ import annotations

from functools import lru_cache

from google.adk.sessions import InMemorySessionService
from google.adk.sessions.base_session_service import BaseSessionService

from testlyn_api.config import get_settings


@lru_cache(maxsize=1)
def get_session_service() -> BaseSessionService:
    """Return a process-singleton session service.

    Dev: InMemorySessionService — sessions live as long as the worker process.
    Prod (future, when ``use_redis_session=True``): swap to a Redis-backed
    implementation. ADK 2.0a1 does not ship one out of the box; for now we
    log a warning and fall back to in-memory so deploy doesn't crash.
    """
    settings = get_settings()
    if settings.chat_use_redis_session:
        import structlog

        structlog.get_logger(__name__).warning(
            "session.redis_not_implemented_falling_back_to_inmemory"
        )
    return InMemorySessionService()
