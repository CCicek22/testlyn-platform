from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from testlyn_api.models.org import Organization
from testlyn_api.models.project import Project
from testlyn_api.models.test import Test as TestModel
from testlyn_api.models.test_run import TestRun
from testlyn_api.models.usage import UsageRecord
from testlyn_api.services.quota import QuotaService


def _make_org(plan: str = "free") -> Organization:
    return Organization(
        name=f"Org-{plan}",
        slug=f"org-{plan}-{uuid.uuid4().hex[:6]}",
        plan=plan,
    )


async def _make_run(session: AsyncSession, org: Organization) -> TestRun:
    """Create a full org→project→test→run chain respecting FK constraints."""
    proj = Project(org_id=org.id, name="P", slug=f"p-{uuid.uuid4().hex[:6]}")
    session.add(proj)
    await session.flush()

    test = TestModel(project_id=proj.id, name="T", script_inline="export default function(){}")
    session.add(test)
    await session.flush()

    run = TestRun(
        test_id=test.id,
        product="load",
        state="queued",
        region="us-central1",
    )
    return run


@pytest.mark.asyncio
async def test_free_tier_blocks_at_run_limit(db_session: AsyncSession) -> None:
    """Free plan at 5 runs/month → 6th attempt raises 402."""
    org = _make_org("free")
    db_session.add(org)
    await db_session.flush()

    from datetime import UTC, datetime

    month = datetime.now(UTC).strftime("%Y-%m")
    record = UsageRecord(org_id=org.id, month=month, runs_count=5, vu_seconds_total=0)
    db_session.add(record)
    await db_session.flush()

    quota = QuotaService(db_session)
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        await quota.check_can_run(org, vus=1, duration_seconds=60)

    assert exc_info.value.status_code == 402
    detail = exc_info.value.detail
    assert detail["code"] == "QUOTA_EXCEEDED"
    assert detail["usage"]["runs_count"] == 5
    assert detail["limits"]["tests_per_month"] == 5


@pytest.mark.asyncio
async def test_free_tier_blocks_vu_over_limit(db_session: AsyncSession) -> None:
    """Free plan VU limit is 50 — requesting 51 raises 402."""
    org = _make_org("free")
    db_session.add(org)
    await db_session.flush()

    quota = QuotaService(db_session)
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        await quota.check_can_run(org, vus=51, duration_seconds=60)

    assert exc_info.value.status_code == 402
    detail = exc_info.value.detail
    assert "51" in detail["detail"]


@pytest.mark.asyncio
async def test_free_tier_blocks_duration_over_limit(db_session: AsyncSession) -> None:
    """Free plan max duration is 300s — 301s raises 402."""
    org = _make_org("free")
    db_session.add(org)
    await db_session.flush()

    quota = QuotaService(db_session)
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        await quota.check_can_run(org, vus=1, duration_seconds=301)

    assert exc_info.value.status_code == 402


@pytest.mark.asyncio
async def test_pro_tier_allows_past_free_limits(db_session: AsyncSession) -> None:
    """Pro plan allows up to 1000 VUs and 3600s — well above free."""
    org = _make_org("pro")
    db_session.add(org)
    await db_session.flush()

    quota = QuotaService(db_session)
    # Should not raise
    await quota.check_can_run(org, vus=500, duration_seconds=1800)


@pytest.mark.asyncio
async def test_pro_tier_blocks_at_its_own_limits(db_session: AsyncSession) -> None:
    """Pro plan caps at 1000 VUs — 1001 raises 402."""
    org = _make_org("pro")
    db_session.add(org)
    await db_session.flush()

    quota = QuotaService(db_session)
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        await quota.check_can_run(org, vus=1001, duration_seconds=60)

    assert exc_info.value.status_code == 402


@pytest.mark.asyncio
async def test_enterprise_allows_unlimited(db_session: AsyncSession) -> None:
    """Enterprise plan has no limits — very high values pass."""
    org = _make_org("enterprise")
    db_session.add(org)
    await db_session.flush()

    quota = QuotaService(db_session)
    await quota.check_can_run(org, vus=99999, duration_seconds=999999)


@pytest.mark.asyncio
async def test_record_usage_round_trips(db_session: AsyncSession) -> None:
    """record_usage creates a usage row and increments runs_count."""
    from sqlalchemy import select

    org = _make_org("free")
    db_session.add(org)
    await db_session.flush()

    run = await _make_run(db_session, org)
    db_session.add(run)
    await db_session.flush()

    quota = QuotaService(db_session)
    await quota.record_usage(org, run)
    await db_session.flush()

    from datetime import UTC, datetime

    month = datetime.now(UTC).strftime("%Y-%m")
    result = await db_session.execute(
        select(UsageRecord).where(
            UsageRecord.org_id == org.id,
            UsageRecord.month == month,
        )
    )
    record = result.scalar_one()
    assert record.runs_count == 1


