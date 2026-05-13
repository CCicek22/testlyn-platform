from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Integer, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from testlyn_api.core.db import Base


class Plugin(Base):
    __tablename__ = "plugins"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    slug: Mapped[str] = mapped_column(Text, unique=True, nullable=False, index=True)
    kind: Mapped[str] = mapped_column(Text, nullable=False)  # runner | integration | panel
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    author: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[str] = mapped_column(Text, nullable=False)
    # BLAKE3 hash of payload bundle signed by Testlyn marketplace key
    sandbox_signature: Mapped[str | None] = mapped_column(Text, nullable=True)
    # GCS URI to the plugin tarball, e.g. gs://testlyn-prod-scripts/plugins/<slug>-<version>.tgz
    payload_uri: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Install count — denormalized for marketplace sort
    install_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
