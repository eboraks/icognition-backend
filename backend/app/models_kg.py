"""
Knowledge Graph models using schema.org canonical types.

These tables run in parallel with the existing Entity/EntityRelationship tables.
No existing tables are modified.
"""

from typing import Optional, List, Dict, Any
from datetime import datetime

from sqlmodel import SQLModel, Field
from sqlalchemy import Column, Index, DateTime, Text, func
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from pgvector.sqlalchemy import Vector


# ---------------------------------------------------------------------------
# Canonical ontology reference tables (pre-populated from schema.org)
# ---------------------------------------------------------------------------

class KGCanonicalClass(SQLModel, table=True):
    """Schema.org class reference. Pre-populated by seed_ontology.py."""

    __tablename__ = "kg_canonical_class"

    id: Optional[int] = Field(default=None, primary_key=True)
    uri: str = Field(max_length=500, unique=True, nullable=False, index=True)
    label: str = Field(max_length=255, nullable=False)
    description: Optional[str] = Field(default=None, sa_column=Column(Text))
    parent_uri: Optional[str] = Field(default=None, max_length=500)
    vector: Optional[List[float]] = Field(default=None, sa_column=Column(Vector(1536)))

    __table_args__ = (
        Index("ix_kg_canonical_class_vector_hnsw", "vector",
              postgresql_using="hnsw",
              postgresql_with={"m": 16, "ef_construction": 64},
              postgresql_ops={"vector": "vector_cosine_ops"}),
    )


class KGCanonicalProperty(SQLModel, table=True):
    """Schema.org property reference. Pre-populated by seed_ontology.py."""

    __tablename__ = "kg_canonical_property"

    id: Optional[int] = Field(default=None, primary_key=True)
    uri: str = Field(max_length=500, unique=True, nullable=False, index=True)
    label: str = Field(max_length=255, nullable=False)
    description: Optional[str] = Field(default=None, sa_column=Column(Text))
    parent_uri: Optional[str] = Field(default=None, max_length=500)
    domain_class_uri: Optional[str] = Field(default=None, max_length=500)
    range_class_uri: Optional[str] = Field(default=None, max_length=500)
    vector: Optional[List[float]] = Field(default=None, sa_column=Column(Vector(1536)))

    __table_args__ = (
        Index("ix_kg_canonical_property_vector_hnsw", "vector",
              postgresql_using="hnsw",
              postgresql_with={"m": 16, "ef_construction": 64},
              postgresql_ops={"vector": "vector_cosine_ops"}),
    )


# ---------------------------------------------------------------------------
# Knowledge graph instance tables (populated during document processing)
# ---------------------------------------------------------------------------

class KGNode(SQLModel, table=True):
    """A node in the knowledge graph. Replaces Entity for the new schema."""

    __tablename__ = "kg_node"

    id: Optional[int] = Field(default=None, primary_key=True)
    uri: Optional[str] = Field(default=None, max_length=500)
    label: str = Field(max_length=500, nullable=False, index=True)
    label_normalized: str = Field(max_length=500, nullable=False, index=True)

    # Schema alignment (nullable — null means no canonical match)
    canonical_class_id: Optional[int] = Field(
        default=None, foreign_key="kg_canonical_class.id", index=True
    )
    schema_type_uri: Optional[str] = Field(default=None, max_length=500)

    # Raw LLM output (always populated — audit trail)
    raw_type: Optional[str] = Field(default=None, max_length=100)
    raw_description: Optional[str] = Field(default=None, sa_column=Column(Text))

    description: Optional[str] = Field(default=None, sa_column=Column(Text))
    properties: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(JSONB))
    wikidata_id: Optional[str] = Field(default=None, max_length=50, index=True)

    # Embedding for semantic dedup (encodes "name - description")
    vector: Optional[List[float]] = Field(default=None, sa_column=Column(Vector(1536)))

    # Legacy mapping for migration
    legacy_entity_id: Optional[int] = Field(
        default=None, foreign_key="entities.id", index=True
    )

    user_id: Optional[str] = Field(
        default=None, foreign_key="users.id", index=True, nullable=True
    )
    created_at: Optional[datetime] = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime(timezone=True), server_default=func.now()),
    )

    __table_args__ = (
        Index(
            "ix_kg_node_dedup",
            "label_normalized", "schema_type_uri", "user_id",
            unique=True,
        ),
        Index(
            "ix_kg_node_vector_hnsw", "vector",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"vector": "vector_cosine_ops"},
        ),
    )


class KGEdge(SQLModel, table=True):
    """A directed edge in the knowledge graph. Replaces EntityRelationship."""

    __tablename__ = "kg_edge"

    id: Optional[int] = Field(default=None, primary_key=True)
    from_node_id: int = Field(foreign_key="kg_node.id", nullable=False, index=True)
    to_node_id: int = Field(foreign_key="kg_node.id", nullable=False, index=True)

    # Schema alignment (nullable — null means no canonical match)
    canonical_property_id: Optional[int] = Field(
        default=None, foreign_key="kg_canonical_property.id", index=True
    )
    property_uri: Optional[str] = Field(default=None, max_length=500)
    property_label: str = Field(max_length=255, nullable=False)

    # Raw LLM output (always populated — audit trail)
    raw_relationship_type: Optional[str] = Field(default=None, max_length=100)

    properties: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(JSONB))
    source_document_id: Optional[int] = Field(
        default=None, foreign_key="document.id", index=True
    )

    # Embedding for semantic search over edges
    vector: Optional[List[float]] = Field(default=None, sa_column=Column(Vector(1536)))

    user_id: Optional[str] = Field(
        default=None, foreign_key="users.id", index=True, nullable=True
    )
    created_at: Optional[datetime] = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime(timezone=True), server_default=func.now()),
    )

    __table_args__ = (
        Index(
            "ix_kg_edge_dedup",
            "from_node_id", "to_node_id", "property_uri", "source_document_id",
            unique=True,
        ),
        Index(
            "ix_kg_edge_vector_hnsw", "vector",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"vector": "vector_cosine_ops"},
        ),
    )


class KGNodeDocument(SQLModel, table=True):
    """Junction table: which documents mention a KG node."""

    __tablename__ = "kg_node_document"

    node_id: int = Field(foreign_key="kg_node.id", primary_key=True)
    document_id: int = Field(foreign_key="document.id", primary_key=True)
    created_at: Optional[datetime] = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime(timezone=True), server_default=func.now()),
    )
