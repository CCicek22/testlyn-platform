from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from testlyn_api.models.project import Project
from testlyn_api.models.test import Test as TestModel
from testlyn_api.models.test_run import TestRun as TestRunModel

_DEV_ORG_ID = uuid.UUID("00000000-0000-0000-0000-d3eff3e10102")
_INTERNAL_TOKEN = "s3cr3t-internal-token"


async def _create_queued_run(session: AsyncSession) -> uuid.UUID:
    proj = Project(org_id=_DEV_ORG_ID, name="P", slug=f"p-{uuid.uuid4().hex[:6]}")
    session.add(proj)
    await session.flush()

    test = TestModel(project_id=proj.id, name="T", script_inline="export default function(){}")
    session.add(test)
    await session.flush()

    run = TestRunModel(test_id=test.id, product="load", state="queued")
    session.add(run)
    await session.flush()
    run_id = run.id
    await session.commit()
    return run_id


@pytest_asyncio.fixture
def cloud_mode_settings(monkeypatch):
    """Force run_mode=cloud with a configured internal_token (no dev bypass).

    The internal router resolves ``get_settings`` lazily at call time, so
    patching the name in ``testlyn_api.config`` is enough to exercise the real
    cloud-mode token gate instead of the docker dev-bypass path.
    """
    from testlyn_api.config import get_settings

    base = get_settings()
    cloud = base.model_copy(
        update={
            "run_mode": "cloud",
            "dev_auth_bypass": False,
            "internal_token": _INTERNAL_TOKEN,
        }
    )
    monkeypatch.setattr("testlyn_api.config.get_settings", lambda: cloud)
    return cloud


@pytest.mark.asyncio
async def test_cloud_unconfigured_secret_returns_401(
    client: AsyncClient, db_session: AsyncSession, monkeypatch
) -> None:
    """Cloud mode with NO internal_token configured must hard-fail 401, never bypass."""
    from testlyn_api.config import get_settings

    cloud = get_settings().model_copy(
        update={"run_mode": "cloud", "dev_auth_bypass": False, "internal_token": ""}
    )
    monkeypatch.setattr("testlyn_api.config.get_settings", lambda: cloud)

    run_id = await _create_queued_run(db_session)
    resp = await client.post(
        f"/v1/internal/runs/{run_id}/complete",
        json={"exit_code": 0},
        headers={"X-Internal-Token": "anything"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_cloud_no_token_returns_403(
    client: AsyncClient, db_session: AsyncSession, cloud_mode_settings
) -> None:
    """Configured secret + missing header → 403 (not silently allowed)."""
    run_id = await _create_queued_run(db_session)
    resp = await client.post(f"/v1/internal/runs/{run_id}/complete", json={"exit_code": 0})
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_cloud_wrong_token_returns_403(
    client: AsyncClient, db_session: AsyncSession, cloud_mode_settings
) -> None:
    run_id = await _create_queued_run(db_session)
    resp = await client.post(
        f"/v1/internal/runs/{run_id}/complete",
        json={"exit_code": 0},
        headers={"X-Internal-Token": "wrong-token"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_cloud_correct_token_proceeds(
    client: AsyncClient, db_session: AsyncSession, cloud_mode_settings
) -> None:
    run_id = await _create_queued_run(db_session)
    resp = await client.post(
        f"/v1/internal/runs/{run_id}/complete",
        json={"exit_code": 0},
        headers={"X-Internal-Token": _INTERNAL_TOKEN},
    )
    assert resp.status_code == 200
    assert resp.json()["state"] == "completed"


# ─── report-ready endpoint ────────────────────────────────────────────────────

_REPORT_URI = "gs://testlyn-prod-reports/org/run/report.pdf"


@pytest.mark.asyncio
async def test_report_ready_unconfigured_secret_returns_401(
    client: AsyncClient, db_session: AsyncSession, monkeypatch
) -> None:
    from testlyn_api.config import get_settings

    cloud = get_settings().model_copy(
        update={"run_mode": "cloud", "dev_auth_bypass": False, "internal_token": ""}
    )
    monkeypatch.setattr("testlyn_api.config.get_settings", lambda: cloud)

    run_id = await _create_queued_run(db_session)
    resp = await client.post(
        f"/v1/internal/runs/{run_id}/report-ready",
        json={"report_gcs_uri": _REPORT_URI},
        headers={"X-Internal-Token": "anything"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_report_ready_no_token_returns_403(
    client: AsyncClient, db_session: AsyncSession, cloud_mode_settings
) -> None:
    run_id = await _create_queued_run(db_session)
    resp = await client.post(
        f"/v1/internal/runs/{run_id}/report-ready",
        json={"report_gcs_uri": _REPORT_URI},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_report_ready_wrong_token_returns_403(
    client: AsyncClient, db_session: AsyncSession, cloud_mode_settings
) -> None:
    run_id = await _create_queued_run(db_session)
    resp = await client.post(
        f"/v1/internal/runs/{run_id}/report-ready",
        json={"report_gcs_uri": _REPORT_URI},
        headers={"X-Internal-Token": "wrong-token"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_report_ready_correct_token_persists_uri(
    client: AsyncClient, db_session: AsyncSession, cloud_mode_settings
) -> None:
    run_id = await _create_queued_run(db_session)
    resp = await client.post(
        f"/v1/internal/runs/{run_id}/report-ready",
        json={"report_gcs_uri": _REPORT_URI},
        headers={"X-Internal-Token": _INTERNAL_TOKEN},
    )
    assert resp.status_code == 200
    assert resp.json()["report_uri"] == _REPORT_URI

    # The persisted run row carries the report URI.
    fetched = await db_session.get(TestRunModel, run_id)
    assert fetched is not None
    assert fetched.report_uri == _REPORT_URI
