"""
Pydantic models for DSPy entity extraction ONLY
Simplified for faster entity-focused extraction
"""

from typing import List, Literal
from pydantic import BaseModel, Field

# --- EntityType Literal ---
EntityType = Literal[
    "person", "organization", "institution", "location", "event",
    "technology", "product", "science", "medical_condition",
    "organism", "regulation", "financial", "creative_work", "concept",
]


# --- Entity Model ---
class Entity(BaseModel):
    """Entity model for extracted entities"""
    name: str = Field(
        description="The extracted name of the entity."
    )
    type: EntityType = Field(
        description="The type of the entity."
    )
    description: str = Field(
        description="A brief (1-sentence) description of the entity's relevance in the text."
    )


# --- Entity Extraction Response Model ---
class EntityExtractionResult(BaseModel):
    """
    Response model for entity extraction
    """
    entities: List[Entity] = Field(
        description="A list of 10-15 key organizations, people, topics, and other entities mentioned in the content."
    )


# --- Relationship Models ---
class EntityRelationship(BaseModel):
    """A directed relationship between two entities."""
    from_entity: str = Field(description="Name of the source entity (must match an extracted entity name).")
    to_entity: str = Field(description="Name of the target entity (must match an extracted entity name).")
    relationship_type: str = Field(
        description=(
            "Short snake_case label for the relationship. "
            "Examples: works_for, founded, authored, mentions, opposes, located_in, part_of, acquired, "
            "collaborated_with, invested_in, regulated_by, responded_to."
        )
    )


class EntityRelationshipResult(BaseModel):
    """Response model for relationship extraction."""
    relationships: List[EntityRelationship] = Field(
        description="List of directed relationships between the extracted entities."
    )

