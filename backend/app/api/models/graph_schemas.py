"""
Pydantic schemas for graph exploration API endpoints.
Uses KG tables (kg_node, kg_edge, kg_node_document).
"""

from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum


class SearchResultType(str, Enum):
    entity = "entity"
    relationship = "relationship"
    document = "document"


# ── Entity (Node) ─────────────────────────────────

class EntitySummary(BaseModel):
    """Lightweight entity for graph rendering (Cytoscape node data)."""
    id: int
    name: str
    type: str  # raw_type from extraction (person, organization, location, etc.)
    canonical_type: Optional[str] = None  # schema.org class label (Person, Country, City)
    wikidata_id: Optional[str] = None


class DocumentSummary(BaseModel):
    id: int
    title: str


class EntityRead(BaseModel):
    """Full entity detail for the side panel."""
    id: int
    name: str
    type: str
    canonical_type: Optional[str] = None
    schema_type_uri: Optional[str] = None
    wikidata_id: Optional[str] = None
    description: Optional[str] = None
    document_count: int = 0
    documents: list[DocumentSummary] = []


# ── Relationship (Edge) ───────────────────────────

class RelationshipSummary(BaseModel):
    """Lightweight relationship for graph rendering (Cytoscape edge data)."""
    id: int
    from_entity_id: int
    to_entity_id: int
    relationship_type: str  # property_label (canonical or raw)
    property_uri: Optional[str] = None


class RelationshipRead(BaseModel):
    """Full relationship detail for the side panel."""
    id: int
    from_entity: EntitySummary
    to_entity: EntitySummary
    relationship_type: str
    property_uri: Optional[str] = None
    raw_relationship_type: Optional[str] = None
    source_documents: list[DocumentSummary] = []


# ── Search ────────────────────────────────────────

class SearchHit(BaseModel):
    id: int
    label: str
    type: str
    result_type: SearchResultType
    similarity: float


class KGRelationshipContext(BaseModel):
    """A relationship in the knowledge graph context."""
    from_entity: str
    relationship_type: str
    to_entity: str


class KGEntityContext(BaseModel):
    """An entity with its relationships from the knowledge graph."""
    id: int
    name: str
    type: str
    description: Optional[str] = None
    relationships: list[KGRelationshipContext] = []
    documents: list[str] = []  # document titles


class SearchResponse(BaseModel):
    query: str
    total: int
    results: list[SearchHit]
    kg_context: list[KGEntityContext] = []  # enriched KG context for matched entities


# ── Graph / Neighborhood ──────────────────────────

class EntityDocumentLink(BaseModel):
    """Link between an entity and a document for graph edge rendering."""
    entity_id: int
    document_id: int


class NeighborhoodResponse(BaseModel):
    """Everything needed to render a subgraph in Cytoscape.js."""
    entities: list[EntitySummary]
    relationships: list[RelationshipSummary]
    documents: list[DocumentSummary] = []
    entity_document_links: list[EntityDocumentLink] = []
    center_entity_id: Optional[int] = None


class DocumentRead(BaseModel):
    """Full document detail for the side panel."""
    id: int
    title: str
    url: Optional[str] = None
    ai_markdown_content: Optional[str] = None
    entities: list[EntitySummary] = []


class SubgraphRequest(BaseModel):
    entity_ids: list[int] = Field(..., max_length=50)
    include_relationships: bool = True
