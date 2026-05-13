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
