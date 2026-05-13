"""Add marketplace tables: plugins, scenarios

Revision ID: 0012
Revises: 0011
Create Date: 2026-05-13 00:00:00.000000

Chains on 0011 (enterprise) after Wave 4 reconciliation.
Seed data: 2 community plugins + 4 free scenario templates for marketplace.
"""
from __future__ import annotations

import uuid

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # plugins table
    # ------------------------------------------------------------------
    op.create_table(
        "plugins",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("slug", sa.Text(), unique=True, nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("author", sa.Text(), nullable=False),
        sa.Column("version", sa.Text(), nullable=False),
        sa.Column("sandbox_signature", sa.Text(), nullable=True),
        sa.Column("payload_uri", sa.Text(), nullable=True),
        sa.Column(
            "install_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_plugins_slug", "plugins", ["slug"], unique=True)

    # ------------------------------------------------------------------
    # scenarios table
    # ------------------------------------------------------------------
    op.create_table(
        "scenarios",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("slug", sa.Text(), unique=True, nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("product", sa.Text(), nullable=False),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "price_cents",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("author", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_scenarios_slug", "scenarios", ["slug"], unique=True)
    op.create_index("ix_scenarios_product", "scenarios", ["product"])

    # ------------------------------------------------------------------
    # Seed: 2 community plugins
    # ------------------------------------------------------------------
    op.execute(
        sa.text(
            """
            INSERT INTO plugins (id, slug, kind, name, description, author, version, install_count)
            VALUES
              (:id1, 'slack-notifier', 'integration', 'Slack Notifier',
               'Posts run results and threshold breaches to a Slack channel via webhook.',
               'community', '0.1.0', 142),
              (:id2, 'p95-heatmap', 'panel', 'P95 Latency Heatmap',
               'Dashboard panel showing p95 latency distribution as a heatmap over the run timeline.',
               'community', '0.2.1', 87)
            ON CONFLICT (slug) DO NOTHING
            """
        ).bindparams(
            id1=str(uuid.uuid4()),
            id2=str(uuid.uuid4()),
        )
    )

    # ------------------------------------------------------------------
    # Seed: 4 free scenario templates
    # ------------------------------------------------------------------
    op.execute(
        sa.text(
            """
            INSERT INTO scenarios (id, slug, name, description, product, author, price_cents)
            VALUES
              (:id1, 'k6-ramp-spike', 'Ramp + Spike',
               'Three-stage k6 script: linear ramp-up to target VUs, hold, then inject a 10x spike for 30s.',
               'load', 'Testlyn', 0),
              (:id2, 'k6-soak-24h', '24-Hour Soak',
               'Steady-state load over 24h at 20% of peak capacity.',
               'load', 'Testlyn', 0),
              (:id3, 'k6-breakpoint', 'Breakpoint Finder',
               'Incrementally increases VUs until error rate exceeds 1% or p99 latency crosses 2s.',
               'load', 'Testlyn', 0),
              (:id4, 'k6-grpc-load', 'gRPC Service Load',
               'Load test for unary gRPC endpoints with per-RPC p50/p95/p99 reporting.',
               'load', 'community', 0)
            ON CONFLICT (slug) DO NOTHING
            """
        ).bindparams(
            id1=str(uuid.uuid4()),
            id2=str(uuid.uuid4()),
            id3=str(uuid.uuid4()),
            id4=str(uuid.uuid4()),
        )
    )


def downgrade() -> None:
    op.drop_table("scenarios")
    op.drop_table("plugins")
