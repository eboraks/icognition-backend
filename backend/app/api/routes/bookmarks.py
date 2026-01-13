"""
Bookmark management API routes
"""

from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, Query, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime
from pydantic import BaseModel, Field
from sqlmodel import select
from asyncio import create_task
from app.db.database import get_session
from app.core.config import settings
from app.core.user_context import UserContext, get_authenticated_user_context, get_active_user_context
from app.services.bookmark_service import BookmarkService
from app.api.models.user_models import UserProfileResponse
from app.utils.logging import get_logger
from app.services.content_analysis_service import get_content_analysis_service
from app.services.dspy_content_service import get_dspy_content_service
from app.models import Document, Bookmark
from app.services.document_service import DocumentService
from app.services.entity_extraction_task_manager import get_entity_extraction_task_manager
from app.services.dspy_entity_service import get_dspy_entity_service
from app.services.dspy_entity_adapter import DspyEntityAdapter
from app.services.embedding_service import get_embedding_service
from app.core.config import settings
from app.api.routes.websocket import get_connection_manager
from app.api.routes.notifications import get_notification_manager

logger = get_logger(__name__)

def sanitize_content_for_db(content: str) -> str:
    """Ensure content is valid UTF-8 and database-safe"""
    if not content:
        return content
    
    # Remove problematic characters for database storage
    content = content.replace('\x00', '')  # Null bytes
    content = content.replace('\x1a', '')  # SUB character
    
    # Ensure valid UTF-8 encoding
    try:
        content.encode('utf-8')
        return content
    except UnicodeEncodeError:
        # Replace invalid characters with replacement character
        return content.encode('utf-8', errors='replace').decode('utf-8')

# Legacy embedding handler removed - using modern services instead


async def _send_document_ready_message(
    document: Document,
    user_id: str,
    title: Optional[str] = None,
    url: Optional[str] = None
) -> None:
    """
    Send a document_ready notification for a processed document.
    
    Args:
        document: The document to send
        user_id: User ID to send the message to
        title: Override title (optional)
        url: Override URL (optional)
    """
    notification_manager = get_notification_manager()
    
    await notification_manager.send_notification({
        "type": "document_ready",
        "data": {
            "id": str(document.id),
            "title": title or document.title,
            "url": url or document.url,
            "ai_is_about": document.ai_is_about,
            "ai_bullet_points": document.ai_bullet_points,
            "created_at": document.created_at.isoformat() if document.created_at else None,
            "updated_at": document.updated_at.isoformat() if document.updated_at else None
        }
    }, user_id)
    
    logger.info(f"Sent document_ready notification for document {document.id} to user {user_id}")


