"""Add DEFAULT partition to rum_pageviews

Revision ID: 0013
Revises: 0012
Create Date: 2026-05-16 00:00:00.000000

0010 declared `rum_pageviews` as `PARTITION BY RANGE (ts)` but never created
any partitions, so any INSERT raises `no partition of relation "rum_pageviews"
found`. 0010 was patched to add the DEFAULT partition for fresh DBs; this
migration backfills the partition on databases that already ran 0010.
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text(
            "CREATE TABLE IF NOT EXISTS rum_pageviews_default "
            "PARTITION OF rum_pageviews DEFAULT"
        )
    )


def downgrade() -> None:
    op.execute(sa.text("DROP TABLE IF EXISTS rum_pageviews_default"))
