"""Postgres tests run against a real database, not the SQLite conftest engine.

Tests here drop and recreate the ``public`` schema of the database named by
``TEST_POSTGRES_URL``. Point it only at a throwaway database.

The autouse fixtures of ``tests/conftest.py`` (SQLite create_all, dev seed,
fakeredis flush) are overridden below with no-ops.
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import AsyncIterator, Callable
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

API_DIR = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def _require_postgres() -> None:
    if not os.environ.get("TEST_POSTGRES_URL"):
        pytest.skip("TEST_POSTGRES_URL is not set")


@pytest.fixture
def postgres_url() -> str:
    return os.environ["TEST_POSTGRES_URL"]


@pytest.fixture
def run_alembic(postgres_url: str) -> Callable[..., subprocess.CompletedProcess[str]]:
    """Run the repo's Alembic CLI in a fresh process (env.py calls asyncio.run)."""

    def _run(*args: str) -> subprocess.CompletedProcess[str]:
        env = {**os.environ, "DATABASE_URL": postgres_url}
        return subprocess.run(
            [sys.executable, "-m", "alembic", *args],
            cwd=API_DIR,
            env=env,
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
        )

    return _run


@pytest_asyncio.fixture
async def engine(postgres_url: str) -> AsyncIterator[AsyncEngine]:
    eng = create_async_engine(postgres_url, poolclass=NullPool)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def fresh_schema(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))


@pytest_asyncio.fixture
async def migrated(
    run_alembic: Callable[..., subprocess.CompletedProcess[str]], fresh_schema: None
) -> None:
    result = run_alembic("upgrade", "head")
    assert result.returncode == 0, result.stderr


@pytest_asyncio.fixture
async def session(engine: AsyncEngine, migrated: None) -> AsyncIterator[AsyncSession]:
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        yield s


# Override the SQLite-only autouse fixtures from tests/conftest.py.
@pytest.fixture(autouse=True)
def setup_db() -> None:
    return None


@pytest.fixture(autouse=True)
def _seed_dev_entities() -> None:
    return None


@pytest.fixture(autouse=True)
def _reset_rate_limit_store() -> None:
    return None
