"""Add theme clustering tables

Creates theme and theme_document tables for document clustering.
No existing tables are modified.

Revision ID: i1j2k3l4m5n6
Revises: h1i2j3k4l5m6
Create Date: 2026-04-09
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel
from pgvector.sqlalchemy import Vector

# revision identifiers, used by Alembic.
revision: str = "i1j2k3l4m5n6"
down_revision: Union[str, Sequence[str], None] = "e1f2g3h4i5j6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- theme ---
    op.create_table(
        "theme",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("label", sqlmodel.sql.sqltypes.AutoString(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("centroid", Vector(1536), nullable=True),
        sa.Column("doc_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("color", sqlmodel.sql.sqltypes.AutoString(length=7), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_theme_user_id"), "theme", ["user_id"])
    op.create_index(
        "ix_theme_user_label",
        "theme",
        ["user_id", "label"],
        unique=True,
    )
    op.execute(
        """
        CREATE INDEX ix_theme_centroid_hnsw
        ON theme
        USING hnsw (centroid vector_cosine_ops)
        WITH (m = 16, ef_construction = 64)
        """
    )

    # --- theme_document ---
    op.create_table(
        "theme_document",
        sa.Column("theme_id", sa.Integer(), nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("is_manual", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["theme_id"], ["theme.id"]),
        sa.ForeignKeyConstraint(["document_id"], ["document.id"]),
        sa.PrimaryKeyConstraint("theme_id", "document_id"),
    )


def downgrade() -> None:
    op.drop_table("theme_document")
    op.drop_index("ix_theme_centroid_hnsw", table_name="theme")
    op.drop_index("ix_theme_user_label", table_name="theme")
    op.drop_index(op.f("ix_theme_user_id"), table_name="theme")
    op.drop_table("theme")
