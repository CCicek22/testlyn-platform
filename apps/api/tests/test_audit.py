from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from testlyn_api.models.audit_log import AuditLog
from testlyn_api.models.org import Organization

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _scaffold_org_project_test(client: AsyncClient) -> tuple[str, str, str]:
    """Create org → project → test, return (org_id, project_id, test_id)."""
    org_resp = await client.post("/v1/orgs", json={"name": "AuditOrg"})
    assert org_resp.status_code == 201
    org_id = org_resp.json()["id"]

    proj_resp = await client.post(
        f"/v1/orgs/{org_id}/projects", json={"name": "AuditProj", "slug": "audit-proj"}
    )
    assert proj_resp.status_code == 201
    proj_id = proj_resp.json()["id"]

    test_resp = await client.post(
        f"/v1/projects/{proj_id}/tests",
        json={
            "name": "Audit Test",
            "script_inline": "export default function() {}",
            "config": {"vus": 1, "duration_seconds": 10},
        },
    )
    assert test_resp.status_code == 201
    test_id = test_resp.json()["id"]
    return org_id, proj_id, test_id


# ---------------------------------------------------------------------------
# POST test_run → audit row created
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_run_writes_audit_row(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch,
) -> None:
    from testlyn_api.core import tasks

    async def _noop(_): pass
    monkeypatch.setattr(tasks, "enqueue_run", _noop)

    org_id, _, test_id = await _scaffold_org_project_test(client)

    run_resp = await client.post(f"/v1/tests/{test_id}/runs", json={})
    assert run_resp.status_code == 201
    run_id = run_resp.json()["id"]

    result = await db_session.execute(select(AuditLog).where(AuditLog.org_id == uuid.UUID(org_id)))
    rows = result.scalars().all()
    assert len(rows) >= 1

    run_row = next(
        (r for r in rows if r.action == "test_run.created"),
        None,
    )
    assert run_row is not None, (
        f"Expected test_run.created audit row; got: {[r.action for r in rows]}"
    )
    assert run_row.resource_type == "test_run"
    assert str(run_row.resource_id) == run_id
    assert run_row.after is not None
    assert run_row.after["state"] == "queued"


# ---------------------------------------------------------------------------
# AuditService.write — direct unit test
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_audit_service_write_creates_row(db_session: AsyncSession) -> None:
    from testlyn_api.core.audit import AuditContext, AuditService

    # Seed an org so FK doesn't fail
    org = Organization(name="DirectAuditOrg", slug=f"direct-audit-{uuid.uuid4().hex[:6]}")
    db_session.add(org)
    await db_session.flush()

    ctx = AuditContext(
        ip="127.0.0.1",
        user_agent="pytest",
        actor_user_id=None,
        org_id=org.id,
        _session=db_session,
    )
    svc = AuditService(ctx)

    resource_id = uuid.uuid4()
    await svc.write(
        action="org.created",
        resource_type="organization",
        resource_id=resource_id,
        after={"name": "DirectAuditOrg"},
    )
    await db_session.flush()

    result = await db_session.execute(select(AuditLog).where(AuditLog.org_id == org.id))
    rows = result.scalars().all()
    assert len(rows) == 1
    row = rows[0]
    assert row.action == "org.created"
    assert row.resource_type == "organization"
    assert str(row.resource_id) == str(resource_id)
    assert row.after == {"name": "DirectAuditOrg"}
    assert row.before is None
    assert row.ip == "127.0.0.1"


@pytest.mark.asyncio
async def test_audit_service_before_after_diff(db_session: AsyncSession) -> None:
    """Write with both before and after payloads (simulating PATCH)."""
    from testlyn_api.core.audit import AuditContext, AuditService

    org = Organization(name="PatchOrg", slug=f"patch-org-{uuid.uuid4().hex[:6]}")
    db_session.add(org)
    await db_session.flush()

    ctx = AuditContext(
        ip=None,
        user_agent=None,
        actor_user_id=None,
        org_id=org.id,
        _session=db_session,
    )
    svc = AuditService(ctx)

    await svc.write(
        action="test.updated",
        resource_type="test",
        resource_id=uuid.uuid4(),
        before={"name": "Old Name"},
        after={"name": "New Name"},
    )
    await db_session.flush()

    result = await db_session.execute(
        select(AuditLog).where(AuditLog.org_id == org.id, AuditLog.action == "test.updated")
    )
    row = result.scalar_one()
    assert row.before == {"name": "Old Name"}
    assert row.after == {"name": "New Name"}


@pytest.mark.asyncio
async def test_audit_service_skips_without_org(db_session: AsyncSession) -> None:
    """write() with no org_id should not raise — just skip + warn."""
    from testlyn_api.core.audit import AuditContext, AuditService

    ctx = AuditContext(
        ip=None,
        user_agent=None,
        actor_user_id=None,
        org_id=None,  # deliberately missing
        _session=db_session,
    )
    svc = AuditService(ctx)

    # Must not raise
    await svc.write(action="something.happened", resource_type="something")

    result = await db_session.execute(select(AuditLog))
    assert result.scalars().all() == []


# ---------------------------------------------------------------------------
# SIEM export wiring — audit write fans out to active sinks
# ---------------------------------------------------------------------------


