from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from testlyn_api.models.org import Organization
from testlyn_api.models.project import Project
from testlyn_api.models.test import Test as TestModel
from testlyn_api.models.test_run import TestRun as TestRunModel

_DEV_ORG_ID = uuid.UUID("00000000-0000-0000-0000-d3eff3e10102")


async def _seed_run(session: AsyncSession, *, org_id: uuid.UUID = _DEV_ORG_ID) -> uuid.UUID:
    proj = Project(org_id=org_id, name="P", slug=f"p-{uuid.uuid4().hex[:6]}")
    session.add(proj)
    await session.flush()

    test = TestModel(project_id=proj.id, name="T", script_inline="export default function(){}")
    session.add(test)
    await session.flush()

    run = TestRunModel(test_id=test.id, product="load", state="completed")
    session.add(run)
    await session.flush()
    run_id = run.id
    await session.commit()
    return run_id


def test_run_samples_sql_has_row_cap() -> None:
    """The /samples query must cap rows so a multi-hour run can't dump tens of
    thousands of per-second rows."""
    from testlyn_api.products.load import bq_queries

    sql = bq_queries._RUN_SAMPLES_SQL.format(
        project="p", dataset="d", max_rows=bq_queries.MAX_SAMPLE_ROWS
    )
    assert f"LIMIT {bq_queries.MAX_SAMPLE_ROWS}" in sql
    assert bq_queries.MAX_SAMPLE_ROWS == 86_400
    # Cap keeps the leading window (ORDER BY ts ASC then LIMIT).
    assert sql.index("ORDER BY ts ASC") < sql.index("LIMIT")


@pytest.mark.asyncio
async def test_samples_404_unknown_run(client: AsyncClient) -> None:
    resp = await client.get(f"/v1/runs/{uuid.uuid4()}/samples")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_samples_non_member_forbidden(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """A run in an org the caller doesn't belong to → 403 (no BQ query reached)."""
    other_org = Organization(name="Other", slug=f"other-{uuid.uuid4().hex[:6]}", plan="free")
    db_session.add(other_org)
    await db_session.flush()
    run_id = await _seed_run(db_session, org_id=other_org.id)

    resp = await client.get(f"/v1/runs/{run_id}/samples")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_samples_empty_array_when_no_rows(
    client: AsyncClient, db_session: AsyncSession, monkeypatch
) -> None:
    from testlyn_api.products.load import bq_queries

    async def _empty(**kwargs):
        return []

    monkeypatch.setattr(bq_queries, "fetch_run_samples", _empty)

    run_id = await _seed_run(db_session)
    resp = await client.get(f"/v1/runs/{run_id}/samples")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_samples_returns_rows_in_time_order(
    client: AsyncClient, db_session: AsyncSession, monkeypatch
) -> None:
    from testlyn_api.products.load import bq_queries

    rows = [
        {"ts": "2026-06-03T00:00:01+00:00", "p95_duration_ms": 120.0, "error_rate": 0.0, "vus": 5},
        {"ts": "2026-06-03T00:00:02+00:00", "p95_duration_ms": 130.0, "error_rate": 0.1, "vus": 5},
    ]

    captured: dict = {}

    async def _fake(*, run_id, project, dataset):  # noqa: ANN001
        captured["run_id"] = run_id
        return rows

    monkeypatch.setattr(bq_queries, "fetch_run_samples", _fake)

    run_id = await _seed_run(db_session)
    resp = await client.get(f"/v1/runs/{run_id}/samples")
    assert resp.status_code == 200
    body = resp.json()
    assert [r["ts"] for r in body] == [rows[0]["ts"], rows[1]["ts"]]
    assert body[0]["vus"] == 5
    assert captured["run_id"] == run_id
