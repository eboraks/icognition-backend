"""
Bookmark management API routes
"""

from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, Query, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime
from pydantic import BaseModel, Field
import uuid as uuid_pkg
from sqlmodel import select
from app.db.database import get_session
from app.core.user_context import UserContext, get_authenticated_user_context, get_active_user_context
from app.services.bookmark_service import BookmarkService
from app.api.models.user_models import UserProfileResponse
from app.log import get_logger
from app import app_logic, html_parser
import app.getters as getter
from app.services.content_analysis_service import get_content_analysis_service
import app.embedding_handler as embedding_handler_module
from app.models import Document, Bookmark, PagePayload
from app.services.document_service import DocumentService


logger = get_logger(__name__)

# Initialize embedding handler instance
embedding_handler = embedding_handler_module.EmbeddingHandler()


async def _process_document_content(
    session: AsyncSession,
    document_id: str,
    title: Optional[str],
    url: Optional[str]
):
    """
    Background task to process document content for summarization and bullet points
    
    Args:
        session: Database session
        document_id: ID of the document to process
        title: Document title
        url: Document URL
    """
    try:
        logger.info(f"Starting content processing for document {document_id}")
        
        # Get the document
        result = await session.execute(
            select(Document).where(Document.id == document_id)
        )
        document = result.scalar_one_or_none()
        
        if not document:
            logger.error(f"Document {document_id} not found")
            return
        
        # Get content analysis service
        content_analysis_service = get_content_analysis_service()
        
        # Analyze the document content
        analysis_result = await content_analysis_service.analyze_document_content(
            content=document.content or "",
            title=title,
            url=url
        )
        
        # Update document with analysis results
        document.ai_is_about = analysis_result['summary']
        document.ai_bullet_points = analysis_result['bullet_points']
        document.updated_at = datetime.now()
        
        # Commit changes
        await session.commit()
        
        logger.info(f"Successfully processed document {document_id} with summary and bullet points")
        
    except Exception as e:
        logger.error(f"Error processing document {document_id}: {str(e)}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        # Don't re-raise to avoid breaking the background task

router = APIRouter(prefix="/bookmarks", tags=["bookmarks"])

@router.post("/{bookmark_id}/re-analyze")
async def re_analyze_bookmark(
    bookmark_id: uuid_pkg.UUID,
    background_tasks: BackgroundTasks,
    user_context: UserContext = Depends(get_authenticated_user_context),
    session: AsyncSession = Depends(get_session)
):
    """Re-trigger content analysis for a bookmark's document"""
    try:
        logger.info(f"Re-triggering analysis for bookmark: {bookmark_id}")
        
        # Get the bookmark
        result = await session.execute(
            select(Bookmark).where(
                Bookmark.id == bookmark_id,
                Bookmark.user_id == user_context.user.id
            )
        )
        bookmark = result.scalar_one_or_none()
        
        if not bookmark:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Bookmark not found"
            )
        
        if not bookmark.document_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Bookmark has no associated document"
            )
        
        # Start background processing
        content_analysis_service = get_content_analysis_service()
        background_tasks.add_task(
            _process_document_content,
            session,
            bookmark.document_id,
            bookmark.title,
            bookmark.url
        )
        
        return {
            "message": "Re-analysis triggered successfully",
            "bookmark_id": bookmark_id,
            "document_id": bookmark.document_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        logger.error(f"Error re-triggering analysis: {e}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to re-trigger analysis"
        )

@router.get("/test-auth")
async def test_auth_disabled():
    """Test endpoint to verify DISABLE_AUTH is working"""
    from app.core.config import settings
    
    return {
        "message": "Test endpoint working",
        "disable_auth": settings.DISABLE_AUTH
    }


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
    
    id: uuid_pkg.UUID
    url: str
    title: str
    description: Optional[str] = None
    content: Optional[str] = None
    bookmark_metadata: Optional[Dict[str, Any]] = None
    is_processed: bool
    processing_status: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    user_id: str
    document_id: Optional[uuid_pkg.UUID] = None

class BookmarkListResponse(BaseModel):
    """Bookmark list response model"""
    
    bookmarks: List[BookmarkResponse]
    total: int
    page: int
    page_size: int
    has_next: bool
    has_previous: bool


@router.post("/", response_model=BookmarkResponse, status_code=201)
async def create_bookmark(
    bookmark_data: BookmarkCreateRequest,
    background_tasks: BackgroundTasks,
    user_context: UserContext = Depends(get_authenticated_user_context),
    session: AsyncSession = Depends(get_session)
):
    """Create a new bookmark with full document processing workflow"""
    try:
        logger.info(f"Creating bookmark for URL: {bookmark_data.url}")
        
        # Check for duplicate bookmark (same URL and user)
        existing_bookmark = await session.execute(
            select(Bookmark).where(
                Bookmark.url == bookmark_data.url,
                Bookmark.user_id == user_context.user.id
            )
        )
        existing_bookmark = existing_bookmark.scalar_one_or_none()
        
        document_service = DocumentService(session)
        if existing_bookmark:
            ## Get the document, and if it doesn't have AI content, re-analyze it
            document = await document_service.get_document_by_id(
                user_id=user_context.user.id,
                document_id=existing_bookmark.document_id
            )
            if document is not None and (document.ai_is_about is None or document.ai_bullet_points is None):
                background_tasks.add_task(
                    _process_document_content,
                    session,
                    document.id,
                    existing_bookmark.title,
                    existing_bookmark.url
                )
                background_tasks.add_task(embedding_handler._find_documents_without_embeddings, user_context.user.id)

            logger.info(f"Duplicate bookmark found for URL: {bookmark_data.url}, returning existing bookmark")
            return BookmarkResponse(
                id=existing_bookmark.id,
                url=existing_bookmark.url,
                title=existing_bookmark.title,
                description=existing_bookmark.description,
                content=existing_bookmark.content,
                bookmark_metadata=existing_bookmark.bookmark_metadata,
                is_processed=existing_bookmark.is_processed,
                processing_status=existing_bookmark.processing_status,
                created_at=existing_bookmark.created_at,
                updated_at=existing_bookmark.updated_at,
                user_id=existing_bookmark.user_id,
                document_id=existing_bookmark.document_id
            )
        
        logger.info(f"No duplicate found, proceeding with bookmark creation for URL: {bookmark_data.url}")
        
        # Validate URL
        if html_parser.unsupported_page_url(bookmark_data.url):
            logger.warning(f"Invalid URL provided: {bookmark_data.url}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="I am sorry, I can't analyze home or search pages"
            )
        
        # Check if we have clean text content (from iPhone app) or need to fetch HTML
        _doc = None
        
        if bookmark_data.content and _is_clean_text_content(bookmark_data.content):
            logger.info(f"Processing clean text content for URL: {bookmark_data.url}")
            _doc = await _create_document_from_clean_text(
                bookmark_data, user_context, session
            )
            logger.info(f"Document created from clean text: {_doc.id if _doc else 'None'}")
        else:
            logger.info(f"Processing HTML content for URL: {bookmark_data.url}")
            # Create page object from URL (this extracts content)
            
            page_payload = PagePayload(
                url=bookmark_data.url,
                user_id=str(user_context.user.id),  # Convert to string for legacy compatibility
                title=bookmark_data.title,
                description=bookmark_data.description,
                content=bookmark_data.content
            )
            
            page = app_logic.create_page(page_payload)
            
            if page is None:
                logger.warning(f"Page object not created for {bookmark_data.url}")
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Hmm, I wasn't able to find information on this page. I sent a message to our engineers"
                )
            
            # Create document from page
            _doc = await _create_document_from_page(page, user_context, session)
            logger.info(f"Document created from page: {_doc.id if _doc else 'None'}")
        
        logger.info(f"Final document status: {_doc.id if _doc else 'None'}")
        
        # Create bookmark record
        bookmark = Bookmark(
            url=bookmark_data.url,
            title=bookmark_data.title or "Untitled",
            description=bookmark_data.description,
            content=bookmark_data.content,
            bookmark_metadata=bookmark_data.metadata or {},
            user_id=user_context.user.id,
            document_id=_doc.id if _doc else None
        )
        
        # Save bookmark to database
        session.add(bookmark)
        await session.commit()
        await session.refresh(bookmark)
        
        if _doc is not None and (_doc.ai_is_about is None or _doc.ai_bullet_points is None):
            # Start background processing tasks
            background_tasks.add_task(
                _process_document_content,
                session,
                _doc.id,
                bookmark.title,
                bookmark.url
            )
            
            # Find documents without embeddings
            background_tasks.add_task(embedding_handler._find_documents_without_embeddings, user_context.user.id)
        
        # Return bookmark response
        return BookmarkResponse(
            id=bookmark.id,
            url=bookmark.url,
            title=bookmark.title,
            description=bookmark.description,
            content=bookmark.content,
            bookmark_metadata=bookmark.bookmark_metadata,
            is_processed=_doc is not None,
            processing_status="pending" if _doc else "not_processed",
            created_at=bookmark.created_at,
            updated_at=bookmark.updated_at,
            user_id=bookmark.user_id,
            document_id=_doc.id if _doc else None
        )
            
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        logger.error(f"Error creating bookmark: {e}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create bookmark"
        )


