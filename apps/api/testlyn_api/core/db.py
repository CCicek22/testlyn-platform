from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any

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


def _asyncpg_connect_args(database_url: str) -> dict[str, Any]:
    """Driver connect args for PgBouncer (transaction-pooling) compatibility.

    Apps connect through PgBouncer :6432 in transaction-pooling mode (CLAUDE.md).
    SQLAlchemy's asyncpg dialect keeps a per-connection cache of server-side
    prepared statements (``prepared_statement_cache_size`` defaults to 100).
    Those cached statements go stale when DDL is applied out-of-band — e.g. an
    Alembic migration job adding ``report_uri`` to ``test_runs`` — and the next
    reuse on a pooled connection raises asyncpg ``InvalidCachedStatementError``
    ("cached plan must not change result type"), which surfaces as a 500.
    Disabling the cache re-prepares each statement, eliminating that failure
    class. Note this is the *dialect* arg (``prepared_statement_cache_size``),
    not asyncpg's native ``statement_cache_size`` — the latter does not control
    the dialect's prepared-statement cache. Only applied for the asyncpg driver;
    the sqlite+aiosqlite test backend rejects the arg.
    """
    if database_url.startswith("postgresql+asyncpg"):
        return {"prepared_statement_cache_size": 0}
    return {}


def get_engine() -> AsyncEngine:
    """Return (and create on first call) the process-wide async engine."""
    global _engine, _session_factory_singleton
    if _engine is None:
        settings = get_settings()
        _engine = create_async_engine(
            settings.database_url,
            echo=False,
            pool_pre_ping=True,
            connect_args=_asyncpg_connect_args(settings.database_url),
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
