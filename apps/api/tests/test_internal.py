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
async def test_cancel_running_run_stops_runner_and_keeps_quota(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cancelling a RUNNING run must call runner.cancel but NOT release quota.

    The run already launched and consumed engine resources — releasing quota
    here would let users run unlimited tests by cancelling before completion.
    """
    from datetime import UTC, datetime

    from sqlalchemy import select
    from testlyn_api.core.runner_registry import RUNNERS
    from testlyn_api.models.org import Organization
    from testlyn_api.models.usage import UsageRecord
    from testlyn_api.services.quota import QuotaService

    run_id = await _create_run(db_session)
    run = await db_session.get(TestRunModel, run_id)
    assert run is not None
    run.state = "running"
    run.runner_id = (
        "projects/p/locations/us-central1/jobs/testlyn-engine/executions/exec-1"
    )

    # Record one usage unit so we can observe it is NOT released.
    org = await db_session.get(Organization, _DEV_ORG_ID)
    assert org is not None
    await QuotaService(db_session).record_usage(org, run)
    await db_session.commit()

    cancelled: list[str] = []

    async def _fake_cancel(self, *, runner_id: str) -> None:  # type: ignore[no-untyped-def]
        cancelled.append(runner_id)

    monkeypatch.setattr(type(RUNNERS["load"]), "cancel", _fake_cancel, raising=True)

    resp = await client.post(f"/v1/runs/{run_id}/cancel")
    assert resp.status_code == 200, resp.text
    assert resp.json()["state"] == "cancelled"

    # Runner was actually stopped.
    assert cancelled == [run.runner_id]

    # Quota was NOT reversed — the run launched and consumed resources.
    month = datetime.now(UTC).strftime("%Y-%m")
    record = (
        await db_session.execute(
            select(UsageRecord).where(
                UsageRecord.org_id == _DEV_ORG_ID, UsageRecord.month == month
            )
        )
    ).scalar_one()
    assert record.runs_count == 1


@pytest.mark.asyncio
async def test_cancel_queued_run_skips_runner_cancel_and_releases_quota(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A still-queued run has no runner_id — runner.cancel must NOT be called,
    and quota IS released (the run never launched)."""
    from datetime import UTC, datetime

    from sqlalchemy import select
    from testlyn_api.core.runner_registry import RUNNERS
    from testlyn_api.models.org import Organization
    from testlyn_api.models.usage import UsageRecord
    from testlyn_api.services.quota import QuotaService

    run_id = await _create_run(db_session)  # state defaults to queued, runner_id None
    run = await db_session.get(TestRunModel, run_id)
    assert run is not None
    org = await db_session.get(Organization, _DEV_ORG_ID)
    assert org is not None
    await QuotaService(db_session).record_usage(org, run)
    await db_session.commit()

    called: list[str] = []

    async def _fake_cancel(self, *, runner_id: str) -> None:  # type: ignore[no-untyped-def]
        called.append(runner_id)

    monkeypatch.setattr(type(RUNNERS["load"]), "cancel", _fake_cancel, raising=True)

    resp = await client.post(f"/v1/runs/{run_id}/cancel")
    assert resp.status_code == 200, resp.text
    assert resp.json()["state"] == "cancelled"
    assert called == []

    # Quota released — the run never launched.
    month = datetime.now(UTC).strftime("%Y-%m")
    record = (
        await db_session.execute(
            select(UsageRecord).where(
                UsageRecord.org_id == _DEV_ORG_ID, UsageRecord.month == month
            )
        )
    ).scalar_one()
    assert record.runs_count == 0


@pytest.mark.asyncio
async def test_cancel_run_marks_cancelled_even_if_runner_raises(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If runner.cancel raises, the run is still marked cancelled (best-effort stop)."""
    from testlyn_api.core.runner_registry import RUNNERS

    run_id = await _create_run(db_session)
    run = await db_session.get(TestRunModel, run_id)
    assert run is not None
    run.state = "running"
    run.runner_id = "exec-boom"
    await db_session.commit()

    async def _boom(self, *, runner_id: str) -> None:  # type: ignore[no-untyped-def]
        raise RuntimeError("cloud run unreachable")

    monkeypatch.setattr(type(RUNNERS["load"]), "cancel", _boom, raising=True)

    resp = await client.post(f"/v1/runs/{run_id}/cancel")
    assert resp.status_code == 200, resp.text
    assert resp.json()["state"] == "cancelled"


async def _create_test(session: AsyncSession) -> uuid.UUID:
    """Seed project + test under the dev org; return the test id."""
    proj = Project(org_id=_DEV_ORG_ID, name="P", slug=f"p-{uuid.uuid4().hex[:6]}")
    session.add(proj)
    await session.flush()
    test = TestModel(project_id=proj.id, name="T", script_inline="export default function(){}")
    session.add(test)
    await session.flush()
    test_id = test.id
    await session.commit()
    return test_id


_INTERNAL_TOKEN = "s3cr3t-internal-token"


@pytest.fixture
def cloud_mode_settings(monkeypatch):
    from testlyn_api.config import get_settings

    cloud = get_settings().model_copy(
        update={
            "run_mode": "cloud",
            "dev_auth_bypass": False,
            "internal_token": _INTERNAL_TOKEN,
        }
    )
    monkeypatch.setattr("testlyn_api.config.get_settings", lambda: cloud)
    return cloud


@pytest.mark.asyncio
async def test_internal_create_run_docker_no_token(
    client: AsyncClient, db_session: AsyncSession, monkeypatch
) -> None:
    """docker dev mode bypasses the token gate and creates a queued run."""
    from testlyn_api.core import tasks

    async def _noop(_):
        pass

    monkeypatch.setattr(tasks, "enqueue_run", _noop)

    test_id = await _create_test(db_session)
    resp = await client.post(f"/v1/internal/tests/{test_id}/runs")
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["state"] == "queued"
    assert data["product"] == "load"
    assert data["triggered_by"] is None


@pytest.mark.asyncio
async def test_internal_create_run_test_not_found(client: AsyncClient) -> None:
    resp = await client.post(f"/v1/internal/tests/{uuid.uuid4()}/runs")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_internal_create_run_correct_token(
    client: AsyncClient, db_session: AsyncSession, cloud_mode_settings, monkeypatch
) -> None:
    from testlyn_api.core import tasks

    async def _noop(_):
        pass

    monkeypatch.setattr(tasks, "enqueue_run", _noop)

    test_id = await _create_test(db_session)
    resp = await client.post(
        f"/v1/internal/tests/{test_id}/runs",
        headers={"X-Internal-Token": _INTERNAL_TOKEN},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["state"] == "queued"


@pytest.mark.asyncio
async def test_internal_create_run_no_token_forbidden(
    client: AsyncClient, db_session: AsyncSession, cloud_mode_settings
) -> None:
    test_id = await _create_test(db_session)
    resp = await client.post(f"/v1/internal/tests/{test_id}/runs")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_internal_create_run_wrong_token_forbidden(
    client: AsyncClient, db_session: AsyncSession, cloud_mode_settings
) -> None:
    test_id = await _create_test(db_session)
    resp = await client.post(
        f"/v1/internal/tests/{test_id}/runs",
        headers={"X-Internal-Token": "nope"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_start_run_commits_running_before_launch(
    client: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """start_run must COMMIT state='running' BEFORE runner.launch.

    Cloud Tasks delivers at-least-once: a duplicate start arriving mid-launch
    must already see the committed 'running' state (and 409) instead of
    double-launching the engine job.
    """
    from datetime import UTC, datetime
    from types import SimpleNamespace

    from testlyn_api.core.db import _session_factory
    from testlyn_api.core.runner_registry import RUNNERS

    run_id = await _create_run(db_session)
    observed: dict[str, str] = {}

    async def _fake_launch(self, **kwargs):  # type: ignore[no-untyped-def]
        # Read the run state from a SEPARATE session — proves the transitional
        # state was committed (visible to other transactions) before launch.
        async with _session_factory() as other:
            row = await other.get(TestRunModel, run_id)
            assert row is not None
            observed["state_during_launch"] = row.state
        return SimpleNamespace(
            runner_id="exec-trans-1",
            started_at=datetime.now(tz=UTC),
            region="us-central1",
        )

    monkeypatch.setattr(type(RUNNERS["load"]), "launch", _fake_launch, raising=True)

    resp = await client.post(f"/v1/internal/runs/{run_id}/start")
    assert resp.status_code == 200, resp.text
    assert resp.json()["state"] == "running"
    assert observed["state_during_launch"] == "running"


@pytest.mark.asyncio
async def test_start_run_duplicate_delivery_conflicts(
    client: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Second start of the same run (duplicate Cloud Tasks delivery) → 409."""
    from datetime import UTC, datetime
    from types import SimpleNamespace

    from testlyn_api.core.runner_registry import RUNNERS

    run_id = await _create_run(db_session)
    launches: list[str] = []

    async def _fake_launch(self, **kwargs):  # type: ignore[no-untyped-def]
        launches.append("launch")
        return SimpleNamespace(
            runner_id="exec-dup-1",
            started_at=datetime.now(tz=UTC),
            region="us-central1",
        )

    monkeypatch.setattr(type(RUNNERS["load"]), "launch", _fake_launch, raising=True)

    first = await client.post(f"/v1/internal/runs/{run_id}/start")
    assert first.status_code == 200, first.text

    second = await client.post(f"/v1/internal/runs/{run_id}/start")
    assert second.status_code == 409, second.text
    assert launches == ["launch"]  # the runner launched exactly once


@pytest.mark.asyncio
async def test_create_run_enqueue_failure_marks_failed_and_releases_quota(
    client: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Enqueue failure → 502, run marked failed (not stuck queued), quota released."""
    from datetime import UTC, datetime

    from sqlalchemy import select
    from testlyn_api.core import tasks
    from testlyn_api.models.usage import UsageRecord

    async def _boom(_run_id) -> None:  # type: ignore[no-untyped-def]
        raise RuntimeError("cloud tasks down")

    monkeypatch.setattr(tasks, "enqueue_run", _boom)

    test_id = await _create_test(db_session)
    resp = await client.post(f"/v1/internal/tests/{test_id}/runs")
    assert resp.status_code == 502, resp.text

    run = (
        await db_session.execute(
            select(TestRunModel).where(TestRunModel.test_id == test_id)
        )
    ).scalar_one()
    assert run.state == "failed"
    assert "enqueue failed" in (run.error_reason or "")

    month = datetime.now(UTC).strftime("%Y-%m")
    record = (
        await db_session.execute(
            select(UsageRecord).where(
                UsageRecord.org_id == _DEV_ORG_ID, UsageRecord.month == month
            )
        )
    ).scalar_one()
    assert record.runs_count == 0


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
