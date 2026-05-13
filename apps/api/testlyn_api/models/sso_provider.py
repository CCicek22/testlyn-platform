from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from testlyn_api.core.db import Base

SSO_KIND = Enum("saml", "oidc", name="sso_provider_kind")


class SsoProvider(Base):
    __tablename__ = "sso_providers"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    kind: Mapped[str] = mapped_column(SSO_KIND, nullable=False)
    # For SAML: raw metadata XML.  For OIDC: discovery URL.
    metadata_xml_or_discovery_url: Mapped[str] = mapped_column(Text(), nullable=False)
    # Maps IdP claim names → Testlyn field names, e.g. {"email": "email", "name": "name"}
    attribute_mappings: Mapped[dict[str, Any]] = mapped_column(
        JSONB(astext_type=Text()), nullable=False, default=dict
    )
    active: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
