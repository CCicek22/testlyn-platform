"""Add enterprise SSO providers and org IP allowlist tables.

Revision ID: 0011
Revises: 0010
Create Date: 2026-05-13 00:00:00.000000

Chains on 0010 (phase4_products) after Wave 4 reconciliation.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # sso_providers
    # One row per SSO configuration an org has registered.
    # kind: 'saml' | 'oidc'
    # For SAML: metadata_xml_or_discovery_url holds the raw XML.
    # For OIDC: it holds the discovery URL (/.well-known/openid-configuration).
    # attribute_mappings: {"email": "...", "name": "...", "sub": "..."} etc.
    # ------------------------------------------------------------------
    op.create_table(
        "sso_providers",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "kind",
            sa.Enum("saml", "oidc", name="sso_provider_kind"),
            nullable=False,
        ),
        sa.Column("metadata_xml_or_discovery_url", sa.Text(), nullable=False),
        sa.Column(
            "attribute_mappings",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_sso_providers_org_id", "sso_providers", ["org_id"])

    # ------------------------------------------------------------------
    # org_ip_allowlist
    # CIDR entries per org. When an org has >=1 active entry, the
    # IPAllowlistMiddleware rejects requests from outside those CIDRs.
    # Off by default (no rows = no restriction).
    # ------------------------------------------------------------------
    op.create_table(
        "org_ip_allowlist",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("cidr", sa.String(50), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_org_ip_allowlist_org_id", "org_ip_allowlist", ["org_id"])


def downgrade() -> None:
    op.drop_index("ix_org_ip_allowlist_org_id", table_name="org_ip_allowlist")
    op.drop_table("org_ip_allowlist")

    op.drop_index("ix_sso_providers_org_id", table_name="sso_providers")
    op.drop_table("sso_providers")
    op.execute("DROP TYPE IF EXISTS sso_provider_kind")
