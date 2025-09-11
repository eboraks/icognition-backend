"""
Bookmark management API routes
"""

from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime
from pydantic import BaseModel, Field

from app.db.database import get_session
from app.core.user_context import UserContext, get_authenticated_user_context, get_active_user_context
from app.services.bookmark_service import BookmarkService
from app.api.models.user_models import UserProfileResponse
from app.utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/bookmarks", tags=["bookmarks"])


class BookmarkCreateRequest(BaseModel):
    """Bookmark creation request model"""
    
    url: str = Field(..., max_length=2048, description="URL of the bookmark")
    title: str = Field(..., max_length=500, description="Title of the bookmark")
    description: Optional[str] = Field(None, description="Description of the bookmark")
    content: Optional[str] = Field(None, description="Full content of the page")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional metadata")


class BookmarkUpdateRequest(BaseModel):
    """Bookmark update request model"""
    
    title: Optional[str] = Field(None, max_length=500, description="Title of the bookmark")
    description: Optional[str] = Field(None, description="Description of the bookmark")
    content: Optional[str] = Field(None, description="Full content of the page")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional metadata")


class BookmarkResponse(BaseModel):
    """Bookmark response model"""
    
    id: int
    url: str
    title: str
    description: Optional[str] = None
    content: Optional[str] = None
    bookmark_metadata: Optional[Dict[str, Any]] = None
    is_processed: bool
    processing_status: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    user_id: int


class BookmarkListResponse(BaseModel):
    """Bookmark list response model"""
    
    bookmarks: List[BookmarkResponse]
    total: int
    page: int
    page_size: int
    has_next: bool
    has_previous: bool


@router.post("/", response_model=BookmarkResponse)
async def create_bookmark(
    bookmark_data: BookmarkCreateRequest,
    user_context: UserContext = Depends(get_authenticated_user_context),
    session: AsyncSession = Depends(get_session)
):
    """Create a new bookmark (automatically creates user if needed)"""
    try:
        bookmark_service = BookmarkService()
        
        bookmark = await BookmarkService.create_bookmark(
            session=session,
            firebase_uid=user_context.firebase_uid,
            url=bookmark_data.url,
            title=bookmark_data.title,
            description=bookmark_data.description,
            content=bookmark_data.content,
            metadata=bookmark_data.metadata
        )
        
        if not bookmark:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create bookmark"
            )
        
        return BookmarkResponse(
            id=bookmark.id,
            url=bookmark.url,
            title=bookmark.title,
            description=bookmark.description,
            content=bookmark.content,
            bookmark_metadata=bookmark.bookmark_metadata,
            is_processed=bookmark.is_processed,
            processing_status=bookmark.processing_status,
            created_at=bookmark.created_at,
            updated_at=bookmark.updated_at,
            user_id=bookmark.user_id
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating bookmark: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create bookmark"
        )


@router.get("/", response_model=BookmarkListResponse)
async def get_user_bookmarks(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=100, description="Number of bookmarks per page"),
    is_processed: Optional[bool] = Query(None, description="Filter by processing status"),
    user_context: UserContext = Depends(get_authenticated_user_context),
    session: AsyncSession = Depends(get_session)
):
    """Get current user's bookmarks with pagination"""
    try:
        bookmark_service = BookmarkService()
        
        offset = (page - 1) * page_size
        
        bookmarks = await bookmark_service.get_user_bookmarks(
            session=session,
            firebase_uid=user_context.firebase_uid,
            limit=page_size,
            offset=offset,
            is_processed=is_processed
        )
        
        total_count = await bookmark_service.count_user_bookmarks(
            session=session,
            firebase_uid=user_context.firebase_uid,
            is_processed=is_processed
        )
        
        bookmark_responses = [
            BookmarkResponse(
                id=bm.id,
                url=bm.url,
                title=bm.title,
                description=bm.description,
                content=bm.content,
                bookmark_metadata=bm.bookmark_metadata,
                is_processed=bm.is_processed,
                processing_status=bm.processing_status,
                created_at=bm.created_at,
                updated_at=bm.updated_at,
                user_id=bm.user_id
            )
            for bm in bookmarks
        ]
        
        has_next = (offset + page_size) < total_count
        has_previous = page > 1
        
        return BookmarkListResponse(
            bookmarks=bookmark_responses,
            total=total_count,
            page=page,
            page_size=page_size,
            has_next=has_next,
            has_previous=has_previous
        )
    except Exception as e:
        logger.error(f"Error getting user bookmarks: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve bookmarks"
        )


