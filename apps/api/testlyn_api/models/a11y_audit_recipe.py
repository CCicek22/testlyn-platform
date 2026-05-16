from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from testlyn_api.core.db import Base


class AuditRecipe(Base):
    __tablename__ = "a11y_audit_recipes"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    target_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    # List of URL strings; column is JSONB in Postgres (migration 0005).
    # SQLAlchemy serialises lists/dicts on assignment — callers must pass a
    # ``list[str]`` directly, NOT ``json.dumps(...)`` (double-encoding bug).
    urls: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    max_depth: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    schedule_cron: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
