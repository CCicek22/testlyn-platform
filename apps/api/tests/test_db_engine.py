from __future__ import annotations

from testlyn_api.core.db import _asyncpg_connect_args


def test_asyncpg_disables_prepared_statement_cache() -> None:
    """PgBouncer txn-pool compat: the asyncpg dialect's prepared-statement cache
    must be disabled, else stale cached statements after an out-of-band DDL
    (Alembic migration) raise InvalidCachedStatementError -> 500.

    Must be the dialect arg ``prepared_statement_cache_size`` (not asyncpg's
    native ``statement_cache_size``, which does not control this cache).
    """
    args = _asyncpg_connect_args("postgresql+asyncpg://u:p@10.0.0.5:6432/testlyn")
    assert args["prepared_statement_cache_size"] == 0


def test_sqlite_gets_no_asyncpg_connect_args() -> None:
    """The sqlite+aiosqlite test backend rejects asyncpg-only connect args."""
    assert _asyncpg_connect_args("sqlite+aiosqlite:///:memory:") == {}