async def _drain_siem_tasks() -> None:
    """Await any fire-and-forget SIEM dispatch tasks spawned by a write."""
    import asyncio

    from testlyn_api.services import audit_siem

    while audit_siem._BACKGROUND_TASKS:
        await asyncio.gather(*audit_siem._BACKGROUND_TASKS, return_exceptions=True)


def _make_service(db_session: AsyncSession, org_id: uuid.UUID):
    from testlyn_api.core.audit import AuditContext, AuditService

    ctx = AuditContext(
        ip=None,
        user_agent=None,
        actor_user_id=None,
        org_id=org_id,
        _session=db_session,
    )
    return AuditService(ctx)


async def _seed_sink(db_session: AsyncSession, org_id: uuid.UUID, *, active: bool = True):
    from testlyn_api.models.audit_siem_sink import AuditSiemSink

    sink = AuditSiemSink(
        org_id=org_id,
        kind="generic_https",
        config={"url": "https://siem.example.com/ingest"},
        active=active,
    )
    db_session.add(sink)
    await db_session.flush()
    return sink


@pytest.mark.asyncio
async def test_audit_write_dispatches_to_active_sink(
    db_session: AsyncSession, monkeypatch
) -> None:
    from testlyn_api.services import audit_siem

    org = Organization(name="SiemOrg", slug=f"siem-{uuid.uuid4().hex[:6]}")
    db_session.add(org)
    await db_session.flush()
    sink = await _seed_sink(db_session, org.id)

    calls: list[tuple] = []

    async def _capture(s, e):
        calls.append((s, e))

    monkeypatch.setattr(audit_siem, "export_event", _capture)

    svc = _make_service(db_session, org.id)
    await svc.write(action="org.created", resource_type="organization")
    await _drain_siem_tasks()

    assert len(calls) == 1
    called_sink, called_event = calls[0]
    assert called_sink.id == sink.id
    assert called_event.action == "org.created"
    assert called_event.org_id == org.id


@pytest.mark.asyncio
async def test_audit_write_no_sink_no_dispatch(
    db_session: AsyncSession, monkeypatch
) -> None:
    from testlyn_api.services import audit_siem

    org = Organization(name="NoSinkOrg", slug=f"nosink-{uuid.uuid4().hex[:6]}")
    db_session.add(org)
    await db_session.flush()

    calls: list[tuple] = []

    async def _capture(s, e):
        calls.append((s, e))

    monkeypatch.setattr(audit_siem, "export_event", _capture)

    svc = _make_service(db_session, org.id)
    await svc.write(action="org.created", resource_type="organization")
    await _drain_siem_tasks()

    assert calls == []


@pytest.mark.asyncio
async def test_audit_write_inactive_sink_no_dispatch(
    db_session: AsyncSession, monkeypatch
) -> None:
    from testlyn_api.services import audit_siem

    org = Organization(name="InactiveSinkOrg", slug=f"inact-{uuid.uuid4().hex[:6]}")
    db_session.add(org)
    await db_session.flush()
    await _seed_sink(db_session, org.id, active=False)

    calls: list[tuple] = []

    async def _capture(s, e):
        calls.append((s, e))

    monkeypatch.setattr(audit_siem, "export_event", _capture)

    svc = _make_service(db_session, org.id)
    await svc.write(action="org.created", resource_type="organization")
    await _drain_siem_tasks()

    assert calls == []


@pytest.mark.asyncio
async def test_audit_write_survives_sink_failure(
    db_session: AsyncSession, monkeypatch
) -> None:
    """A sink whose export_event raises must NOT fail the audit write."""
    from testlyn_api.services import audit_siem

    org = Organization(name="FailSinkOrg", slug=f"fail-{uuid.uuid4().hex[:6]}")
    db_session.add(org)
    await db_session.flush()
    await _seed_sink(db_session, org.id)

    async def _boom(s, e):
        raise RuntimeError("SIEM down")

    monkeypatch.setattr(audit_siem, "export_event", _boom)

    svc = _make_service(db_session, org.id)
    # Must not raise despite the failing sink.
    await svc.write(action="org.created", resource_type="organization")
    await _drain_siem_tasks()

    # Audit row still committed.
    await db_session.flush()
    result = await db_session.execute(select(AuditLog).where(AuditLog.org_id == org.id))
    assert len(result.scalars().all()) == 1


@pytest.mark.asyncio
async def test_quota_exceeded_blocks_run(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch,
) -> None:
    """Free org at monthly limit returns 402 with QUOTA_EXCEEDED code."""
    from datetime import UTC, datetime

    from testlyn_api.core import tasks

    async def _noop(_): pass
    monkeypatch.setattr(tasks, "enqueue_run", _noop)

    org_id, _, test_id = await _scaffold_org_project_test(client)

    # Exhaust free tier (5 runs) by stuffing usage_records
    from testlyn_api.models.usage import UsageRecord

    month = datetime.now(UTC).strftime("%Y-%m")
    record = UsageRecord(org_id=uuid.UUID(org_id), month=month, runs_count=5, vu_seconds_total=0)
    db_session.add(record)
    await db_session.commit()

    run_resp = await client.post(f"/v1/tests/{test_id}/runs", json={})
    assert run_resp.status_code == 402
    body = run_resp.json()
    # FastAPI wraps HTTPException.detail under "detail" key
    detail = body["detail"]
    assert detail["code"] == "QUOTA_EXCEEDED"
    assert detail["limits"]["tests_per_month"] == 5
