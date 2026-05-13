"""RBAC: extend org_members.role + project_role_overrides

Revision ID: 0006
Revises: 0005
Create Date: 2026-05-13 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Valid roles (kept as text — Postgres VARCHAR + CHECK, no native ENUM to avoid
# the complexity of ALTER TYPE across connections).
_ROLES = ("owner", "admin", "member", "viewer")


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. Ensure org_members.role accepts 'viewer'.
    #    It's already a VARCHAR(32), so this is a CHECK-constraint guard only.
    #    We drop+recreate the constraint if it already exists (idempotent).
    # ------------------------------------------------------------------
    conn = op.get_bind()
    dialect = conn.dialect.name

    if dialect == "postgresql":
        # Add 'viewer' to the allowed set via a CHECK constraint.
        # The column is already VARCHAR(32) with no constraint, so just add one.
        # Use IF NOT EXISTS-style: attempt to drop first (no-op if absent).
        op.execute(
            sa.text(
                "ALTER TABLE org_members DROP CONSTRAINT IF EXISTS ck_org_members_role"
            )
        )
        op.execute(
            sa.text(
                "ALTER TABLE org_members ADD CONSTRAINT ck_org_members_role "
                "CHECK (role IN ('owner', 'admin', 'member', 'viewer'))"
            )
        )
    # SQLite: no ALTER COLUMN; the VARCHAR(32) default allows any value.
    # The CHECK constraint is enforced at application layer via permissions.py.

    # ------------------------------------------------------------------
    # 2. project_role_overrides — per-project role for a user
    # ------------------------------------------------------------------
    op.create_table(
        "project_role_overrides",
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True) if dialect == "postgresql" else sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True) if dialect == "postgresql" else sa.Text(),
            nullable=False,
        ),
        sa.Column("role", sa.String(32), nullable=False),
        sa.PrimaryKeyConstraint("project_id", "user_id"),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "role IN ('owner', 'admin', 'member', 'viewer')",
            name="ck_project_role_overrides_role",
        ),
    )
    op.create_index(
        "ix_project_role_overrides_user_id",
        "project_role_overrides",
        ["user_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_project_role_overrides_user_id", table_name="project_role_overrides")
    op.drop_table("project_role_overrides")

    conn = op.get_bind()
    if conn.dialect.name == "postgresql":
        op.execute(
            sa.text(
                "ALTER TABLE org_members DROP CONSTRAINT IF EXISTS ck_org_members_role"
            )
        )
