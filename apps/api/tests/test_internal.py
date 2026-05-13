from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from testlyn_api.models.project import Project
from testlyn_api.models.test import Test as TestModel
from testlyn_api.models.test_run import TestRun as TestRunModel


_DEV_ORG_ID = uuid.UUID("00000000-0000-0000-0000-d3eff3e10102")


async def _create_run(session: AsyncSession) -> uuid.UUID:
    """Seed minimal DB rows and return a queued run id.

    User + org rows are pre-seeded by the autouse _seed_dev_entities fixture
    in conftest; use merge() so this helper is idempotent.
    """
    org_id = _DEV_ORG_ID

    proj = Project(org_id=org_id, name="P", slug="p")
    session.add(proj)
    await session.flush()

    test = TestModel(project_id=proj.id, name="T", script_inline="export default function(){}")
    session.add(test)
    await session.flush()

    run = TestRunModel(test_id=test.id, product="load")
    session.add(run)
    await session.flush()

    run_id = run.id
    await session.commit()
    return run_id


@pytest.mark.asyncio
async def test_complete_run_success(client: AsyncClient, db_session: AsyncSession) -> None:
    run_id = await _create_run(db_session)

    response = await client.post(
        f"/v1/internal/runs/{run_id}/complete",
        json={"exit_code": 0},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["state"] == "completed"
    assert data["finished_at"] is not None


@pytest.mark.asyncio
async def test_complete_run_failure(client: AsyncClient, db_session: AsyncSession) -> None:
    run_id = await _create_run(db_session)

    response = await client.post(
        f"/v1/internal/runs/{run_id}/complete",
        json={"exit_code": 1},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["state"] == "failed"
    assert "k6 exited with code 1" in data["error_reason"]


@pytest.mark.asyncio
async def test_complete_run_not_found(client: AsyncClient) -> None:
    fake_id = uuid.uuid4()
    response = await client.post(
        f"/v1/internal/runs/{fake_id}/complete",
        json={"exit_code": 0},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_complete_run_with_summary_uri(client: AsyncClient, db_session: AsyncSession) -> None:
    run_id = await _create_run(db_session)

    response = await client.post(
        f"/v1/internal/runs/{run_id}/complete",
        json={"exit_code": 0, "summary_uri": "gs://testlyn-prod-results/run123/summary.json"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["summary_uri"] == "gs://testlyn-prod-results/run123/summary.json"
