"""
Pydantic models for DSPy content extraction WITHOUT entity extraction
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


# --- Main ContentExtract Model WITHOUT entities ---
class ContentExtractNoEntities(BaseModel):
    """
    A Pydantic model for holding structured data extracted from a text source.
    This version excludes entity extraction for faster processing.
    """
    title: str = Field(
        description="The extracted title of the content."
    )
    source_type: SourceType = Field(
        description="The type of source."
    )
    markdown_content: str = Field(
        description="Detailed extracted content in Markdown format, such as paragraphs, bullet points, or tables depending on the source."
    )
    analysis: ContentAnalysis = Field(
        description="Analysis metadata including objectivity, tone, and intent."
    )
    access_notes: str = Field(
        default="", 
        description="Notes on access issues, e.g., paywalls."
    )

