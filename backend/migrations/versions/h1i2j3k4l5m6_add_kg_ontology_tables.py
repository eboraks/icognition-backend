"""Add KG ontology tables for schema.org-based knowledge graph

Creates 5 new tables: kg_canonical_class, kg_canonical_property, kg_node,
kg_edge, kg_node_document. No existing tables are modified.

Revision ID: h1i2j3k4l5m6
Revises: g1h2i3j4k5l6
Create Date: 2026-04-05
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel
from pgvector.sqlalchemy import Vector

# revision identifiers, used by Alembic.
revision: str = "h1i2j3k4l5m6"
down_revision: Union[str, Sequence[str], None] = "g1h2i3j4k5l6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- kg_canonical_class ---
    op.create_table(
        "kg_canonical_class",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("uri", sqlmodel.sql.sqltypes.AutoString(length=500), nullable=False),
        sa.Column("label", sqlmodel.sql.sqltypes.AutoString(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("parent_uri", sqlmodel.sql.sqltypes.AutoString(length=500), nullable=True),
        sa.Column("vector", Vector(1536), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("uri"),
    )
    op.create_index(op.f("ix_kg_canonical_class_uri"), "kg_canonical_class", ["uri"])
    op.execute(
        """
        CREATE INDEX ix_kg_canonical_class_vector_hnsw
        ON kg_canonical_class
        USING hnsw (vector vector_cosine_ops)
        WITH (m = 16, ef_construction = 64)
        """
    )

    # --- kg_canonical_property ---
    op.create_table(
        "kg_canonical_property",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("uri", sqlmodel.sql.sqltypes.AutoString(length=500), nullable=False),
        sa.Column("label", sqlmodel.sql.sqltypes.AutoString(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("parent_uri", sqlmodel.sql.sqltypes.AutoString(length=500), nullable=True),
        sa.Column("domain_class_uri", sqlmodel.sql.sqltypes.AutoString(length=500), nullable=True),
        sa.Column("range_class_uri", sqlmodel.sql.sqltypes.AutoString(length=500), nullable=True),
        sa.Column("vector", Vector(1536), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("uri"),
    )
    op.create_index(op.f("ix_kg_canonical_property_uri"), "kg_canonical_property", ["uri"])
    op.execute(
        """
        CREATE INDEX ix_kg_canonical_property_vector_hnsw
        ON kg_canonical_property
        USING hnsw (vector vector_cosine_ops)
        WITH (m = 16, ef_construction = 64)
        """
    )

    # --- kg_node ---
    op.create_table(
        "kg_node",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("uri", sqlmodel.sql.sqltypes.AutoString(length=500), nullable=True),
        sa.Column("label", sqlmodel.sql.sqltypes.AutoString(length=500), nullable=False),
        sa.Column("label_normalized", sqlmodel.sql.sqltypes.AutoString(length=500), nullable=False),
        sa.Column("canonical_class_id", sa.Integer(), nullable=True),
        sa.Column("schema_type_uri", sqlmodel.sql.sqltypes.AutoString(length=500), nullable=True),
        sa.Column("raw_type", sqlmodel.sql.sqltypes.AutoString(length=100), nullable=True),
        sa.Column("raw_description", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("properties", sa.dialects.postgresql.JSONB(), nullable=True),
        sa.Column("wikidata_id", sqlmodel.sql.sqltypes.AutoString(length=50), nullable=True),
        sa.Column("legacy_entity_id", sa.Integer(), nullable=True),
        sa.Column("user_id", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["canonical_class_id"], ["kg_canonical_class.id"]),
        sa.ForeignKeyConstraint(["legacy_entity_id"], ["entities.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_kg_node_label"), "kg_node", ["label"])
    op.create_index(op.f("ix_kg_node_label_normalized"), "kg_node", ["label_normalized"])
    op.create_index(op.f("ix_kg_node_canonical_class_id"), "kg_node", ["canonical_class_id"])
    op.create_index(op.f("ix_kg_node_wikidata_id"), "kg_node", ["wikidata_id"])
    op.create_index(op.f("ix_kg_node_user_id"), "kg_node", ["user_id"])
    op.create_index(
        "ix_kg_node_dedup",
        "kg_node",
        ["label_normalized", "schema_type_uri", "user_id"],
        unique=True,
    )

    # --- kg_edge ---
    op.create_table(
        "kg_edge",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("from_node_id", sa.Integer(), nullable=False),
        sa.Column("to_node_id", sa.Integer(), nullable=False),
        sa.Column("canonical_property_id", sa.Integer(), nullable=True),
        sa.Column("property_uri", sqlmodel.sql.sqltypes.AutoString(length=500), nullable=True),
        sa.Column("property_label", sqlmodel.sql.sqltypes.AutoString(length=255), nullable=False),
        sa.Column("raw_relationship_type", sqlmodel.sql.sqltypes.AutoString(length=100), nullable=True),
        sa.Column("properties", sa.dialects.postgresql.JSONB(), nullable=True),
        sa.Column("source_document_id", sa.Integer(), nullable=True),
        sa.Column("vector", Vector(1536), nullable=True),
        sa.Column("user_id", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["from_node_id"], ["kg_node.id"]),
        sa.ForeignKeyConstraint(["to_node_id"], ["kg_node.id"]),
        sa.ForeignKeyConstraint(["canonical_property_id"], ["kg_canonical_property.id"]),
        sa.ForeignKeyConstraint(["source_document_id"], ["document.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_kg_edge_from_node_id"), "kg_edge", ["from_node_id"])
    op.create_index(op.f("ix_kg_edge_to_node_id"), "kg_edge", ["to_node_id"])
    op.create_index(op.f("ix_kg_edge_canonical_property_id"), "kg_edge", ["canonical_property_id"])
    op.create_index(op.f("ix_kg_edge_source_document_id"), "kg_edge", ["source_document_id"])
    op.create_index(op.f("ix_kg_edge_user_id"), "kg_edge", ["user_id"])
    op.create_index(
        "ix_kg_edge_dedup",
        "kg_edge",
        ["from_node_id", "to_node_id", "property_uri", "source_document_id"],
        unique=True,
    )
    op.execute(
        """
        CREATE INDEX ix_kg_edge_vector_hnsw
        ON kg_edge
        USING hnsw (vector vector_cosine_ops)
        WITH (m = 16, ef_construction = 64)
        """
    )

    # --- kg_node_document ---
    op.create_table(
        "kg_node_document",
        sa.Column("node_id", sa.Integer(), nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["node_id"], ["kg_node.id"]),
        sa.ForeignKeyConstraint(["document_id"], ["document.id"]),
        sa.PrimaryKeyConstraint("node_id", "document_id"),
    )


def downgrade() -> None:
    op.drop_table("kg_node_document")
    op.drop_index("ix_kg_edge_vector_hnsw", table_name="kg_edge")
    op.drop_index("ix_kg_edge_dedup", table_name="kg_edge")
    op.drop_index(op.f("ix_kg_edge_user_id"), table_name="kg_edge")
    op.drop_index(op.f("ix_kg_edge_source_document_id"), table_name="kg_edge")
    op.drop_index(op.f("ix_kg_edge_canonical_property_id"), table_name="kg_edge")
    op.drop_index(op.f("ix_kg_edge_to_node_id"), table_name="kg_edge")
    op.drop_index(op.f("ix_kg_edge_from_node_id"), table_name="kg_edge")
    op.drop_table("kg_edge")
    op.drop_index("ix_kg_node_dedup", table_name="kg_node")
    op.drop_index(op.f("ix_kg_node_user_id"), table_name="kg_node")
    op.drop_index(op.f("ix_kg_node_wikidata_id"), table_name="kg_node")
    op.drop_index(op.f("ix_kg_node_canonical_class_id"), table_name="kg_node")
    op.drop_index(op.f("ix_kg_node_label_normalized"), table_name="kg_node")
    op.drop_index(op.f("ix_kg_node_label"), table_name="kg_node")
    op.drop_table("kg_node")
    op.drop_index("ix_kg_canonical_property_vector_hnsw", table_name="kg_canonical_property")
    op.drop_index(op.f("ix_kg_canonical_property_uri"), table_name="kg_canonical_property")
    op.drop_table("kg_canonical_property")
    op.drop_index("ix_kg_canonical_class_vector_hnsw", table_name="kg_canonical_class")
    op.drop_index(op.f("ix_kg_canonical_class_uri"), table_name="kg_canonical_class")
    op.drop_table("kg_canonical_class")
