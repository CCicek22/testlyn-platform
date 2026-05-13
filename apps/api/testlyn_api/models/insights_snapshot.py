from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, Numeric, func
from sqlalchemy.orm import Mapped, mapped_column

from testlyn_api.core.db import Base


class InsightsSnapshot(Base):
    """
    Denormalized cross-product KPI snapshot per org.
    Refreshed on a Cloud Scheduler cron (e.g. hourly).
    """

    __tablename__ = "insights_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    snapshot_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    # Load product KPI
    p95_latency_ms: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    # A11y product KPI
    a11y_score: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    # Security product KPI
    open_critical_findings: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # API contract product KPI
    contract_drift_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Synthetic data product KPI (hours since last generation)
    synthetic_data_freshness_h: Mapped[float | None] = mapped_column(
        Numeric(8, 2), nullable=True
    )
    # Full denormalized payload for extensibility
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
