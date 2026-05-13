from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Integer, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from testlyn_api.core.db import Base


class Scenario(Base):
    __tablename__ = "scenarios"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    slug: Mapped[str] = mapped_column(Text, unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    # product discriminator — matches test.product column (hard rule §2 schema discipline)
    product: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    # JSON payload: { script, k6Config, sampleTarget, tags, ... }
    payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # price_cents = 0 means free; >0 stubs paid (Stripe Connect not wired yet)
    price_cents: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    author: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
