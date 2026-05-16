"""Add Phase 4 product tables: mobile_runs, visual_baselines, rum_sites, rum_pageviews,
tdm_subsetting_jobs, qa_maturity_assessments, eng_analytics_connections, cicd_runs

Revision ID: 0010
Revises: 0009
Create Date: 2026-05-13 00:00:00.000000

Chains on 0009 (phase3_products). Scaffold-grade tables for W4A Phase 4 products.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # mobile_runs
    # Tracks mobile performance test runs.
    # ------------------------------------------------------------------
    op.create_table(
        "mobile_runs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("target_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "queued", "running", "completed", "failed",
                name="mobile_run_status",
            ),
            nullable=False,
            server_default="queued",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_mobile_runs_org_id", "mobile_runs", ["org_id"])

    # ------------------------------------------------------------------
    # visual_baselines
    # Stores baseline screenshots for visual regression comparisons.
    # ------------------------------------------------------------------
    op.create_table(
        "visual_baselines",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("target_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("screenshot_uri", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_visual_baselines_org_id", "visual_baselines", ["org_id"])

    # ------------------------------------------------------------------
    # rum_sites
    # Registered sites for Real User Monitoring.
    # ------------------------------------------------------------------
    op.create_table(
        "rum_sites",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("target_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("snippet_id", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_rum_sites_org_id", "rum_sites", ["org_id"])

    # ------------------------------------------------------------------
    # rum_pageviews
    # Individual RUM pageview records with Core Web Vitals.
    # Partitioned by ts (range partitioning on Postgres 16).
    # ------------------------------------------------------------------
    op.create_table(
        "rum_pageviews",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("site_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("lcp_ms", sa.Numeric(10, 2), nullable=True),
        sa.Column("fid_ms", sa.Numeric(10, 2), nullable=True),
        sa.Column("cls", sa.Numeric(6, 4), nullable=True),
        sa.Column(
            "ts",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["site_id"], ["rum_sites.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", "ts"),
        postgresql_partition_by="RANGE (ts)",
    )
    # DEFAULT partition catches all rows until time-range partitions are
    # provisioned out-of-band (cron + pg_partman or similar). Without this,
    # the first INSERT after create_table fails with "no partition of
    # relation rum_pageviews found for row".
    op.execute(
        sa.text("CREATE TABLE rum_pageviews_default PARTITION OF rum_pageviews DEFAULT")
    )
    op.create_index("ix_rum_pageviews_site_id_ts", "rum_pageviews", ["site_id", "ts"])

    # ------------------------------------------------------------------
    # tdm_subsetting_jobs
    # Tracks Test Data Management subsetting runs.
    # ------------------------------------------------------------------
    op.create_table(
        "tdm_subsetting_jobs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "queued", "running", "completed", "failed",
                name="tdm_job_status",
            ),
            nullable=False,
            server_default="queued",
        ),
        sa.Column("output_uri", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_tdm_subsetting_jobs_org_id", "tdm_subsetting_jobs", ["org_id"])

    # ------------------------------------------------------------------
    # qa_maturity_assessments
    # Stores questionnaire answers + LLM-generated maturity roadmaps.
    # ------------------------------------------------------------------
    op.create_table(
        "qa_maturity_assessments",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("answers", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("score", sa.Numeric(5, 2), nullable=True),
        sa.Column("generated_roadmap_md", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_qa_maturity_assessments_org_id", "qa_maturity_assessments", ["org_id"])

    # ------------------------------------------------------------------
    # eng_analytics_connections
    # Source code / issue tracker connections for engineering analytics.
    # ------------------------------------------------------------------
    op.create_table(
        "eng_analytics_connections",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("config", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_eng_analytics_connections_org_id", "eng_analytics_connections", ["org_id"])

    # ------------------------------------------------------------------
    # cicd_runs
    # Ingested CI/CD pipeline run metrics.
    # ------------------------------------------------------------------
    op.create_table(
        "cicd_runs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("pipeline_id", sa.Text(), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("flaky_test_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cost_estimate_usd", sa.Numeric(10, 4), nullable=False, server_default="0"),
        sa.Column(
            "ts",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_cicd_runs_org_id_ts", "cicd_runs", ["org_id", "ts"])


def downgrade() -> None:
    op.drop_index("ix_cicd_runs_org_id_ts", table_name="cicd_runs")
    op.drop_table("cicd_runs")

    op.drop_index("ix_eng_analytics_connections_org_id", table_name="eng_analytics_connections")
    op.drop_table("eng_analytics_connections")

    op.drop_index("ix_qa_maturity_assessments_org_id", table_name="qa_maturity_assessments")
    op.drop_table("qa_maturity_assessments")

    op.drop_index("ix_tdm_subsetting_jobs_org_id", table_name="tdm_subsetting_jobs")
    op.drop_table("tdm_subsetting_jobs")
    op.execute("DROP TYPE IF EXISTS tdm_job_status")

    op.drop_index("ix_rum_pageviews_site_id_ts", table_name="rum_pageviews")
    # Drop DEFAULT partition first (DROP TABLE on partitioned parent
    # cascades, but be explicit for symmetry with upgrade()).
    op.execute(sa.text("DROP TABLE IF EXISTS rum_pageviews_default"))
    op.drop_table("rum_pageviews")

    op.drop_index("ix_rum_sites_org_id", table_name="rum_sites")
    op.drop_table("rum_sites")

    op.drop_index("ix_visual_baselines_org_id", table_name="visual_baselines")
    op.drop_table("visual_baselines")

    op.drop_index("ix_mobile_runs_org_id", table_name="mobile_runs")
    op.drop_table("mobile_runs")
    op.execute("DROP TYPE IF EXISTS mobile_run_status")
