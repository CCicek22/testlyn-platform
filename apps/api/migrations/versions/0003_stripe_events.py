"""Add stripe_event_log table

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-12 00:00:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "stripe_event_log",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("stripe_event_id", sa.String(128), nullable=False),
        sa.Column("event_type", sa.String(128), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("stripe_event_id", name="uq_stripe_event_log_event_id"),
    )
    op.create_index(
        "ix_stripe_event_log_stripe_event_id",
        "stripe_event_log",
        ["stripe_event_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_stripe_event_log_stripe_event_id", table_name="stripe_event_log")
    op.drop_table("stripe_event_log")
