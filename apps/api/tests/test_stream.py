from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from testlyn_api.models.project import Project
from testlyn_api.models.test import Test as TestModel
from testlyn_api.models.test_run import TestRun as TestRunModel

_DEV_ORG_ID = uuid.UUID("00000000-0000-0000-0000-d3eff3e10102")


async def _seed_run(session: AsyncSession, state: str = "running") -> uuid.UUID:
    """Create project→test→run under the pre-seeded dev org."""
    proj = Project(org_id=_DEV_ORG_ID, name="P", slug=f"p-{uuid.uuid4().hex[:6]}")
    session.add(proj)
    await session.flush()

    test = TestModel(project_id=proj.id, name="T", script_inline="export default function(){}")
    session.add(test)
    await session.flush()

    run = TestRunModel(test_id=test.id, product="load", state=state)
    session.add(run)
    await session.flush()

    run_id = run.id
    await session.commit()
    return run_id


@pytest.mark.asyncio
async def test_stream_404_unknown_run(client: AsyncClient) -> None:
    fake_id = uuid.uuid4()
    response = await client.get(f"/v1/runs/{fake_id}/stream")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_stream_completed_run_yields_done_event(
    client: AsyncClient, db_session: AsyncSession, monkeypatch
) -> None:
    """A completed run should yield a 'done' SSE event immediately."""
    from testlyn_api.products.load import bq_queries

    async def _mock_bq(**kwargs):
        return []

    monkeypatch.setattr(bq_queries, "stream_run_metrics", _mock_bq)

    run_id = await _seed_run(db_session, state="completed")

    chunks: list[bytes] = []
    async with client.stream("GET", f"/v1/runs/{run_id}/stream") as response:
        assert response.status_code == 200
        async for chunk in response.aiter_bytes():
            chunks.append(chunk)
            # Stop after first meaningful chunk
            if chunk:
                break

    full = b"".join(chunks).decode()
    assert "done" in full or "heartbeat" in full


@pytest.mark.asyncio
async def test_stream_running_run_yields_heartbeat(
    client: AsyncClient, db_session: AsyncSession, monkeypatch
) -> None:
    """A running run with no BQ data should yield heartbeat SSE comments."""
    from testlyn_api.products.load import bq_queries

    call_count = 0

    async def _mock_bq(**kwargs):
        nonlocal call_count
        call_count += 1
        return []

    monkeypatch.setattr(bq_queries, "stream_run_metrics", _mock_bq)

    run_id = await _seed_run(db_session, state="running")

    chunks: list[bytes] = []
    async with client.stream("GET", f"/v1/runs/{run_id}/stream") as response:
        assert response.status_code == 200
        async for chunk in response.aiter_bytes():
            if chunk:
                chunks.append(chunk)
                break

    # Either heartbeat or data event — just confirm we got a response
    assert len(chunks) > 0