@router.get("/{bookmark_id}", response_model=BookmarkResponse)
async def get_bookmark(
    bookmark_id: int,
    user_context: UserContext = Depends(get_authenticated_user_context),
    session: AsyncSession = Depends(get_session)
):
    """Get a specific bookmark by ID"""
    try:
        bookmark_service = BookmarkService()
        
        bookmark = await bookmark_service.get_bookmark_by_id(
            session=session,
            bookmark_id=bookmark_id,
            firebase_uid=user_context.firebase_uid
        )
        
        if not bookmark:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Bookmark not found"
            )
        
        return BookmarkResponse(
            id=bookmark.id,
            url=bookmark.url,
            title=bookmark.title,
            description=bookmark.description,
            content=bookmark.content,
            bookmark_metadata=bookmark.bookmark_metadata,
            is_processed=bookmark.is_processed,
            processing_status=bookmark.processing_status,
            created_at=bookmark.created_at,
            updated_at=bookmark.updated_at,
            user_id=bookmark.user_id
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting bookmark {bookmark_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve bookmark"
        )


@router.put("/{bookmark_id}", response_model=BookmarkResponse)
async def update_bookmark(
    bookmark_id: int,
    bookmark_update: BookmarkUpdateRequest,
    user_context: UserContext = Depends(get_authenticated_user_context),
    session: AsyncSession = Depends(get_session)
):
    """Update a specific bookmark"""
    try:
        bookmark_service = BookmarkService()
        
        success = await bookmark_service.update_bookmark(
            session=session,
            bookmark_id=bookmark_id,
            firebase_uid=user_context.firebase_uid,
            title=bookmark_update.title,
            description=bookmark_update.description,
            content=bookmark_update.content,
            metadata=bookmark_update.metadata
        )
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Bookmark not found or update failed"
            )
        
        # Get updated bookmark
        updated_bookmark = await bookmark_service.get_bookmark_by_id(
            session=session,
            bookmark_id=bookmark_id,
            firebase_uid=user_context.firebase_uid
        )
        
        if not updated_bookmark:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Bookmark not found after update"
            )
        
        return BookmarkResponse(
            id=updated_bookmark.id,
            url=updated_bookmark.url,
            title=updated_bookmark.title,
            description=updated_bookmark.description,
            content=updated_bookmark.content,
            bookmark_metadata=updated_bookmark.bookmark_metadata,
            is_processed=updated_bookmark.is_processed,
            processing_status=updated_bookmark.processing_status,
            created_at=updated_bookmark.created_at,
            updated_at=updated_bookmark.updated_at,
            user_id=updated_bookmark.user_id
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating bookmark {bookmark_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update bookmark"
        )


@router.delete("/{bookmark_id}")
async def delete_bookmark(
    bookmark_id: int,
    user_context: UserContext = Depends(get_authenticated_user_context),
    session: AsyncSession = Depends(get_session)
):
    """Delete a specific bookmark"""
    try:
        bookmark_service = BookmarkService()
        
        success = await bookmark_service.delete_bookmark(
            session=session,
            bookmark_id=bookmark_id,
            firebase_uid=user_context.firebase_uid
        )
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Bookmark not found or delete failed"
            )
        
        return {"message": "Bookmark deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting bookmark {bookmark_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete bookmark"
        )


@router.get("/url/{url:path}")
async def get_bookmarks_by_url(
    url: str,
    user_context: UserContext = Depends(get_authenticated_user_context),
    session: AsyncSession = Depends(get_session)
):
    """Get bookmarks by URL for current user"""
    try:
        bookmark_service = BookmarkService()
        
        bookmarks = await bookmark_service.get_bookmarks_by_url(
            session=session,
            firebase_uid=user_context.firebase_uid,
            url=url
        )
        
        bookmark_responses = [
            BookmarkResponse(
                id=bm.id,
                url=bm.url,
                title=bm.title,
                description=bm.description,
                content=bm.content,
                bookmark_metadata=bm.bookmark_metadata,
                is_processed=bm.is_processed,
                processing_status=bm.processing_status,
                created_at=bm.created_at,
                updated_at=bm.updated_at,
                user_id=bm.user_id
            )
            for bm in bookmarks
        ]
        
        return {"bookmarks": bookmark_responses, "count": len(bookmark_responses)}
    except Exception as e:
        logger.error(f"Error getting bookmarks by URL {url}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve bookmarks by URL"
        )
