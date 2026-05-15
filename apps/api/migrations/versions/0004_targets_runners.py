"""Add targets, runners_registry, tests.target_id

Revision ID: 0004
Revises: 0003
Create Date: 2026-05-12 00:00:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Seed data for runners_registry
_RUNNERS_SEED = [
    {
        "name": "k6",
        "product": "load",
        "image_uri": "grafana/k6:1.3.0",
        "cpu_cores": 1,
        "memory_mb": 512,
        "capabilities": '{"streaming": true, "thresholds": true}',
    },
    {
        "name": "playwright",
        "product": "functional",
        "image_uri": "mcr.microsoft.com/playwright:v1.50.0-noble",
        "cpu_cores": 2,
        "memory_mb": 1024,
        "capabilities": '{"browsers": ["chromium", "firefox", "webkit"]}',
    },
    {
        "name": "axe-core",
        "product": "a11y",
        "image_uri": "ghcr.io/testlyn/engine-a11y:dev",
        "cpu_cores": 1,
        "memory_mb": 512,
        "capabilities": '{"wcag_levels": ["A", "AA", "AAA"]}',
    },
]


def upgrade() -> None:
    # --- targets ---
    op.create_table(
        "targets",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column(
            "kind",
            sa.Enum("web", "mobile", "api", name="targetkind"),
            nullable=False,
        ),
        sa.Column("base_url", sa.Text(), nullable=True),
        sa.Column("auth_config", postgresql.JSONB(), nullable=True),
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
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("org_id", "name", name="uq_targets_org_name"),
    )
    op.create_index("ix_targets_org_id", "targets", ["org_id"])

    # --- runners_registry ---
    op.create_table(
        "runners_registry",
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("product", sa.Text(), nullable=False),
        sa.Column("image_uri", sa.Text(), nullable=True),
        sa.Column("cpu_cores", sa.Integer(), nullable=True),
        sa.Column("memory_mb", sa.Integer(), nullable=True),
        sa.Column("capabilities", postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("name"),
    )

    # Seed runners_registry (idempotent)
    conn = op.get_bind()
    for row in _RUNNERS_SEED:
        conn.execute(
            sa.text(
                """
                INSERT INTO runners_registry (name, product, image_uri, cpu_cores, memory_mb, capabilities)
                VALUES (:name, :product, :image_uri, :cpu_cores, :memory_mb, CAST(:capabilities AS jsonb))
                ON CONFLICT (name) DO NOTHING
                """
            ),
            row,
        )

    # --- tests.target_id (nullable FK, back-compat) ---
    op.add_column(
        "tests",
        sa.Column("target_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_tests_target_id",
        "tests",
        "targets",
        ["target_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_tests_target_id", "tests", type_="foreignkey")
    op.drop_column("tests", "target_id")
    op.drop_table("runners_registry")
    op.drop_index("ix_targets_org_id", table_name="targets")
    op.drop_table("targets")
    op.execute("DROP TYPE IF EXISTS targetkind")
