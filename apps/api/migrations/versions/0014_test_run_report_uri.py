"""Add report_uri column to test_runs

Revision ID: 0014
Revises: 0013
Create Date: 2026-05-24 00:00:00.000000

report_uri holds the PDF report GCS URI, set by the report-builder via
POST /v1/internal/runs/{id}/report-ready. It is distinct from summary_uri,
which is the k6 summary JSON written at run completion.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("test_runs", sa.Column("report_uri", sa.String(2048), nullable=True))


def downgrade() -> None:
    op.drop_column("test_runs", "report_uri")
