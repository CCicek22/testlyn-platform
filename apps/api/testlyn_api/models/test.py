from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from testlyn_api.core.db import Base


class Test(Base):
    __tablename__ = "tests"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # discriminator — never remove, Phase 2+ depends on this
    product: Mapped[str] = mapped_column(String(64), nullable=False, default="load", index=True)
    script_uri: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    script_inline: Mapped[str | None] = mapped_column(Text, nullable=True)
    # JSONB config: {vus, duration_seconds, thresholds}
    config: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)  # type: ignore[type-arg]
    created_by: Mapped[uuid.UUID | None] = mapped_column(
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