@pytest.mark.asyncio
async def test_advisory_lock_key_is_stable_across_calls() -> None:
    """Advisory lock SQL must be deterministic (not per-process hash())."""
    from sqlalchemy import select

    captured: list[str] = []

    class _FakeDialect:
        name = "postgresql"

    class _FakeBind:
        dialect = _FakeDialect()

    class _FakeSession:
        bind = _FakeBind()

        async def execute(self, stmt):
            text_clause = getattr(stmt, "text", None)
            if text_clause is not None and "pg_advisory_xact_lock" in text_clause:
                # Compile with literal binds so a regression to a random Python
                # hash() value (interpolated into the SQL) would surface here.
                captured.append(str(stmt.compile(compile_kwargs={"literal_binds": True})))

            class _Result:
                def scalar_one_or_none(self_inner):
                    return UsageRecord(org_id=org_id, month="2026-01", runs_count=0, vu_seconds_total=0)

            return _Result()

        def add(self, _obj):  # pragma: no cover - not exercised when record exists
            pass

        async def flush(self):  # pragma: no cover
            pass

    org_id = uuid.UUID("11111111-1111-1111-1111-111111111111")
    svc = QuotaService(_FakeSession())  # type: ignore[arg-type]

    # Avoid the unused-import lint while keeping select available for parity.
    _ = select

    await svc._get_or_create_usage(org_id, "2026-01")
    await svc._get_or_create_usage(org_id, "2026-01")

    assert len(captured) == 2
    assert captured[0] == captured[1]
    # Deterministic + parameterized: the literal org_id string, not a hash int.
    assert "hashtextextended" in captured[0]
    assert str(org_id) in captured[0]


@pytest.mark.asyncio
async def test_record_usage_increments(db_session: AsyncSession) -> None:
    """Calling record_usage twice yields runs_count == 2."""
    from datetime import UTC, datetime

    from sqlalchemy import select

    org = _make_org("hobby")
    db_session.add(org)
    await db_session.flush()

    quota = QuotaService(db_session)

    run1 = await _make_run(db_session, org)
    db_session.add(run1)
    await db_session.flush()
    await quota.record_usage(org, run1)

    run2 = await _make_run(db_session, org)
    db_session.add(run2)
    await db_session.flush()
    await quota.record_usage(org, run2)

    await db_session.flush()

    month = datetime.now(UTC).strftime("%Y-%m")
    result = await db_session.execute(
        select(UsageRecord).where(
            UsageRecord.org_id == org.id,
            UsageRecord.month == month,
        )
    )
    record = result.scalar_one()
    assert record.runs_count == 2


@pytest.mark.asyncio
async def test_release_usage_reverses_recorded_run(db_session: AsyncSession) -> None:
    """release_usage decrements a previously recorded run back to 0."""
    from datetime import UTC, datetime

    from sqlalchemy import select

    org = _make_org("free")
    db_session.add(org)
    await db_session.flush()

    run = await _make_run(db_session, org)
    db_session.add(run)
    await db_session.flush()

    quota = QuotaService(db_session)
    await quota.record_usage(org, run)
    await quota.release_usage(org, run)
    await db_session.flush()

    month = datetime.now(UTC).strftime("%Y-%m")
    record = (
        await db_session.execute(
            select(UsageRecord).where(
                UsageRecord.org_id == org.id, UsageRecord.month == month
            )
        )
    ).scalar_one()
    assert record.runs_count == 0


@pytest.mark.asyncio
async def test_release_usage_idempotent_floors_at_zero(db_session: AsyncSession) -> None:
    """Calling release_usage more times than record_usage never goes negative."""
    from datetime import UTC, datetime

    from sqlalchemy import select

    org = _make_org("free")
    db_session.add(org)
    await db_session.flush()

    run = await _make_run(db_session, org)
    db_session.add(run)
    await db_session.flush()

    quota = QuotaService(db_session)
    await quota.record_usage(org, run)
    await quota.release_usage(org, run)
    await quota.release_usage(org, run)  # second release is a no-op
    await db_session.flush()

    month = datetime.now(UTC).strftime("%Y-%m")
    record = (
        await db_session.execute(
            select(UsageRecord).where(
                UsageRecord.org_id == org.id, UsageRecord.month == month
            )
        )
    ).scalar_one()
    assert record.runs_count == 0