@router.get("/find", response_model=BookmarkResponse)
async def find_bookmark(
    query: str = Query(..., description="URL to search for"),
    user_context: UserContext = Depends(get_authenticated_user_context),
    session: AsyncSession = Depends(get_session)
):
    """Find an existing bookmark by URL"""
    try:
        logger.info(f"Searching for bookmark with URL: {query}")
        
        # Search for existing bookmark with this URL and user
        result = await session.execute(
            select(Bookmark).where(
                Bookmark.url == query,
                Bookmark.user_id == user_context.user.id
            )
        )
        existing_bookmark = result.scalar_one_or_none()
        
        if not existing_bookmark:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No bookmark found for URL: {query}"
            )
        
        logger.info(f"Found bookmark: {existing_bookmark.id}")
        
        return BookmarkResponse(
            id=existing_bookmark.id,
            url=existing_bookmark.url,
            title=existing_bookmark.title,
            description=existing_bookmark.description,
            content=existing_bookmark.content,
            bookmark_metadata=existing_bookmark.bookmark_metadata,
            is_processed=existing_bookmark.is_processed,
            processing_status=existing_bookmark.processing_status,
            created_at=existing_bookmark.created_at,
            updated_at=existing_bookmark.updated_at,
            user_id=existing_bookmark.user_id,
            document_id=existing_bookmark.document_id
        )
        
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        logger.error(f"Error finding bookmark: {e}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to find bookmark"
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
            firebase_uid=user_context.user.id,
            limit=page_size,
            offset=offset,
            is_processed=is_processed
        )
        
        total_count = await bookmark_service.count_user_bookmarks(
            session=session,
            firebase_uid=user_context.user.id,
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
    bookmark_id: uuid_pkg.UUID,
    user_context: UserContext = Depends(get_authenticated_user_context),
    session: AsyncSession = Depends(get_session)
):
    """Get a specific bookmark by ID"""
    try:
        bookmark_service = BookmarkService()
        
        bookmark = await bookmark_service.get_bookmark_by_id(
            session=session,
            bookmark_id=bookmark_id,
            firebase_uid=user_context.user.id
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
    bookmark_id: uuid_pkg.UUID,
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
            firebase_uid=user_context.user.id,
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
            firebase_uid=user_context.user.id
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
    bookmark_id: uuid_pkg.UUID,
    user_context: UserContext = Depends(get_authenticated_user_context),
    session: AsyncSession = Depends(get_session)
):
    """Delete a specific bookmark"""
    try:
        bookmark_service = BookmarkService()
        
        success = await bookmark_service.delete_bookmark(
            session=session,
            bookmark_id=bookmark_id,
            firebase_uid=user_context.user.id
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
            firebase_uid=user_context.user.id,
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


def _is_clean_text_content(content: str) -> bool:
    """
    Detect if content is clean text (from iPhone app) vs raw HTML.
    
    Clean text indicators:
    - No HTML tags
    - Contains readable sentences
    - Has proper spacing and punctuation
    """
    if not content or len(content.strip()) < 50:
        return False
    
    # Check for HTML tags
    html_tags = ['<html', '<body', '<div', '<p', '<span', '<h1', '<h2', '<h3', '<br', '<img', '<a href']
    if any(tag in content.lower() for tag in html_tags):
        return False
    
    # Check for clean text indicators
    clean_text_indicators = [
        content.count('.') > 2,  # Multiple sentences
        content.count(' ') > 10,  # Proper spacing
        len(content.split()) > 20,  # Substantial content
        not content.startswith('<'),  # Doesn't start with HTML
    ]
    
    return sum(clean_text_indicators) >= 3


async def _create_document_from_clean_text(
    bookmark_data: BookmarkCreateRequest,
    user_context: UserContext,
    session: AsyncSession
) -> Document:
    """
    Create Document directly from clean text content without Page object.
    This bypasses HTML parsing for iPhone app content.
    """
    
    
    logger.info(f"Creating document from clean text for URL: {bookmark_data.url}")
    
    # Check if document already exists for this URL
    clean_url = bookmark_data.url.strip()
    result = await session.execute(
        select(Document).where(
            Document.url == clean_url,
            Document.user_id == user_context.user.id
        )
    )
    existing_doc = result.scalar_one_or_none()
    
    if existing_doc:
        logger.info(f"Document already exists for {clean_url}, returning existing document")
        return existing_doc
    
    # Create new document from clean text
    doc = Document(
        title=bookmark_data.title or "Untitled",
        url=clean_url,
        content_source="text",
        content=bookmark_data.content,
        user_id=user_context.user.id,
        created_at=datetime.now(),
        updated_at=datetime.now()
    )
    
    # Save to database
    try:
        session.add(doc)
        await session.commit()
        await session.refresh(doc)
        
        logger.info(f"Created document {doc.id} from clean text")
        return doc
    except Exception as e:
        import traceback
        logger.error(f"Error creating document from clean text: {e}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise


async def _create_document_from_page(
    page,
    user_context: UserContext,
    session: AsyncSession
) -> Document:
    """
    Create Document from Page object (HTML content).
    """
    
    logger.info(f"Creating document from page for URL: {page.clean_url}")
    
    # Check if document already exists for this URL
    result = await session.execute(
        select(Document).where(
            Document.url == page.clean_url,
            Document.user_id == user_context.user.id
        )
    )
    existing_doc = result.scalar_one_or_none()
    
    if existing_doc:
        logger.info(f"Document already exists for {page.clean_url}, returning existing document")
        return existing_doc
    
    # Create new document from page
    doc = Document(
        title=page.title or "Untitled",
        url=page.clean_url,
        content_source="html",
        raw_html=page.html_root_element,
        content=page.full_text,
        user_id=user_context.user.id,
        created_at=datetime.now(),
        updated_at=datetime.now()
    )
    
    # Save to database
    session.add(doc)
    await session.commit()
    await session.refresh(doc)
    
    logger.info(f"Created document {doc.id} from page")
    return doc
