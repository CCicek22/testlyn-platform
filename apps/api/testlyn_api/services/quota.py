from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import structlog
from fastapi import HTTPException, status
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from testlyn_api.models.usage import UsageRecord

if TYPE_CHECKING:
    from testlyn_api.models.org import Organization
    from testlyn_api.models.test_run import TestRun

log = structlog.get_logger(__name__)


@dataclass(frozen=True)
class TierLimits:
    tests_per_month: int | None  # None = unlimited
    max_vus: int | None
    max_duration_seconds: int | None


# Tier caps per pricing spec
_TIER_LIMITS: dict[str, TierLimits] = {
    "free": TierLimits(tests_per_month=5, max_vus=50, max_duration_seconds=300),
    "hobby": TierLimits(tests_per_month=50, max_vus=200, max_duration_seconds=1800),
    "pro": TierLimits(tests_per_month=500, max_vus=1000, max_duration_seconds=3600),
    "business": TierLimits(tests_per_month=5000, max_vus=5000, max_duration_seconds=14400),
    "enterprise": TierLimits(tests_per_month=None, max_vus=None, max_duration_seconds=None),
}


def _current_month() -> str:
    return datetime.now(UTC).strftime("%Y-%m")


class QuotaService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def _get_or_create_usage(self, org_id: object, month: str) -> UsageRecord:
        # Advisory lock prevents TOCTOU race when two runs start simultaneously
        # for the same org. The lock key MUST be stable across processes —
        # Python's hash() is per-process randomized (PYTHONHASHSEED), so it would
        # not serialize across Cloud Run instances. Use Postgres-native
        # hashtextextended() (deterministic) computed inside the DB; the org_id
        # is passed as a bind parameter, never interpolated into SQL.
        # Raw SQL here is an explicit exception to §6 (no raw SQL in app code);
        # pg_advisory_xact_lock has no SQLAlchemy ORM equivalent.
        # Skipped on non-Postgres backends (e.g. SQLite in tests).
        dialect = self._session.bind.dialect.name if self._session.bind else ""  # type: ignore[union-attr]
        if dialect == "postgresql":
            await self._session.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:k, 0))").bindparams(
                    k=str(org_id)
                )
            )

        result = await self._session.execute(
            select(UsageRecord).where(
                UsageRecord.org_id == org_id,  # type: ignore[arg-type]
                UsageRecord.month == month,
            )
        )
        record = result.scalar_one_or_none()
        if record is None:
            record = UsageRecord(org_id=org_id, month=month, runs_count=0, vu_seconds_total=0)  # type: ignore[arg-type]
            self._session.add(record)
            await self._session.flush()
        return record

    async def check_can_run(
        self,
        org: Organization,
        vus: int,
        duration_seconds: int,
    ) -> None:
        """Raise HTTP 402 with structured body if quota is exceeded."""
        plan = (org.plan or "free").lower()
        limits = _TIER_LIMITS.get(plan, _TIER_LIMITS["free"])

        month = _current_month()
        usage = await self._get_or_create_usage(org.id, month)

        errors: list[str] = []

        if limits.max_vus is not None and vus > limits.max_vus:
            errors.append(f"VU count {vus} exceeds plan limit of {limits.max_vus} VUs")

        if (
            limits.max_duration_seconds is not None
            and duration_seconds > limits.max_duration_seconds
        ):
            errors.append(
                f"Duration {duration_seconds}s exceeds plan limit of {limits.max_duration_seconds}s"
            )

        if limits.tests_per_month is not None and usage.runs_count >= limits.tests_per_month:
            errors.append(
                f"Monthly run limit of {limits.tests_per_month} reached ({usage.runs_count} used)"
            )

        if errors:
            log.warning(
                "quota.exceeded",
                org_id=str(org.id),
                plan=plan,
                vus=vus,
                duration_seconds=duration_seconds,
                runs_count=usage.runs_count,
            )
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail={
                    "code": "QUOTA_EXCEEDED",
                    "detail": "; ".join(errors),
                    "limits": {
                        "tests_per_month": limits.tests_per_month,
                        "max_vus": limits.max_vus,
                        "max_duration_seconds": limits.max_duration_seconds,
                    },
                    "usage": {
                        "runs_count": usage.runs_count,
                        "month": month,
                    },
                },
            )

    async def record_usage(self, org: Organization, test_run: TestRun) -> None:
        """Increment usage_records for the org's current month."""
        month = _current_month()
        record = await self._get_or_create_usage(org.id, month)
        record.runs_count += 1
        # vu_seconds_total is updated post-run when we have real data;
        # increment by 0 here to keep the record current.
        await self._session.flush()
        log.info(
            "quota.usage_recorded",
            org_id=str(org.id),
            run_id=str(test_run.id),
            runs_count=record.runs_count,
            month=month,
        )
