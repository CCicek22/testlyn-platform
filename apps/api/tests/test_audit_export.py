"""Tests for audit log endpoints and SIEM sink CRUD.

Covers:
- GET /v1/orgs/{org_id}/audit-log  — paginated list (admin+)
- GET /v1/orgs/{org_id}/audit-log.csv  — streaming CSV export
- GET /v1/orgs/{org_id}/audit-log.json — streaming JSON export
- GET /v1/orgs/{org_id}/audit-sinks  — list sinks (owner)
- POST /v1/orgs/{org_id}/audit-sinks — create sink (owner)
- DELETE /v1/orgs/{org_id}/audit-sinks/{sink_id} — delete sink (owner)
- Non-admin blocked from audit log (403)
- Owner-only for sinks (403 for admin)
"""

from __future__ import annotations

import csv
import io
import json
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession
from testlyn_api.models.audit_log import AuditLog
from testlyn_api.models.audit_siem_sink import AuditSiemSink
from testlyn_api.models.org import Organization, OrgMember

# ── Helpers ────────────────────────────────────────────────────────────────────


async def _create_org(client: AsyncClient, name: str = "AuditExportOrg") -> str:
    resp = await client.post("/v1/orgs", json={"name": name})
    assert resp.status_code == 201
    return resp.json()["id"]


async def _set_role(db_session: AsyncSession, org_id: str, user_id: uuid.UUID, role: str) -> None:
    await db_session.execute(
        update(OrgMember)
        .where(OrgMember.org_id == uuid.UUID(org_id), OrgMember.user_id == user_id)
        .values(role=role)
    )
    await db_session.commit()


async def _seed_audit_rows(
    db_session: AsyncSession, org_id: str, count: int = 3
) -> list[AuditLog]:
    rows = []
    for i in range(count):
        row = AuditLog(
            org_id=uuid.UUID(org_id),
            action=f"test.action_{i}",
            resource_type="test",
            resource_id=uuid.uuid4(),
            after={"index": i},
        )
        db_session.add(row)
        rows.append(row)
    await db_session.commit()
    return rows


# ── Audit log list ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_admin_can_list_audit_log(
    client: AsyncClient,
    db_session: AsyncSession,
    dev_user_id: uuid.UUID,
) -> None:
    org_id = await _create_org(client, "ListAuditOrg")
    # default role is owner; set to admin
    await _set_role(db_session, org_id, dev_user_id, "admin")
    await _seed_audit_rows(db_session, org_id, 3)

    resp = await client.get(f"/v1/orgs/{org_id}/audit-log")
    assert resp.status_code == 200
    body = resp.json()
    assert "items" in body
    assert len(body["items"]) == 3
    assert body["cursor"] is None


@pytest.mark.asyncio
async def test_audit_log_pagination_cursor(
    client: AsyncClient,
    db_session: AsyncSession,
    dev_user_id: uuid.UUID,
) -> None:
    from datetime import UTC, datetime, timedelta

    org_id = await _create_org(client, "PaginateAuditOrg")
    await _set_role(db_session, org_id, dev_user_id, "admin")
    rows = await _seed_audit_rows(db_session, org_id, 5)
    # Give each row a distinct created_at so keyset pagination orders by the
    # (created_at, id) tuple deterministically (mirrors production, where
    # rows arrive at distinct timestamps).
    base = datetime(2026, 1, 1, tzinfo=UTC)
    for i, row in enumerate(rows):
        await db_session.execute(
            update(AuditLog)
            .where(AuditLog.id == row.id)
            .values(created_at=base + timedelta(minutes=i))
        )
    await db_session.commit()

    # Fetch with limit=3 — expect cursor
    resp = await client.get(f"/v1/orgs/{org_id}/audit-log?limit=3")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["items"]) == 3
    assert body["cursor"] is not None

    # Fetch next page using cursor
    cursor = body["cursor"]
    resp2 = await client.get(f"/v1/orgs/{org_id}/audit-log?limit=3&cursor={cursor}")
    assert resp2.status_code == 200
    body2 = resp2.json()
    assert len(body2["items"]) == 2  # remaining rows
    assert body2["cursor"] is None
    # No row appears on both pages.
    page1_ids = {i["id"] for i in body["items"]}
    page2_ids = {i["id"] for i in body2["items"]}
    assert page1_ids.isdisjoint(page2_ids)


