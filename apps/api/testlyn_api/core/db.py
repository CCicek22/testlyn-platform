from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from testlyn_api.config import get_settings


class Base(DeclarativeBase):
    pass


# Lazily-built singletons. Building the engine at module import time runs the
# Settings cache lookup before tests have a chance to patch env vars and also
# opens a connection pool against a (potentially unreachable) DB just by
# importing any model module. Defer until first request via get_engine().
_engine: AsyncEngine | None = None
_session_factory_singleton: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    """Return (and create on first call) the process-wide async engine."""
    global _engine, _session_factory_singleton
    if _engine is None:
        settings = get_settings()
        _engine = create_async_engine(
            settings.database_url,
            echo=False,
            pool_pre_ping=True,
        )
        _session_factory_singleton = async_sessionmaker(_engine, expire_on_commit=False)
    return _engine


def _session_factory() -> AsyncSession:
    """Backwards-compat callable: returns a new session (use as ``async with``).

    Existing call sites do ``async with _session_factory() as session``; preserve
    that shape so the lazy-engine change is non-breaking.
    """
    if _session_factory_singleton is None:
        get_engine()
    assert _session_factory_singleton is not None  # narrowed by get_engine()
    return _session_factory_singleton()


async def get_session() -> AsyncGenerator[AsyncSession]:
    if _session_factory_singleton is None:
        get_engine()
    assert _session_factory_singleton is not None
    async with _session_factory_singleton() as session:
        yield session
