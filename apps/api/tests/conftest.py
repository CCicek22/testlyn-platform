from __future__ import annotations

import os
import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Force dev bypass + docker mode before any app imports
os.environ.setdefault("DEV_AUTH_BYPASS", "true")
os.environ.setdefault("RUN_MODE", "docker")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("GCP_PROJECT_ID", "test-project")
os.environ.setdefault("GCP_REGION", "us-central1")
os.environ.setdefault("GCS_SCRIPTS_BUCKET", "test-scripts")
os.environ.setdefault("GCS_RESULTS_BUCKET", "test-results")
os.environ.setdefault("GCS_REPORTS_BUCKET", "test-reports")
os.environ.setdefault("GCP_BQ_DATASET", "testlyn_metrics")
os.environ.setdefault("CLOUD_TASKS_QUEUE", "test-queue")
os.environ.setdefault("API_BASE_URL", "http://testserver")
os.environ.setdefault("FIREBASE_PROJECT_ID", "test-firebase")
os.environ.setdefault("WEB_BASE_URL", "http://localhost:3000")
os.environ.setdefault("K6_IMAGE_TAG", "grafana/k6:1.3.0")
os.environ.setdefault("SSE_HEARTBEAT_INTERVAL", "0.5")
os.environ.setdefault("SSE_MAX_TICKS", "1")

from testlyn_api.core.db import Base
from testlyn_api.deps import get_session
from testlyn_api.main import app

TEST_ENGINE = create_async_engine(
    "sqlite+aiosqlite:///:memory:",
    connect_args={"check_same_thread": False},
)
TestSessionLocal = async_sessionmaker(TEST_ENGINE, expire_on_commit=False)


@pytest_asyncio.fixture(scope="function", autouse=True)
async def setup_db():
    async with TEST_ENGINE.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with TEST_ENGINE.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    async with TestSessionLocal() as session:
        yield session


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncClient:
    async def _override_get_session():
        yield db_session

    app.dependency_overrides[get_session] = _override_get_session

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest.fixture
def dev_user_id() -> uuid.UUID:
    return uuid.UUID("00000000-0000-0000-0000-d3eff3e10101")


@pytest.fixture
def dev_org_id() -> uuid.UUID:
    return uuid.UUID("00000000-0000-0000-0000-d3eff3e10102")