@pytest.mark.asyncio
async def test_audit_log_pagination_distinct_timestamps_no_dupes(
    client: AsyncClient,
    db_session: AsyncSession,
    dev_user_id: uuid.UUID,
) -> None:
    """Keyset pagination must walk the full set exactly once when rows have
    distinct created_at values.

    Regression: filtering on the random uuid4 ``id`` alone (instead of the
    (created_at, id) ordering key) skipped/duplicated rows across pages.
    """
    from datetime import UTC, datetime, timedelta

    org_id = await _create_org(client, "PaginateDistinctTsOrg")
    await _set_role(db_session, org_id, dev_user_id, "admin")
    rows = await _seed_audit_rows(db_session, org_id, 5)

    # Spread created_at so ordering is driven by created_at, not id. Because
    # ids are random uuid4, an id-only cursor would mis-order these.
    base = datetime(2026, 1, 1, tzinfo=UTC)
    for i, row in enumerate(rows):
        await db_session.execute(
            update(AuditLog)
            .where(AuditLog.id == row.id)
            .values(created_at=base + timedelta(minutes=i))
        )
    await db_session.commit()

    seen: list[str] = []
    cursor: str | None = None
    for _ in range(10):  # safety bound
        url = f"/v1/orgs/{org_id}/audit-log?limit=2"
        if cursor:
            url += f"&cursor={cursor}"
        resp = await client.get(url)
        assert resp.status_code == 200
        body = resp.json()
        seen.extend(item["id"] for item in body["items"])
        cursor = body["cursor"]
        if cursor is None:
            break

    assert len(seen) == 5, f"expected 5 rows once, got {len(seen)}"
    assert len(set(seen)) == 5, "duplicate rows across pages"
    assert set(seen) == {str(r.id) for r in rows}
    # Newest-first ordering preserved.
    assert seen[0] == str(rows[-1].id)


@pytest.mark.asyncio
async def test_stale_cursor_returns_400(
    client: AsyncClient,
    db_session: AsyncSession,
    dev_user_id: uuid.UUID,
) -> None:
    """A cursor id that doesn't resolve within the org must 400, not silently
    restart pagination from page 1."""
    org_id = await _create_org(client, "StaleCursorOrg")
    await _set_role(db_session, org_id, dev_user_id, "admin")
    await _seed_audit_rows(db_session, org_id, 2)

    resp = await client.get(f"/v1/orgs/{org_id}/audit-log?cursor={uuid.uuid4()}")
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_cross_org_cursor_returns_400(
    client: AsyncClient,
    db_session: AsyncSession,
    dev_user_id: uuid.UUID,
) -> None:
    """A valid cursor id belonging to a DIFFERENT org must 400 — the cursor
    lookup is org-scoped."""
    org_a = await _create_org(client, "CursorOrgA")
    org_b = await _create_org(client, "CursorOrgB")
    await _set_role(db_session, org_a, dev_user_id, "admin")
    await _set_role(db_session, org_b, dev_user_id, "admin")
    rows_b = await _seed_audit_rows(db_session, org_b, 2)

    # Use org_b's row id as a cursor against org_a → must reject, not page-1.
    resp = await client.get(f"/v1/orgs/{org_a}/audit-log?cursor={rows_b[0].id}")
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_export_emits_all_rows_past_max_limit(
    client: AsyncClient,
    db_session: AsyncSession,
    dev_user_id: uuid.UUID,
    monkeypatch,
) -> None:
    """Export must paginate through the full keyset, not cap at one page, and
    must not emit the extra limit+1 keyset row.

    Shrink _MAX_LIMIT so a small seed crosses the page boundary.
    """
    from datetime import UTC, datetime, timedelta

    import testlyn_api.routers.audit as audit_mod

    monkeypatch.setattr(audit_mod, "_MAX_LIMIT", 2)

    org_id = await _create_org(client, "ExportAllOrg")
    await _set_role(db_session, org_id, dev_user_id, "admin")
    rows = await _seed_audit_rows(db_session, org_id, 5)
    base = datetime(2026, 1, 1, tzinfo=UTC)
    for i, row in enumerate(rows):
        await db_session.execute(
            update(AuditLog)
            .where(AuditLog.id == row.id)
            .values(created_at=base + timedelta(minutes=i))
        )
    await db_session.commit()

    resp = await client.get(f"/v1/orgs/{org_id}/audit-log.json")
    assert resp.status_code == 200
    data = json.loads(resp.text)
    ids = [d["id"] for d in data]
    assert len(ids) == 5, f"expected all 5 rows, got {len(ids)}"
    assert len(set(ids)) == 5, "duplicate or extra (limit+1) rows in export"
    assert set(ids) == {str(r.id) for r in rows}