async def _process_document_content(
    document_id: str,
    title: Optional[str],
    url: Optional[str],
    user_id: Optional[str] = None
):
    """
    Background task to process document content for summarization and bullet points
    
    Args:
        document_id: ID of the document to process
        title: Document title
        url: Document URL
        user_id: User ID for WebSocket notifications
    """
    notification_manager = get_notification_manager()
    
    try:
        logger.info(f"Starting content processing for document {document_id}")
        
        # Get database session
        session_gen = get_session()
        session = await session_gen.__anext__()
        
        # Send initial progress update
        if user_id:
            await notification_manager.send_notification({
                "type": "progress_percentage",
                "data": 10
            }, user_id)
        
        # Convert document_id to int if it's a string (Document.id is an integer)
        doc_id = int(document_id) if isinstance(document_id, str) else document_id
        
        # Get the document
        result = await session.execute(
            select(Document).where(Document.id == doc_id)
        )
        document = result.scalar_one_or_none()
        
        if not document:
            logger.error(f"Document {doc_id} not found")
            if user_id:
                await notification_manager.send_notification({
                    "type": "error",
                    "data": "Document not found"
                }, user_id)
            return
        
        # Check if content is NOT_AVAILABLE, empty, or unavailable
        content_unavailable = False
        
        # Check content_type
        if document.content_type in ["not_available", "fetch_failed"]:
            content_unavailable = True
        
        # Check if content is empty
        if not document.content or not document.content.strip():
            content_unavailable = True
        
        # Check content_availability metadata
        if document.document_metadata and document.document_metadata.get('content_availability'):
            content_status = document.document_metadata['content_availability']
            if not content_status.get('content_available', True):
                content_unavailable = True
            elif content_status.get('content_status') == 'unavailable':
                content_unavailable = True
        
        if content_unavailable:
            logger.info(f"Skipping content analysis for document {doc_id} - content is NOT_AVAILABLE, empty, or unavailable")
            
            # Mark as processed without AI analysis
            document.ai_is_about = "Content not available for analysis"
            document.ai_bullet_points = []
            document.updated_at = datetime.now()
            await session.commit()
            await session.refresh(document)
            
            if user_id:
                await notification_manager.send_notification({
                    "type": "document_ready",
                    "data": {
                        "bookmark_id": title,
                        "document_id": document.id,
                        "status": "not_available"
                    }
                }, user_id)
            
            await session.close()
            return
        
        # Send progress update
        if user_id:
            await notification_manager.send_notification({
                "type": "progress_percentage",
                "data": 30
            }, user_id)
        
        # Get DSPy content service (NEW: using DSPy instead of old ContentAnalysisService)
        dspy_content_service = get_dspy_content_service()
        
        # Analyze the document content using DSPy
        logger.info(f"Analyzing document content with DSPy for {doc_id}")
        analysis_result = await dspy_content_service.analyze_document_content(
            content=document.content or "",
            title=title,
            url=url
        )
        
        # Send progress update
        if user_id:
            await notification_manager.send_notification({
                "type": "progress_percentage",
                "data": 80
            }, user_id)
        
        # Update document with DSPy analysis results
        document.ai_is_about = analysis_result['summary']
        document.ai_bullet_points = analysis_result['bullet_points']
        document.extracted_content = analysis_result['extracted_content']
        document.source_type = analysis_result['extracted_content']['source_type']
        document.updated_at = datetime.now()
        
        # Commit changes
        await session.commit()
        await session.refresh(document)
        
        logger.info(f"Successfully processed document {doc_id} with summary and bullet points")
        
        # Send completion update with document data
        if user_id:
            await _send_document_ready_message(document, user_id, title, url)
            
            # Send final progress
            await notification_manager.send_notification({
                "type": "progress_percentage",
                "data": 100
            }, user_id)
        
    except Exception as e:
        logger.error(f"Error processing document {document_id}: {str(e)}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        
        # Send error notification
        if user_id:
            await notification_manager.send_notification({
                "type": "error",
                "data": f"Error processing document: {str(e)}"
            }, user_id)
        
    finally:
        # Clean up session
        try:
            await session.close()
        except Exception as e:
            logger.error(f"Error closing session for document {document_id}: {str(e)}")
        
        # Don't re-raise to avoid breaking the background task


async def _process_document_entities(
    document_id: str,
    user_id: str
):
    """
    Background task to extract entities from document content using DSPy
    
    Args:
        document_id: ID of the document to process
        user_id: User ID for entity extraction
    """
    try:
        logger.info(f"Starting DSPy entity extraction for document {document_id}")
        
        # Get database session
        session_gen = get_session()
        session = await session_gen.__anext__()
        
        try:
            # Convert document_id to int if it's a string (Document.id is an integer)
            doc_id = int(document_id) if isinstance(document_id, str) else document_id
            
            # Get the document
            result = await session.execute(
                select(Document).where(Document.id == doc_id)
            )
            document = result.scalar_one_or_none()
            
            if not document:
                logger.warning(f"Document {doc_id} not found for entity extraction")
                return
            
            # Check if content is available
            content_unavailable = False
            
            # Check if content is empty
            if not document.content or not document.content.strip():
                content_unavailable = True
            
            # Check content_type
            if document.content_type in ["not_available", "fetch_failed"]:
                content_unavailable = True
            
            # Check content_availability metadata
            if document.document_metadata and document.document_metadata.get('content_availability'):
                content_status = document.document_metadata['content_availability']
                if not content_status.get('content_available', True):
                    content_unavailable = True
                elif content_status.get('content_status') == 'unavailable':
                    content_unavailable = True
            
            if content_unavailable:
                logger.info(f"Skipping entity extraction for document {doc_id} - content is NOT_AVAILABLE, empty, or unavailable")
                return
            
            # Get DSPy entity service
            dspy_entity_service = get_dspy_entity_service()
            
            # Extract entities using DSPy
            entities = await dspy_entity_service.extract_entities_from_content(
                content=document.content,
                document_id=doc_id
            )
            
            # Process and store entities using adapter
            adapter = DspyEntityAdapter(session)
            result = await adapter.process_document_entities(
                firebase_uid=user_id,
                document_id=doc_id,
                entities=entities
            )
            
            # Commit changes
            await session.commit()
            
            logger.info(f"DSPy entity extraction completed for document {doc_id}: {result.get('entities_processed', 0)} entities processed")
            
        finally:
            await session.close()
            
    except Exception as e:
        logger.error(f"Error in DSPy entity extraction for document {document_id}: {str(e)}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        
        # Don't re-raise to avoid breaking the background task


async def _process_html_content_to_document(
    bookmark_id: str,
    user_id: str,
    html_content: str,
    title: Optional[str],
    url: Optional[str]
):
    """
    Background task to process HTML content and create document
    
    Args:
        bookmark_id: ID of the bookmark to update
        user_id: User ID for document creation
        html_content: HTML content to process
        title: Document title
        url: Document URL
    """
    try:
        logger.info(f"Starting HTML content processing for bookmark {bookmark_id}")
        
        # Get database session
        session_gen = get_session()
        session = await session_gen.__anext__()
        
        try:
            # Get the bookmark
            result = await session.execute(
                select(Bookmark).where(Bookmark.id == bookmark_id)
            )
            bookmark = result.scalar_one_or_none()
            
            if not bookmark:
                logger.error(f"Bookmark {bookmark_id} not found for HTML processing")
                return
            
            # Check if bookmark already has a document
            if bookmark.document_id:
                logger.info(f"Bookmark {bookmark_id} already has document {bookmark.document_id}, using existing document")
                document = await session.get(Document, bookmark.document_id)
                if not document:
                    logger.error(f"Document {bookmark.document_id} not found for bookmark {bookmark_id}")
                    return
            else:
                # Check if document already exists for this URL
                if url:
                    result = await session.execute(
                        select(Document).where(
                            Document.url == url,
                            Document.user_id == user_id
                        )
                    )
                    existing_doc = result.scalar_one_or_none()
                    
                    if existing_doc:
                        logger.info(f"Document already exists for URL {url}, reusing existing document {existing_doc.id}")
                        document = existing_doc
                        # Update bookmark with existing document ID
                        bookmark.document_id = document.id
                        await session.commit()
                        await session.refresh(bookmark)
                    else:
                        # Create document from HTML content (no embeddings)
                        logger.info(f"Creating new document for bookmark {bookmark_id}")
                        document_service = DocumentService(session)
                        document = await document_service.create_document_from_content(
                            user_id=user_id,
                            content=html_content,
                            content_type="html",
                            title=title,
                            url=url
                        )
                        
                        if not document:
                            logger.error(f"Failed to create document from HTML content for bookmark {bookmark_id}")
                            bookmark.processing_status = "failed"
                            await session.commit()
                            return
                        
                        # Update bookmark with document ID
                        bookmark.document_id = document.id
                        await session.commit()
                        await session.refresh(bookmark)
                        logger.info(f"Successfully created document {document.id} from HTML content for bookmark {bookmark_id}")
                else:
                    # No URL provided, create new document
                    logger.info(f"Creating new document for bookmark {bookmark_id} (no URL)")
                    document_service = DocumentService(session)
                    document = await document_service.create_document_from_content(
                        user_id=user_id,
                        content=html_content,
                        content_type="html",
                        title=title,
                        url=url
                    )
                    
                    if not document:
                        logger.error(f"Failed to create document from HTML content for bookmark {bookmark_id}")
                        bookmark.processing_status = "failed"
                        await session.commit()
                        return
                    
                    # Update bookmark with document ID
                    bookmark.document_id = document.id
                    await session.commit()
                    await session.refresh(bookmark)
                    logger.info(f"Successfully created document {document.id} from HTML content for bookmark {bookmark_id}")
            
            # Update bookmark processing status
            bookmark.is_processed = True
            bookmark.processing_status = "completed"
            await session.commit()
            await session.refresh(bookmark)
            
            # Launch 3 independent background tasks
            logger.info(f"Launching 3 background tasks for document {document.id}")
            
            # Task 1: Summary & Bullet Points (critical for UX)
            create_task(_process_document_content(
                document.id, title, url, user_id
            ))
            
            # Task 2: Entity Extraction (for filtering)
            create_task(_process_document_entities(
                document.id, user_id
            ))
            
            # Task 3: Embedding Generation (for search)
            create_task(_process_document_embeddings(
                document.id
            ))
                
        finally:
            await session.close()
            
    except Exception as e:
        logger.error(f"Error processing HTML content for bookmark {bookmark_id}: {str(e)}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        
        # Don't re-raise to avoid breaking the background task


async def _process_document_embeddings(
    document_id: str
):
    """
    Background task to generate embeddings for document content
    
    Args:
        document_id: ID of the document to process
    """
    try:
        logger.info(f"Starting embedding generation for document {document_id}")
        
        # Get database session
        session_gen = get_session()
        session = await session_gen.__anext__()
        
        try:
            # Convert document_id to int if it's a string (Document.id is an integer)
            doc_id = int(document_id) if isinstance(document_id, str) else document_id
            
            # Get the document
            result = await session.execute(
                select(Document).where(Document.id == doc_id)
            )
            document = result.scalar_one_or_none()
            
            if not document:
                logger.error(f"Document {doc_id} not found for embedding generation")
                return
            
            if not document.content:
                logger.warning(f"Document {doc_id} has no content for embedding generation")
                return
            
            # Get embedding service
            embedding_service = get_embedding_service()
            
            # Generate and store embeddings in the Embedding table
            embedding_success = await embedding_service.generate_and_store_document_embeddings(
                session=session,
                document=document,
                user_id=document.user_id,
                force_regenerate=False
            )
            
            if embedding_success:
                logger.info(f"Successfully generated embeddings for document {document_id}")
                await session.commit()
            else:
                logger.warning(f"Failed to generate embeddings for document {document_id}")
                
        finally:
            await session.close()
            
    except Exception as e:
        logger.error(f"Error generating embeddings for document {document_id}: {str(e)}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        
        # Don't re-raise to avoid breaking the background task


async def _process_document_entities_batch(
    document_ids: List[str],
    user_id: str
):
    """
    Background task to extract entities from multiple documents
    
    Args:
        document_ids: List of document IDs to process
        user_id: User ID for entity extraction
    """
    try:
        logger.info(f"Starting batch entity extraction for {len(document_ids)} documents")
        
        # Get database session
        session_gen = get_session()
        session = await session_gen.__anext__()
        
        try:
            # Get entity extraction task manager
            task_manager = get_entity_extraction_task_manager()
            
            total_entities_processed = 0
            successful_docs = 0
            
            for document_id in document_ids:
                try:
                    # Convert document_id to int if it's a string (Document.id is an integer)
                    doc_id = int(document_id) if isinstance(document_id, str) else document_id
                    
                    # Get the document
                    result = await session.execute(
                        select(Document).where(Document.id == doc_id)
                    )
                    document = result.scalar_one_or_none()
                    
                    if not document or not document.content:
                        logger.warning(f"Document {doc_id} not found or has no content for entity extraction")
                        continue
                    
                    # Extract entities from document content
                    result = await task_manager.extract_entities_async(
                        firebase_uid=user_id,
                        document_id=document.id,  # Use document.id directly (already a UUID)
                        content=document.content
                    )
                    
                    entities_processed = result.get('entities_processed', 0)
                    total_entities_processed += entities_processed
                    successful_docs += 1
                    
                    logger.info(f"Entity extraction completed for document {doc_id}: {entities_processed} entities processed")
                    
                except Exception as e:
                    logger.error(f"Error processing document {document_id} in batch: {str(e)}")
                    continue
            
            logger.info(f"Batch entity extraction completed: {successful_docs}/{len(document_ids)} documents processed, {total_entities_processed} total entities")
            
        finally:
            await session.close()
            
    except Exception as e:
        logger.error(f"Error in batch entity extraction: {str(e)}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")


async def _process_document_embeddings_batch(
    document_ids: List[str],
    user_id: str
):
    """
    Background task to generate embeddings for multiple documents
    
    Args:
        document_ids: List of document IDs to process
        user_id: User ID for embedding generation
    """
    try:
        logger.info(f"Starting batch embedding generation for {len(document_ids)} documents")
        
        # Get database session
        session_gen = get_session()
        session = await session_gen.__anext__()
        
        try:
            # Get embedding service
            embedding_service = get_embedding_service()
            
            successful_docs = 0
            
            for document_id in document_ids:
                try:
                    # Convert document_id to int if it's a string (Document.id is an integer)
                    doc_id = int(document_id) if isinstance(document_id, str) else document_id
                    
                    # Get the document
                    result = await session.execute(
                        select(Document).where(Document.id == doc_id)
                    )
                    document = result.scalar_one_or_none()
                    
                    if not document:
                        logger.warning(f"Document {doc_id} not found for embedding generation")
                        continue
                    
                    if not document.content:
                        logger.warning(f"Document {doc_id} has no content for embedding generation")
                        continue
                    
                    # Generate and store embeddings in the Embedding table
                    embedding_success = await embedding_service.generate_and_store_document_embeddings(
                        session=session,
                        document=document,
                        user_id=user_id,
                        force_regenerate=False
                    )
                    
                    if embedding_success:
                        logger.info(f"Successfully generated embeddings for document {document_id}")
                        successful_docs += 1
                        await session.commit()
                    else:
                        logger.warning(f"Failed to generate embeddings for document {document_id}")
                        
                except Exception as e:
                    logger.error(f"Error processing document {document_id} in batch: {str(e)}")
                    continue
            
            logger.info(f"Batch embedding generation completed: {successful_docs}/{len(document_ids)} documents processed")
            
        finally:
            await session.close()
            
    except Exception as e:
        logger.error(f"Error in batch embedding generation: {str(e)}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")


router = APIRouter(prefix="/bookmarks", tags=["bookmarks"])

@router.post("/{bookmark_id}/re-analyze")
async def re_analyze_bookmark(
    bookmark_id: int,
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
            bookmark.document_id,
            bookmark.title,
            bookmark.url,
            user_context.user.id
        )
        
        # Add entity extraction as separate background task
        background_tasks.add_task(
            _process_document_entities,
            bookmark.document_id,
            user_context.user.id
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
    user_id: str
    document_id: Optional[int] = None

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
        
        document_service = DocumentService(session)
        
        # First, check for existing document by URL (not just bookmark)
        existing_document = await session.execute(
            select(Document).where(
                Document.url == bookmark_data.url,
                Document.user_id == user_context.user.id
            )
        )
        existing_document = existing_document.scalar_one_or_none()
        
        # Check for duplicate bookmark (same URL and user)
        existing_bookmark = await session.execute(
            select(Bookmark).where(
                Bookmark.url == bookmark_data.url,
                Bookmark.user_id == user_context.user.id
            )
        )
        existing_bookmark = existing_bookmark.scalar_one_or_none()
        
        # If both bookmark and document exist, check if update is needed
        if existing_bookmark and existing_document:
            # Prepare content for comparison
            new_raw_html = None
            if bookmark_data.content and bookmark_data.content.strip() and bookmark_data.content != "NOT_AVAILABLE":
                # If content is HTML, use it as raw_html
                if not _is_clean_text_content(bookmark_data.content):
                    new_raw_html = sanitize_content_for_db(bookmark_data.content)
            
            # Compare raw_html and description
            raw_html_changed = False
            description_changed = False
            
            if new_raw_html is not None:
                existing_raw_html = existing_document.raw_html or ""
                if new_raw_html != existing_raw_html:
                    raw_html_changed = True
                    logger.info(f"raw_html changed for document {existing_document.id}")
            
            new_description = bookmark_data.description or ""
            existing_description = existing_bookmark.description or ""
            if new_description != existing_description:
                description_changed = True
                logger.info(f"description changed for bookmark {existing_bookmark.id}")
            
            # If nothing changed, return "bookmark exists"
            if not raw_html_changed and not description_changed:
                logger.info(f"Bookmark and document exist with same content for URL: {bookmark_data.url}, returning existing bookmark")
                
                # Refresh to ensure all attributes are loaded
                await session.refresh(existing_bookmark)
                await session.refresh(existing_document)
                
                # Still check if document needs AI processing
                if existing_document.ai_is_about is None or existing_document.ai_bullet_points is None:
                    background_tasks.add_task(
                        _process_document_content,
                        existing_document.id,
                        existing_bookmark.title,
                        existing_bookmark.url,
                        user_context.user.id
                    )
                    background_tasks.add_task(
                        _process_document_entities,
                        existing_document.id,
                        user_context.user.id
                    )
                    background_tasks.add_task(
                        _process_document_embeddings,
                        existing_document.id
                    )
                elif existing_document.ai_is_about and existing_document.ai_bullet_points:
                    await _send_document_ready_message(
                        existing_document, 
                        user_context.user.id, 
                        existing_bookmark.title, 
                        existing_bookmark.url
                    )
                
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
            
            # If something changed, update the existing bookmark and document
            logger.info(f"Updating existing bookmark {existing_bookmark.id} and document {existing_document.id} with new content")
            
            # Update bookmark
            if description_changed:
                existing_bookmark.description = bookmark_data.description
            if bookmark_data.title and bookmark_data.title != existing_bookmark.title:
                existing_bookmark.title = bookmark_data.title
            if bookmark_data.metadata:
                existing_bookmark.bookmark_metadata = bookmark_data.metadata
            existing_bookmark.updated_at = datetime.now()
            
            # Update document
            if raw_html_changed:
                existing_document.raw_html = new_raw_html
                # Also update content if we have it
                if bookmark_data.content and bookmark_data.content.strip():
                    existing_document.content = sanitize_content_for_db(bookmark_data.content)
                existing_document.updated_at = datetime.now()
                # Reset AI processing if content changed
                if existing_document.ai_is_about or existing_document.ai_bullet_points:
                    existing_document.ai_is_about = None
                    existing_document.ai_bullet_points = []
            
            await session.commit()
            await session.refresh(existing_bookmark)
            await session.refresh(existing_document)
            
            # Trigger background processing if content was updated
            if raw_html_changed:
                background_tasks.add_task(
                    _process_document_content,
                    existing_document.id,
                    existing_bookmark.title,
                    existing_bookmark.url,
                    user_context.user.id
                )
                background_tasks.add_task(
                    _process_document_entities,
                    existing_document.id,
                    user_context.user.id
                )
                background_tasks.add_task(
                    _process_document_embeddings,
                    existing_document.id
                )
            
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
        
        # If document exists but no bookmark, create bookmark linked to existing document
        if existing_document and not existing_bookmark:
            logger.info(f"Document exists for URL {bookmark_data.url} but no bookmark, creating bookmark linked to document {existing_document.id}")
            
            # Create bookmark linked to existing document
            bookmark = Bookmark(
                url=bookmark_data.url,
                title=bookmark_data.title or existing_document.title or "Untitled",
                description=bookmark_data.description,
                content=sanitize_content_for_db(bookmark_data.content) if bookmark_data.content else None,
                bookmark_metadata=bookmark_data.metadata or {},
                user_id=user_context.user.id,
                document_id=existing_document.id,
                is_processed=True,
                processing_status="completed" if (existing_document.ai_is_about and existing_document.ai_bullet_points) else "pending"
            )
            
            session.add(bookmark)
            await session.commit()
            await session.refresh(bookmark)
            
            # If document needs AI processing, trigger it
            if existing_document.ai_is_about is None or existing_document.ai_bullet_points is None:
                background_tasks.add_task(
                    _process_document_content,
                    existing_document.id,
                    bookmark.title,
                    bookmark.url,
                    user_context.user.id
                )
                background_tasks.add_task(
                    _process_document_entities,
                    existing_document.id,
                    user_context.user.id
                )
                background_tasks.add_task(
                    _process_document_embeddings,
                    existing_document.id
                )
            elif existing_document.ai_is_about and existing_document.ai_bullet_points:
                await _send_document_ready_message(
                    existing_document, 
                    user_context.user.id, 
                    bookmark.title, 
                    bookmark.url
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
                user_id=bookmark.user_id,
                document_id=bookmark.document_id
            )
        
        # If only bookmark exists but no document, handle it
        if existing_bookmark:
            ## Get the document, and if it doesn't have AI content, re-analyze it
            document = await document_service.get_document_by_id(
                user_id=user_context.user.id,
                document_id=existing_bookmark.document_id
            )
            if document is not None and (document.ai_is_about is None or document.ai_bullet_points is None):
                background_tasks.add_task(
                    _process_document_content,
                    document.id,
                    existing_bookmark.title,
                    existing_bookmark.url,
                    user_context.user.id
                )
                # Add entity extraction as separate background task
                background_tasks.add_task(
                    _process_document_entities,
                    document.id,
                    user_context.user.id
                )
                # Add embedding generation as separate background task
                background_tasks.add_task(
                    _process_document_embeddings,
                    document.id
                )
            elif document is None:
                # Bookmark exists but no document - create document and process it
                logger.info(f"Bookmark {existing_bookmark.id} exists but has no document, creating document")
                
                # Create document from bookmark data
                document = await document_service.create_document_from_content(
                    user_id=user_context.user.id,
                    content=existing_bookmark.content or "",
                    content_type="html",
                    title=existing_bookmark.title,
                    url=existing_bookmark.url
                )
                
                if document:
                    # Update bookmark with document ID
                    existing_bookmark.document_id = document.id
                    await session.commit()
                    
                    # Launch 3 background tasks for the new document
                    background_tasks.add_task(
                        _process_document_content,
                        document.id,
                        existing_bookmark.title,
                        existing_bookmark.url,
                        user_context.user.id
                    )
                    background_tasks.add_task(
                        _process_document_entities,
                        document.id,
                        user_context.user.id
                    )
                    background_tasks.add_task(
                        _process_document_embeddings,
                        document.id
                    )
                    
                    logger.info(f"Created document {document.id} for existing bookmark {existing_bookmark.id}")
                else:
                    logger.error(f"Failed to create document for existing bookmark {existing_bookmark.id}")
                    
            elif document is not None and document.ai_is_about and document.ai_bullet_points:
                # Document already has AI content, broadcast it immediately
                await _send_document_ready_message(
                    document, 
                    user_context.user.id, 
                    existing_bookmark.title, 
                    existing_bookmark.url
                )
                
                logger.info(f"Broadcasted existing document {document.id} for duplicate bookmark")

            logger.info(f"Duplicate bookmark found for URL: {bookmark_data.url}, returning existing bookmark")
            
            # Refresh bookmark to ensure all attributes are loaded
            await session.refresh(existing_bookmark)
            
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
        
        # Basic URL validation
        if not bookmark_data.url or not bookmark_data.url.startswith(('http://', 'https://')):
            logger.warning(f"Invalid URL provided: {bookmark_data.url}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid URL provided"
            )
        
        # Check if we have content provided or need to fetch HTML
        _doc = None
        
        # Normalize content - treat empty/whitespace as None
        content_provided = bookmark_data.content and bookmark_data.content.strip()
        
        # Handle NOT_AVAILABLE content case - create bookmark and document without AI analysis
        if bookmark_data.content == "NOT_AVAILABLE":
            logger.info(f"Content NOT_AVAILABLE for URL: {bookmark_data.url}, creating bookmark and document without AI analysis")
            
            # Check if document already exists for this URL
            if existing_document:
                logger.info(f"Document already exists for URL: {bookmark_data.url}, reusing existing document {existing_document.id}")
                _doc = existing_document
            else:
                # Create document without content for NOT_AVAILABLE case
                _doc = await document_service.create_document_from_content(
                    user_id=user_context.user.id,
                    content="",  # Empty content
                    content_type="not_available",
                    title=bookmark_data.title,
                    url=bookmark_data.url
                )
                
                if _doc:
                    logger.info(f"Created document {_doc.id} for NOT_AVAILABLE content")
                else:
                    logger.error(f"Failed to create document for NOT_AVAILABLE content")
        
        elif content_provided and _is_clean_text_content(bookmark_data.content):
            logger.info(f"Processing clean text content for URL: {bookmark_data.url}")
            _doc = await _create_document_from_clean_text(
                bookmark_data, user_context, session
            )
            logger.info(f"Document created from clean text: {_doc.id if _doc else 'None'}")
            
            # If document was created but has no raw_html and we have a URL, try to fetch content
            if _doc and not _doc.raw_html and _doc.url:
                logger.info(f"Document {_doc.id} created from clean text but has no raw_html, attempting to fetch from URL")
                try:
                    updated_doc = await document_service.fetch_and_update_document(
                        user_id=user_context.user.id,
                        document_id=str(_doc.id)
                    )
                    if updated_doc:
                        _doc = updated_doc
                        logger.info(f"Successfully fetched content for document {_doc.id}")
                except Exception as e:
                    logger.warning(f"Failed to fetch content for document {_doc.id}: {e}")
                    # Continue with existing document even if fetch failed
        elif content_provided:
            logger.info(f"Processing HTML content provided by client for URL: {bookmark_data.url}")
            
            # Sanitize content once for both bookmark and document creation
            sanitized_content = sanitize_content_for_db(bookmark_data.content)
            
            # Create bookmark first without document
            bookmark = Bookmark(
                url=bookmark_data.url,
                title=bookmark_data.title,
                description=bookmark_data.description,
                content=sanitized_content,  # Use sanitized content
                bookmark_metadata=bookmark_data.metadata,  # Fixed: use 'metadata' not 'bookmark_metadata'
                user_id=user_context.user.id,
                is_processed=False,
                processing_status="pending_html_processing"
            )
            
            session.add(bookmark)
            await session.commit()
            await session.refresh(bookmark)
            
            # Process HTML content in background task using sanitized content
            background_tasks.add_task(
                _process_html_content_to_document,
                bookmark.id,
                user_context.user.id,
                sanitized_content,  # Use sanitized content instead of original
                bookmark_data.title,
                bookmark_data.url
            )
            
            logger.info(f"Bookmark created with HTML content, processing in background: {bookmark.id}")
            
            # Return bookmark response immediately
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
                user_id=bookmark.user_id,
                document_id=bookmark.document_id  # Will be None initially, updated in background task
            )
        else:
            # No content provided (iPhone app case) - fetch content from URL
            logger.info(f"No content provided for URL: {bookmark_data.url}, fetching HTML content")
            document_service = DocumentService(session)
            
            # Check if document already exists for this URL
            if existing_document:
                logger.info(f"Document already exists for URL: {bookmark_data.url}, reusing existing document {existing_document.id}")
                _doc = existing_document
            else:
                try:
                    _doc = await document_service.create_document_from_url(
                        user_id=user_context.user.id,
                        url=bookmark_data.url,
                        title=bookmark_data.title
                    )
                    logger.info(f"Document created from URL fetch: {_doc.id if _doc else 'None'}")
                    
                    # Log content availability status if available
                    if _doc and _doc.document_metadata and _doc.document_metadata.get('content_availability'):
                        content_status = _doc.document_metadata['content_availability']
                        logger.info(
                            f"Document {_doc.id} content status: {content_status.get('content_status')} "
                            f"(available: {content_status.get('content_available')}, "
                            f"issues: {content_status.get('issues')})"
                        )
                except Exception as e:
                    logger.warning(f"Failed to create document from URL {bookmark_data.url}: {e}")
                    # Don't raise exception - create document without content instead
                    # This allows the bookmark to be created even if fetch fails
                    try:
                        _doc = await document_service.create_document_from_content(
                            user_id=user_context.user.id,
                            content="",  # Empty content
                            content_type="fetch_failed",
                            title=bookmark_data.title,
                            url=bookmark_data.url
                        )
                        if _doc and _doc.document_metadata is None:
                            _doc.document_metadata = {}
                        _doc.document_metadata.update({
                            'fetch_error': str(e),
                            'content_availability': {
                                'status': 'unavailable',
                                'content_available': False,
                                'content_status': 'unavailable',
                                'issues': ['fetch_failed'],
                            }
                        })
                        await session.commit()
                        await session.refresh(_doc)
                        logger.info(f"Created document {_doc.id} without content due to fetch failure")
                    except Exception as create_error:
                        logger.error(f"Failed to create document after fetch failure: {create_error}")
                        raise HTTPException(
                            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail="Unable to process the provided URL"
                        )
        
        logger.info(f"Final document status: {_doc.id if _doc else 'None'}")
        
        # Create bookmark record
        bookmark = Bookmark(
            url=bookmark_data.url,
            title=bookmark_data.title or "Untitled",
            description=bookmark_data.description,
            content=sanitize_content_for_db(bookmark_data.content),
            bookmark_metadata=bookmark_data.metadata or {},
            user_id=user_context.user.id,
            document_id=_doc.id if _doc else None
        )
        
        # Save bookmark to database
        session.add(bookmark)
        await session.commit()
        await session.refresh(bookmark)
        
        # Skip AI processing for NOT_AVAILABLE content or unavailable content
        if bookmark_data.content == "NOT_AVAILABLE":
            logger.info(f"Skipping AI processing for NOT_AVAILABLE content - bookmark {bookmark.id} created with document {_doc.id if _doc else 'None'}")
        elif _doc is not None:
            # Check if content is available before triggering background tasks
            content_available = True
            if _doc.document_metadata and _doc.document_metadata.get('content_availability'):
                content_status = _doc.document_metadata['content_availability']
                content_available = content_status.get('content_available', True)
                content_status_value = content_status.get('content_status', 'unknown')
                
                if not content_available or content_status_value == 'unavailable':
                    logger.info(
                        f"Skipping AI processing for document {_doc.id} - "
                        f"content status: {content_status_value}, "
                        f"available: {content_available}"
                    )
                    content_available = False
            
            # Also check if document has actual content
            if content_available and (not _doc.content or not _doc.content.strip()):
                logger.info(f"Skipping AI processing for document {_doc.id} - no content available")
                content_available = False
            
            # Only trigger background tasks if content is available
            if content_available and (_doc.ai_is_about is None or _doc.ai_bullet_points is None):
                # Start background processing tasks
                background_tasks.add_task(
                    _process_document_content,
                    _doc.id,
                    bookmark.title,
                    bookmark.url,
                    user_context.user.id
                )
                
                # Add entity extraction as separate background task
                background_tasks.add_task(
                    _process_document_entities,
                    _doc.id,
                    user_context.user.id
                )
            
            # Find documents without embeddings
            # Legacy embedding handler call removed - using modern services instead
        
        # Return bookmark response
        processing_status = "not_available" if bookmark_data.content == "NOT_AVAILABLE" else ("pending" if _doc else "not_processed")
        
        return BookmarkResponse(
            id=bookmark.id,
            url=bookmark.url,
            title=bookmark.title,
            description=bookmark.description,
            content=bookmark.content,
            bookmark_metadata=bookmark.bookmark_metadata,
            is_processed=_doc is not None,
            processing_status=processing_status,
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
                user_id=bm.user_id,
                document_id=bm.document_id  # Include document_id for relationship tracking
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
            user_id=bookmark.user_id,
            document_id=bookmark.document_id
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
            user_id=updated_bookmark.user_id,
            document_id=updated_bookmark.document_id
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
                user_id=bm.user_id,
                document_id=bm.document_id
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
        content=sanitize_content_for_db(bookmark_data.content),
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


# Legacy _create_document_from_page function removed - using DocumentService instead
