"""
Base database models for iCognition Backend
"""

from sqlmodel import SQLModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from sqlalchemy import Column, DateTime, func, JSON, Text
from sqlalchemy.dialects.postgresql import ARRAY, FLOAT
from pgvector.sqlalchemy import Vector


class BaseModel(SQLModel):
    """Base model with common fields"""
    
    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: Optional[datetime] = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime(timezone=True), server_default=func.now())
    )
    updated_at: Optional[datetime] = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    )
    
    class Config:
        # Make this an abstract base class
        table = False


class VectorField:
    """Helper class for vector fields"""
    
    @staticmethod
    def create_vector_field(dimensions: int = 1536):
        """Create a vector field with specified dimensions"""
        return Field(
            sa_column=Column(ARRAY(FLOAT(precision=32)), nullable=True),
            description=f"Vector embedding with {dimensions} dimensions"
        )


# Example models for testing SQLModel integration
class TestDocument(SQLModel, table=True):
    """Test document model with vector embedding"""
    
    __tablename__ = "test_documents"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: Optional[datetime] = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime(timezone=True), server_default=func.now())
    )
    updated_at: Optional[datetime] = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    )
    
    title: str = Field(max_length=255)
    content: str
    embedding: Optional[List[float]] = VectorField.create_vector_field(1536)
    doc_metadata: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(JSON))


class TestEntity(SQLModel, table=True):
    """Test entity model"""
    
    __tablename__ = "test_entities"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: Optional[datetime] = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime(timezone=True), server_default=func.now())
    )
    updated_at: Optional[datetime] = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    )
    
    name: str = Field(max_length=255, index=True)
    description: Optional[str] = None
    entity_type: str = Field(max_length=100)
    embedding: Optional[List[float]] = VectorField.create_vector_field(1536)
    entity_metadata: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(JSON))


# User Management Models
class User(SQLModel, table=True):
    """User model for authentication and user management"""
    
    __tablename__ = "users"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: Optional[datetime] = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime(timezone=True), server_default=func.now())
    )
    updated_at: Optional[datetime] = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    )
    
    # Firebase UID - unique identifier from Firebase Auth
    firebase_uid: str = Field(max_length=128, index=True, unique=True)
    
    # User profile information
    email: Optional[str] = Field(max_length=255, index=True)
    display_name: Optional[str] = Field(max_length=255)
    photo_url: Optional[str] = Field(max_length=500)
    
    # User activity tracking
    last_active: Optional[datetime] = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime(timezone=True), server_default=func.now())
    )
    
    # User preferences and settings
    preferences: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(JSON))
    
    # Account status
    is_active: bool = Field(default=True)
    is_verified: bool = Field(default=False)
    
    # Timestamps for account lifecycle
    first_login: Optional[datetime] = Field(default_factory=datetime.utcnow)
    last_login: Optional[datetime] = Field(default_factory=datetime.utcnow)


# Bookmark Management Models
class Bookmark(SQLModel, table=True):
    """Bookmark model for web page bookmarks"""

    __tablename__ = "bookmarks"

    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: Optional[datetime] = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime(timezone=True), server_default=func.now())
    )
    updated_at: Optional[datetime] = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    )

    # User association
    user_id: int = Field(foreign_key="users.id", index=True)

    # Bookmark content
    url: str = Field(max_length=2048, index=True)
    title: str = Field(max_length=500)
    description: Optional[str] = None
    content: Optional[str] = None  # Full page content for analysis

    # Metadata
    bookmark_metadata: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(JSON))

    # Status
    is_processed: bool = Field(default=False)
    processing_status: Optional[str] = Field(max_length=50, default="pending")


# Document Management Models
class Document(SQLModel, table=True):
    """Document model for processed web page content"""

    __tablename__ = "documents"

    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: Optional[datetime] = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime(timezone=True), server_default=func.now())
    )
    updated_at: Optional[datetime] = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    )

    # User association
    user_id: int = Field(foreign_key="users.id", index=True)

    # Document identification
    url: Optional[str] = Field(default=None, max_length=2048, index=True)
    title: str = Field(max_length=500)
    
    # Content source tracking
    content_source: str = Field(default="url", max_length=20)  # "url", "html", "text"
    
    # Document metadata
    author: Optional[str] = Field(max_length=255)
    publication_date: Optional[datetime] = Field(sa_column=Column(DateTime(timezone=True)))
    description: Optional[str] = None
    keywords: Optional[List[str]] = Field(default=None, sa_column=Column(JSON))

    # Content storage
    raw_html: str = Field(sa_column=Column(Text))
    content: str = Field(sa_column=Column(Text))
    content_vector: Optional[List[float]] = Field(default=None, sa_column=Column(Vector(1536)))

    # Processing status
    status: str = Field(max_length=50, default="pending", index=True)
    
    # Additional metadata
    document_metadata: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(JSON))


class Entity(SQLModel, table=True):
    """Entity model for extracted entities from documents"""
    
    __tablename__ = "entities"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True, max_length=255)
    type: str = Field(index=True, max_length=50)  # Person, Product, Company, Location, Event, Technology, Topic
    description: Optional[str] = Field(default=None, sa_column=Column(Text))
    wikidata_id: Optional[str] = Field(default=None, index=True, max_length=50)
    wikidata_label: Optional[str] = Field(default=None, max_length=255)
    wikidata_description: Optional[str] = Field(default=None, sa_column=Column(Text))
    aliases: Optional[List[str]] = Field(default=None, sa_column=Column(ARRAY(Text)))
    vector: Optional[List[float]] = Field(default=None, sa_column=Column(Vector(768)))
    user_id: int = Field(foreign_key="users.id", index=True)
    created_at: Optional[datetime] = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime(timezone=True), server_default=func.now())
    )
    updated_at: Optional[datetime] = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    )


class EntityDocument(SQLModel, table=True):
    """Many-to-many relationship between entities and documents"""
    
    __tablename__ = "entity_documents"
    
    entity_id: int = Field(foreign_key="entities.id", primary_key=True)
    document_id: int = Field(foreign_key="documents.id", primary_key=True)
    relevance: float = Field(default=0.0)
    created_at: Optional[datetime] = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime(timezone=True), server_default=func.now())
    )


# Export all models for Alembic
__all__ = ["BaseModel", "VectorField", "TestDocument", "TestEntity", "User", "Bookmark", "Document", "Entity", "EntityDocument"]