@pytest.mark.asyncio
async def test_member_blocked_from_audit_log(
    client: AsyncClient,
    db_session: AsyncSession,
    dev_user_id: uuid.UUID,
) -> None:
    org_id = await _create_org(client, "MemberBlockedOrg")
    await _set_role(db_session, org_id, dev_user_id, "member")

    resp = await client.get(f"/v1/orgs/{org_id}/audit-log")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_viewer_blocked_from_audit_log(
    client: AsyncClient,
    db_session: AsyncSession,
    dev_user_id: uuid.UUID,
) -> None:
    org_id = await _create_org(client, "ViewerBlockedOrg")
    await _set_role(db_session, org_id, dev_user_id, "viewer")

    resp = await client.get(f"/v1/orgs/{org_id}/audit-log")
    assert resp.status_code == 403


# ── CSV export ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_csv_export_valid(
    client: AsyncClient,
    db_session: AsyncSession,
    dev_user_id: uuid.UUID,
) -> None:
    org_id = await _create_org(client, "CsvExportOrg")
    await _set_role(db_session, org_id, dev_user_id, "admin")
    await _seed_audit_rows(db_session, org_id, 2)

    resp = await client.get(f"/v1/orgs/{org_id}/audit-log.csv")
    assert resp.status_code == 200
    assert "text/csv" in resp.headers["content-type"]
    assert f"audit-{org_id}.csv" in resp.headers["content-disposition"]

    reader = csv.DictReader(io.StringIO(resp.text))
    rows = list(reader)
    assert len(rows) == 2
    assert "id" in reader.fieldnames  # type: ignore[operator]
    assert "action" in reader.fieldnames  # type: ignore[operator]
    assert "created_at" in reader.fieldnames  # type: ignore[operator]


@pytest.mark.asyncio
async def test_csv_export_blocked_for_member(
    client: AsyncClient,
    db_session: AsyncSession,
    dev_user_id: uuid.UUID,
) -> None:
    org_id = await _create_org(client, "CsvBlockedOrg")
    await _set_role(db_session, org_id, dev_user_id, "member")

    resp = await client.get(f"/v1/orgs/{org_id}/audit-log.csv")
    assert resp.status_code == 403


# ── JSON export ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_json_export_valid(
    client: AsyncClient,
    db_session: AsyncSession,
    dev_user_id: uuid.UUID,
) -> None:
    org_id = await _create_org(client, "JsonExportOrg")
    await _set_role(db_session, org_id, dev_user_id, "admin")
    await _seed_audit_rows(db_session, org_id, 2)

    resp = await client.get(f"/v1/orgs/{org_id}/audit-log.json")
    assert resp.status_code == 200
    assert "application/json" in resp.headers["content-type"]
    assert f"audit-{org_id}.json" in resp.headers["content-disposition"]

    data = json.loads(resp.text)
    assert isinstance(data, list)
    assert len(data) == 2
    assert "action" in data[0]
    assert "created_at" in data[0]


# ── SIEM sinks CRUD ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_owner_can_create_and_list_sink(
    client: AsyncClient,
    db_session: AsyncSession,
    dev_user_id: uuid.UUID,
) -> None:
    org_id = await _create_org(client, "SinkCreateOrg")
    # Creator is owner by default

    create_resp = await client.post(
        f"/v1/orgs/{org_id}/audit-sinks",
        json={
            "kind": "generic_https",
            "config": {"url": "https://hooks.example.com/audit"},
            "active": True,
        },
    )
    assert create_resp.status_code == 201
    sink = create_resp.json()
    assert sink["kind"] == "generic_https"
    assert sink["active"] is True
    assert sink["org_id"] == org_id

    list_resp = await client.get(f"/v1/orgs/{org_id}/audit-sinks")
    assert list_resp.status_code == 200
    items = list_resp.json()
    assert len(items) == 1
    assert items[0]["id"] == sink["id"]


@pytest.mark.asyncio
async def test_owner_can_delete_sink(
    client: AsyncClient,
    db_session: AsyncSession,
    dev_user_id: uuid.UUID,
) -> None:
    org_id = await _create_org(client, "SinkDeleteOrg")

    create_resp = await client.post(
        f"/v1/orgs/{org_id}/audit-sinks",
        json={"kind": "splunk_hec", "config": {"url": "https://splunk.example.com", "token": "abc"}},
    )
    assert create_resp.status_code == 201
    sink_id = create_resp.json()["id"]

    del_resp = await client.delete(f"/v1/orgs/{org_id}/audit-sinks/{sink_id}")
    assert del_resp.status_code == 204

    list_resp = await client.get(f"/v1/orgs/{org_id}/audit-sinks")
    assert list_resp.status_code == 200
    assert list_resp.json() == []


