"""Add Phase 3 product tables: synthetic_data_jobs, contract_scans, security_scans, insights_snapshots

Revision ID: 0009
Revises: 0008
Create Date: 2026-05-13 00:00:00.000000

Chains on 0008 (webhooks). W3A migrations (0006 RBAC, 0007 SIEM) will rebase
into the chain when stream W3A merges.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # synthetic_data_jobs
    # Tracks each call to POST /v1/products/synthetic-data/generate.
    # ------------------------------------------------------------------
    op.create_table(
        "synthetic_data_jobs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("dsn_secret_id", sa.Text(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("queued", "running", "completed", "failed", name="synth_job_status"),
            nullable=False,
            server_default="queued",
        ),
        sa.Column("output_uri", sa.Text(), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_synthetic_data_jobs_org_id", "synthetic_data_jobs", ["org_id"])

    # ------------------------------------------------------------------
    # contract_scans
    # Tracks each call to POST /v1/products/api-contract/scan.
    # ------------------------------------------------------------------
    op.create_table(
        "contract_scans",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("openapi_url", sa.Text(), nullable=False),
        sa.Column("target_url", sa.Text(), nullable=False),
        sa.Column("drift_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "last_run_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_contract_scans_org_id", "contract_scans", ["org_id"])

    # ------------------------------------------------------------------
    # security_scans
    # Tracks each call to POST /v1/products/security/scan.
    # ------------------------------------------------------------------
    op.create_table(
        "security_scans",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("target_url", sa.Text(), nullable=False),
        sa.Column(
            "kind",
            sa.Enum("baseline", "full", name="security_scan_kind"),
            nullable=False,
            server_default="baseline",
        ),
        sa.Column("findings_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_security_scans_org_id", "security_scans", ["org_id"])

    # ------------------------------------------------------------------
    # insights_snapshots
    # Denormalized cross-product KPI snapshots per org.
    # Refreshed via Cloud Scheduler cron → POST /v1/internal/orgs/:id/insights/refresh
    # ------------------------------------------------------------------
    op.create_table(
        "insights_snapshots",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "snapshot_time",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("p95_latency_ms", sa.Numeric(10, 2), nullable=True),
        sa.Column("a11y_score", sa.Numeric(5, 2), nullable=True),
        sa.Column("open_critical_findings", sa.Integer(), nullable=True),
        sa.Column("contract_drift_count", sa.Integer(), nullable=True),
        sa.Column("synthetic_data_freshness_h", sa.Numeric(8, 2), nullable=True),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_insights_snapshots_org_id", "insights_snapshots", ["org_id"])
    op.create_index(
        "ix_insights_snapshots_org_time",
        "insights_snapshots",
        ["org_id", "snapshot_time"],
    )


def downgrade() -> None:
    op.drop_index("ix_insights_snapshots_org_time", table_name="insights_snapshots")
    op.drop_index("ix_insights_snapshots_org_id", table_name="insights_snapshots")
    op.drop_table("insights_snapshots")

    op.drop_index("ix_security_scans_org_id", table_name="security_scans")
    op.drop_table("security_scans")
    op.execute("DROP TYPE IF EXISTS security_scan_kind")

    op.drop_index("ix_contract_scans_org_id", table_name="contract_scans")
    op.drop_table("contract_scans")

    op.drop_index("ix_synthetic_data_jobs_org_id", table_name="synthetic_data_jobs")
    op.drop_table("synthetic_data_jobs")
    op.execute("DROP TYPE IF EXISTS synth_job_status")
