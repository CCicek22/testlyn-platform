"""Add a11y Postgres tables (a11y_audit_recipes, a11y_violations_cache)

Revision ID: 0005
Revises: 0003
Create Date: 2026-05-12 00:00:00.000000

NOTE — BigQuery schema changes:
  The five new runs_summary columns for a11y violation counts
  (wcag_violations_count, wcag_critical, wcag_serious, wcag_moderate, wcag_minor)
  are managed in Terraform, NOT here. Adding columns to a BQ table managed by
  Terraform via the console or Alembic would cause a plan drift.

  See: infra/terraform/modules/bigquery_a11y/main.tf
  That module adds the five columns to the existing runs_summary table schema
  as a separate addition-only resource block to avoid colliding with the
  foundation bigquery module.

  This migration handles ONLY the Postgres side.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # a11y_audit_recipes
    # Stores scheduled or on-demand audit configs per target.
    # target_id is a forward FK — targets table added by W2A migration 0004.
    # FK is nullable to allow creation before W2A stream lands.
    # ------------------------------------------------------------------
    op.create_table(
        "a11y_audit_recipes",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "target_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,  # nullable — targets table may not exist yet in dev
        ),
        sa.Column("urls", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("max_depth", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("schedule_cron", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_a11y_audit_recipes_target_id",
        "a11y_audit_recipes",
        ["target_id"],
    )

    # ------------------------------------------------------------------
    # a11y_violations_cache
    # Stores LLM-generated remediation text keyed by (rule_id, html_snippet_hash).
    # Avoids repeat Vertex AI calls for identical violations.
    # ------------------------------------------------------------------
    op.create_table(
        "a11y_violations_cache",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("rule_id", sa.Text(), nullable=False),
        sa.Column("html_snippet_hash", sa.Text(), nullable=False),
        sa.Column("remediation", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "rule_id",
            "html_snippet_hash",
            name="uq_a11y_violations_cache_rule_snippet",
        ),
    )
    op.create_index(
        "ix_a11y_violations_cache_rule_id",
        "a11y_violations_cache",
        ["rule_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_a11y_violations_cache_rule_id", table_name="a11y_violations_cache")
    op.drop_table("a11y_violations_cache")

    op.drop_index("ix_a11y_audit_recipes_target_id", table_name="a11y_audit_recipes")
    op.drop_table("a11y_audit_recipes")