@pytest.mark.asyncio
async def test_delete_nonexistent_sink_returns_404(
    client: AsyncClient,
    db_session: AsyncSession,
    dev_user_id: uuid.UUID,
) -> None:
    org_id = await _create_org(client, "Sink404Org")

    resp = await client.delete(f"/v1/orgs/{org_id}/audit-sinks/{uuid.uuid4()}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_admin_blocked_from_create_sink(
    client: AsyncClient,
    db_session: AsyncSession,
    dev_user_id: uuid.UUID,
) -> None:
    org_id = await _create_org(client, "SinkAdminBlockedOrg")
    await _set_role(db_session, org_id, dev_user_id, "admin")

    resp = await client.post(
        f"/v1/orgs/{org_id}/audit-sinks",
        json={"kind": "generic_https", "config": {"url": "https://example.com"}},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_create_sink_invalid_kind(
    client: AsyncClient,
    db_session: AsyncSession,
    dev_user_id: uuid.UUID,
) -> None:
    org_id = await _create_org(client, "SinkBadKindOrg")

    resp = await client.post(
        f"/v1/orgs/{org_id}/audit-sinks",
        json={"kind": "unknown_kind", "config": {"url": "https://example.com"}},
    )
    assert resp.status_code == 422


# ── audit_siem service unit tests ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_export_event_formats_splunk(db_session: AsyncSession) -> None:
    """_fmt_splunk produces expected keys."""
    from testlyn_api.services.audit_siem import _fmt_splunk

    org = Organization(name="SiemOrg", slug=f"siem-{uuid.uuid4().hex[:6]}")
    db_session.add(org)
    await db_session.flush()

    event = AuditLog(
        org_id=org.id,
        action="test.created",
        resource_type="test",
        resource_id=uuid.uuid4(),
        after={"name": "t"},
    )
    db_session.add(event)
    await db_session.flush()

    payload = _fmt_splunk(event)
    assert payload["sourcetype"] == "testlyn:audit"
    assert "event" in payload
    assert payload["event"]["action"] == "test.created"


@pytest.mark.asyncio
async def test_export_event_formats_datadog(db_session: AsyncSession) -> None:
    from testlyn_api.services.audit_siem import _fmt_datadog

    org = Organization(name="DdOrg", slug=f"dd-{uuid.uuid4().hex[:6]}")
    db_session.add(org)
    await db_session.flush()

    event = AuditLog(
        org_id=org.id,
        action="test.deleted",
        resource_type="test",
    )
    db_session.add(event)
    await db_session.flush()

    payload = _fmt_datadog(event)
    assert payload["ddsource"] == "testlyn"
    assert "action:test.deleted" in payload["ddtags"]
    assert "message" in payload


@pytest.mark.asyncio
async def test_export_event_skips_when_no_url(
    db_session: AsyncSession, monkeypatch
) -> None:
    """export_event with no url in config logs warning and returns without error."""
    from testlyn_api.services.audit_siem import export_event

    org = Organization(name="NoUrlOrg", slug=f"nourl-{uuid.uuid4().hex[:6]}")
    db_session.add(org)
    await db_session.flush()

    sink = AuditSiemSink(
        org_id=org.id,
        kind="generic_https",
        config={},  # no url
        active=True,
    )
    db_session.add(sink)
    await db_session.flush()

    event = AuditLog(
        org_id=org.id,
        action="org.created",
        resource_type="organization",
    )
    db_session.add(event)
    await db_session.flush()

    # Should not raise even without a URL
    await export_event(sink, event)


@pytest.mark.asyncio
async def test_backfill_recent_returns_count(
    db_session: AsyncSession, monkeypatch
) -> None:
    """backfill_recent calls export_event for each row and returns count."""
    from testlyn_api.services.audit_siem import backfill_recent

    exported: list[str] = []

    async def _mock_export(sink, event):  # type: ignore[no-untyped-def]
        exported.append(str(event.id))

    monkeypatch.setattr("testlyn_api.services.audit_siem.export_event", _mock_export)

    org = Organization(name="BackfillOrg", slug=f"backfill-{uuid.uuid4().hex[:6]}")
    db_session.add(org)
    await db_session.flush()

    sink = AuditSiemSink(
        org_id=org.id,
        kind="generic_https",
        config={"url": "https://example.com"},
        active=True,
    )
    db_session.add(sink)

    for i in range(3):
        db_session.add(AuditLog(
            org_id=org.id,
            action=f"event.{i}",
            resource_type="test",
        ))
    await db_session.commit()

    count = await backfill_recent(sink, "2000-01-01T00:00:00", db_session)
    assert count == 3
    assert len(exported) == 3
