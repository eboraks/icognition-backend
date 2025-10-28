"""
Pydantic models for DSPy entity extraction ONLY
Simplified for faster entity-focused extraction
"""

from typing import List, Literal
from pydantic import BaseModel, Field

# --- EntityType Literal ---
EntityType = Literal["organization", "person", "topic", "location", "event", "technology", "product", "institution"]


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

