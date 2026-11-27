"""Knowledge store: documents and chunks with pgvector embeddings

Revision ID: 0015
Revises: 0014
Create Date: 2026-11-27 00:00:00.000000

knowledge_documents holds one row per ingested text (deduplicated per org by
content_sha256). knowledge_chunks holds its chunks with a 256-dimension
embedding (HNSW, cosine) and a generated tsvector for full-text search.

The 256 below must match KNOWLEDGE_EMBEDDING_DIM in
testlyn_api/models/knowledge.py.

The vector extension is created IF NOT EXISTS and is left in place on
downgrade, since other objects may depend on it.

CREATE EXTENSION vector needs a superuser: pgvector is not a trusted
extension. A non-superuser migration role works only if an administrator has
already created the extension in the target database; IF NOT EXISTS then makes
this step a no-op.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "knowledge_documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("source", sa.String(40), nullable=False),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("chunk_count", sa.Integer(), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
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
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        # NULLS NOT DISTINCT (Postgres 15+): org-wide rows (project NULL) are unique too.
        sa.UniqueConstraint(
            "org_id",
            "project_id",
            "content_sha256",
            name="uq_knowledge_documents_org_project_sha",
            postgresql_nulls_not_distinct=True,
        ),
    )
    op.create_index("ix_knowledge_documents_org_id", "knowledge_documents", ["org_id"])
    op.create_index(
        "ix_knowledge_documents_project_id", "knowledge_documents", ["project_id"]
    )

    op.create_table(
        "knowledge_chunks",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("heading", sa.String(300), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("char_start", sa.Integer(), nullable=False),
        sa.Column("char_end", sa.Integer(), nullable=False),
        sa.Column("token_estimate", sa.Integer(), nullable=False),
        sa.Column("embedding", Vector(256), nullable=False),  # KNOWLEDGE_EMBEDDING_DIM
        sa.Column("embedding_model", sa.String(100), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["document_id"], ["knowledge_documents.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "document_id", "ordinal", name="uq_knowledge_chunks_document_ordinal"
        ),
    )
    op.create_index("ix_knowledge_chunks_org_id", "knowledge_chunks", ["org_id"])
    op.create_index(
        "ix_knowledge_chunks_document_id", "knowledge_chunks", ["document_id"]
    )

    # HNSW index for cosine nearest-neighbour search (pgvector).
    op.execute(
        "CREATE INDEX ix_knowledge_chunks_embedding_hnsw ON knowledge_chunks "
        "USING hnsw (embedding vector_cosine_ops)"
    )

    # Full-text search column. Generated and maintained by Postgres; not mapped
    # in the ORM in this release (search lands in a later change).
    op.execute(
        "ALTER TABLE knowledge_chunks ADD COLUMN text_tsv tsvector GENERATED ALWAYS AS "
        "(to_tsvector('english'::regconfig, coalesce(heading, '') || ' ' || text)) STORED"
    )
    op.execute(
        "CREATE INDEX ix_knowledge_chunks_text_tsv ON knowledge_chunks USING gin (text_tsv)"
    )


def downgrade() -> None:
    op.drop_table("knowledge_chunks")
    op.drop_table("knowledge_documents")
