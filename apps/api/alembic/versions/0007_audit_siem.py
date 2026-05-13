"""Audit SIEM sinks table

Revision ID: 0007
Revises: 0006
Create Date: 2026-05-13 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    conn = op.get_bind()
    dialect = conn.dialect.name

    uuid_col = postgresql.UUID(as_uuid=True) if dialect == "postgresql" else sa.Text()
    # JSONB on Postgres, JSON on SQLite
    json_col = postgresql.JSONB(astext_type=sa.Text()) if dialect == "postgresql" else sa.JSON()

    op.create_table(
        "audit_log_siem_sinks",
        sa.Column(
            "id",
            uuid_col,
            server_default=sa.text("gen_random_uuid()") if dialect == "postgresql" else sa.text("(lower(hex(randomblob(16))))"),
            nullable=False,
        ),
        sa.Column("org_id", uuid_col, nullable=False),
        sa.Column("kind", sa.String(64), nullable=False),
        sa.Column("config", json_col, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()") if dialect == "postgresql" else sa.text("(datetime('now'))"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()") if dialect == "postgresql" else sa.text("(datetime('now'))"),
            nullable=False,
        ),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true") if dialect == "postgresql" else sa.text("1")),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["org_id"],
            ["organizations.id"],
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "kind IN ('splunk_hec', 'datadog_logs', 'generic_https')",
            name="ck_audit_siem_sinks_kind",
        ),
    )
    op.create_index("ix_audit_siem_sinks_org_id", "audit_log_siem_sinks", ["org_id"])
    op.create_index(
        "ix_audit_siem_sinks_org_active",
        "audit_log_siem_sinks",
        ["org_id", "active"],
    )


def downgrade() -> None:
    op.drop_index("ix_audit_siem_sinks_org_active", table_name="audit_log_siem_sinks")
    op.drop_index("ix_audit_siem_sinks_org_id", table_name="audit_log_siem_sinks")
    op.drop_table("audit_log_siem_sinks")
