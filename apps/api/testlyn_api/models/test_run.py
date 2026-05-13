from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from testlyn_api.core.db import Base


class TestRun(Base):
    __tablename__ = "test_runs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    test_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tests.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # discriminator — mirrors Test.product; never remove
    product: Mapped[str] = mapped_column(String(64), nullable=False, default="load", index=True)
    state: Mapped[str] = mapped_column(
        String(32), nullable=False, default="queued", index=True
    )  # queued | running | completed | failed | cancelled
    runner_id: Mapped[str | None] = mapped_column(String(512), nullable=True)
    region: Mapped[str] = mapped_column(String(64), nullable=False, default="us-central1")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    summary_uri: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    error_reason: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    triggered_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
