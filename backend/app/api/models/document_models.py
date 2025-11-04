"""
API models for document management
"""

from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, HttpUrl, Field, field_validator, model_validator, ConfigDict
from app.models import Document
import uuid as uuid_pkg

class DocumentCreateRequest(BaseModel):
    """Request model for creating a new document"""
    
    url: Optional[HttpUrl] = Field(None, description="URL of the web page to bookmark")
    title: Optional[str] = Field(None, max_length=500, description="Title of the document")
    content: Optional[str] = Field(None, description="Direct content (HTML or text) from the user")
    content_type: str = Field(default="url", description="Content source type: 'url', 'html', or 'text'")
    raw_html: Optional[str] = Field(None, description="Raw HTML content (legacy field, deprecated)")
    
    @field_validator('title')
    @classmethod
    def validate_title(cls, v):
        if v is not None and len(v.strip()) == 0:
            raise ValueError('Title cannot be empty')
        return v
    
    @field_validator('content_type')
    @classmethod
    def validate_content_type(cls, v):
        if v not in ['url', 'html', 'text']:
            raise ValueError('content_type must be one of: url, html, text')
        return v
    
    @field_validator('content')
    @classmethod
    def validate_content(cls, v, info):
        # If content_type is not 'url', content should be provided
        content_type = info.data.get('content_type', 'url')
        if content_type != 'url' and not v:
            raise ValueError('content is required when content_type is not "url"')
        return v
    
    @model_validator(mode='after')
    def validate_url_or_content(self):
        """Validate that either URL or content is provided"""
        if not self.url and not self.content:
            raise ValueError('Either URL or content must be provided')
        return self


class DocumentResponse(BaseModel):
    """Response model for document data"""
    
    id: int
    updated_at: datetime
    user_id: str
    url: Optional[str] = None
    title: str
    content_source: str
    author: Optional[str] = None
    publication_date: Optional[datetime] = None
    description: Optional[str] = None
    keywords: Optional[List[str]] = None
    content: Optional[str] = None
    document_metadata: Optional[Dict[str, Any]] = None
    ai_is_about: Optional[str] = None
    ai_bullet_points: Optional[List[str]] = None
    
    model_config = ConfigDict(from_attributes=True)


class DocumentListResponse(BaseModel):
    """Response model for document list with pagination"""
    
    documents: List[DocumentResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class DocumentUpdateRequest(BaseModel):
    """Request model for updating document metadata"""
    
    title: Optional[str] = Field(None, max_length=500)
    author: Optional[str] = Field(None, max_length=255)
    description: Optional[str] = None
    keywords: Optional[List[str]] = None
    document_metadata: Optional[Dict[str, Any]] = None
    
    @field_validator('title')
    @classmethod
    def validate_title(cls, v):
        if v is not None and len(v.strip()) == 0:
            raise ValueError('Title cannot be empty')
        return v


class DocumentProcessingStatusResponse(BaseModel):
    """Response model for document processing status"""
    
    id: int
    status: str
    updated_at: datetime
    document_metadata: Optional[Dict[str, Any]] = None
    
    model_config = ConfigDict(from_attributes=True)


class DocumentContentResponse(BaseModel):
    """Response model for document content (for analysis)"""
    
    id: int
    title: str
    content: str
    author: Optional[str] = None
    publication_date: Optional[datetime] = None
    description: Optional[str] = None
    keywords: Optional[List[str]] = None
    
    model_config = ConfigDict(from_attributes=True)


class EntityTreeNodeData(BaseModel):
    """Data payload for entity tree leaf nodes"""
    entity_id: int
    document_ids: List[int]


class EntityTreeNode(BaseModel):
    """Tree node structure for PrimeVue Tree component"""
    key: str
    label: str
    children: Optional[List['EntityTreeNode']] = None
    data: Optional[EntityTreeNodeData] = None


class EntityTreeResponse(BaseModel):
    """Response model for entity tree structure"""
    tree: List[EntityTreeNode]
    
    model_config = ConfigDict(from_attributes=True)

# Update forward reference for recursive model
EntityTreeNode.model_rebuild()
