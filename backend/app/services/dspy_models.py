"""
Pydantic models for DSPy content extraction
"""

from typing import List, Literal
from pydantic import BaseModel, Field

# --- Define Literal types for strict validation ---
SourceType = Literal[
    "News Article", "Opinion Piece", "Blog Post", 
    "Social Media Post", "Report", "Other"
]

ObjectivityType = Literal[
    "Objective", "Subjective (Opinion)", "Biased (Pro-X)", 
    "Biased (Anti-Y)", "Satire"
]

ToneType = Literal[
    "Formal", "Informal", "Analytical", "Persuasive", 
    "Journalistic", "Casual", "Satirical"
]

IntentType = Literal[
    "To inform", "To persuade", "To analyze", 
    "To entertain", "To sell"
]

# --- EntityType Literal ---
EntityType = Literal["organization", "person", "topic"]


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


# --- Nested Model for Analysis ---
class ContentAnalysis(BaseModel):
    """Content analysis metadata"""
    objectivity: ObjectivityType = Field(
        description="The objectivity level of the content."
    )
    tone: ToneType = Field(
        description="The tone of the content."
    )
    intent: IntentType = Field(
        description="The intent of the content."
    )


# --- Main ContentExtract Model ---
class ContentExtract(BaseModel):
    """
    A Pydantic model for holding structured data extracted from a text source.
    """
    title: str = Field(
        description="The extracted title of the content."
    )
    source_type: SourceType = Field(
        description="The type of source."
    )
    summary: str = Field(
        description="A neutral, one-paragraph summary."
    )
    key_takeaways: List[str] = Field(
        description="A list of the most important facts, conclusions, or arguments."
    )
    key_entities: List[Entity] = Field(
        description="A list of all key organizations, people, and topics mentioned."
    )
    analysis: ContentAnalysis = Field(
        description="Analysis metadata including objectivity, tone, and intent."
    )
    access_notes: str = Field(
        default="", 
        description="Notes on access issues, e.g., paywalls."
    )

