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
from asyncio import create_task
from app.db.database import get_session
from app.core.user_context import UserContext, get_authenticated_user_context, get_active_user_context
from app.services.bookmark_service import BookmarkService
from app.api.models.user_models import UserProfileResponse
from app.log import get_logger
from app.services.content_analysis_service import get_content_analysis_service
from app.models import Document, Bookmark
from app.services.document_service import DocumentService
from app.services.entity_extraction_task_manager import get_entity_extraction_task_manager
from app.services.embedding_service import get_embedding_service
from app.core.config import settings
from app.api.routes.websocket import get_connection_manager


logger = get_logger(__name__)

# Legacy embedding handler removed - using modern services instead


async def _send_document_ready_message(
    document: Document,
    user_id: str,
    title: Optional[str] = None,
    url: Optional[str] = None
) -> None:
    """
    Send a document_ready WebSocket message for a processed document.
    
    Args:
        document: The document to send
        user_id: User ID to send the message to
        title: Override title (optional)
        url: Override URL (optional)
    """
    ws_manager = get_connection_manager()
    
    await ws_manager.send_personal_message({
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
    
    logger.info(f"Sent document_ready message for document {document.id} to user {user_id}")


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
    ws_manager = get_connection_manager()
    
    try:
        logger.info(f"Starting content processing for document {document_id}")
        
        # Get database session
        session_gen = get_session()
        session = await session_gen.__anext__()
        
        # Send initial progress update
        if user_id:
            await ws_manager.send_personal_message({
                "type": "progress_percentage",
                "data": 10
            }, user_id)
        
        # Get the document
        result = await session.execute(
            select(Document).where(Document.id == document_id)
        )
        document = result.scalar_one_or_none()
        
        if not document:
            logger.error(f"Document {document_id} not found")
            if user_id:
                await ws_manager.send_personal_message({
                    "type": "error",
                    "data": "Document not found"
                }, user_id)
            return
        
        # Send progress update
        if user_id:
            await ws_manager.send_personal_message({
                "type": "progress_percentage",
                "data": 30
            }, user_id)
        
        # Get content analysis service
        content_analysis_service = get_content_analysis_service()
        
        # Analyze the document content
        logger.info(f"Analyzing document content for {document_id}")
        analysis_result = await content_analysis_service.analyze_document_content(
            content=document.content or "",
            title=title,
            url=url
        )
        
        # Send progress update
        if user_id:
            await ws_manager.send_personal_message({
                "type": "progress_percentage",
                "data": 80
            }, user_id)
        
        # Update document with analysis results
        document.ai_is_about = analysis_result['summary']
        document.ai_bullet_points = analysis_result['bullet_points']
        document.updated_at = datetime.now()
        
        # Commit changes
        await session.commit()
        await session.refresh(document)
        
        logger.info(f"Successfully processed document {document_id} with summary and bullet points")
        
        # Send completion update with document data
        if user_id:
            await _send_document_ready_message(document, user_id, title, url)
            
            # Send final progress
            await ws_manager.send_personal_message({
                "type": "progress_percentage",
                "data": 100
            }, user_id)
        
    except Exception as e:
        logger.error(f"Error processing document {document_id}: {str(e)}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        
        # Send error notification
        if user_id:
            await ws_manager.send_personal_message({
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
    Background task to extract entities from document content
    
    Args:
        document_id: ID of the document to process
        user_id: User ID for entity extraction
    """
    try:
        logger.info(f"Starting entity extraction for document {document_id}")
        
        # Get database session
        session_gen = get_session()
        session = await session_gen.__anext__()
        
        try:
            # Get the document
            result = await session.execute(
                select(Document).where(Document.id == document_id)
            )
            document = result.scalar_one_or_none()
            
            if not document or not document.content:
                logger.warning(f"Document {document_id} not found or has no content for entity extraction")
                return
            
            # Get entity extraction task manager
            task_manager = get_entity_extraction_task_manager()
            
            # Extract entities from document content
            result = await task_manager.extract_entities_async(
                firebase_uid=user_id,
                document_id=int(document_id),
                content=document.content
            )
            
            logger.info(f"Entity extraction completed for document {document_id}: {result.get('entities_processed', 0)} entities processed")
            
        finally:
            await session.close()
            
    except Exception as e:
        logger.error(f"Error in entity extraction for document {document_id}: {str(e)}")
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
            
            # Create document from HTML content (no embeddings)
            document_service = DocumentService(session)
            document = await document_service.create_document_from_content(
                user_id=user_id,
                content=html_content,
                content_type="html",
                title=title,
                url=url
            )
            
            if document:
                # Update bookmark with document ID
                bookmark.document_id = document.id
                bookmark.is_processed = True
                bookmark.processing_status = "completed"
                
                await session.commit()
                await session.refresh(bookmark)
                
                logger.info(f"Successfully created document {document.id} from HTML content for bookmark {bookmark_id}")
                
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
                
            else:
                logger.error(f"Failed to create document from HTML content for bookmark {bookmark_id}")
                bookmark.processing_status = "failed"
                await session.commit()
                
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
            # Get the document
            result = await session.execute(
                select(Document).where(Document.id == document_id)
            )
            document = result.scalar_one_or_none()
            
            if not document:
                logger.error(f"Document {document_id} not found for embedding generation")
                return
            
            if not document.content:
                logger.warning(f"Document {document_id} has no content for embedding generation")
                return
            
            # Get embedding service
            embedding_service = get_embedding_service()
            
            # Generate embeddings for the document
            embedding_success = await embedding_service.update_document_embedding(
                session=session,
                document_id=document.id,
                user_id=document.user_id,
                force_regenerate=False
            )
            
            if embedding_success:
                logger.info(f"Successfully generated embeddings for document {document_id}")
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
                    # Get the document
                    result = await session.execute(
                        select(Document).where(Document.id == document_id)
                    )
                    document = result.scalar_one_or_none()
                    
                    if not document or not document.content:
                        logger.warning(f"Document {document_id} not found or has no content for entity extraction")
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
                    
                    logger.info(f"Entity extraction completed for document {document_id}: {entities_processed} entities processed")
                    
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
                    # Get the document
                    result = await session.execute(
                        select(Document).where(Document.id == document_id)
                    )
                    document = result.scalar_one_or_none()
                    
                    if not document:
                        logger.warning(f"Document {document_id} not found for embedding generation")
                        continue
                    
                    if not document.content:
                        logger.warning(f"Document {document_id} has no content for embedding generation")
                        continue
                    
                    # Prepare enhanced content for embedding (chunk content and include metadata)
                    content_parts = []
                    
                    # Add authors if available
                    if document.authors and document.authors.strip():
                        content_parts.append(f"Authors: {document.authors.strip()}")
                    
                    # Add URL if available
                    if document.url and document.url.strip():
                        content_parts.append(f"URL: {document.url.strip()}")
                    
                    # Add description if available
                    if document.metadata_description and document.metadata_description.strip():
                        content_parts.append(f"Description: {document.metadata_description.strip()}")
                    
                    # Add site name if available
                    if document.site_name and document.site_name.strip():
                        content_parts.append(f"Site: {document.site_name.strip()}")
                    
                    # Chunk the main content
                    content = document.content.strip()
                    chunk_size = 1000  # Adjust as needed
                    content_chunks = [content[i:i+chunk_size] for i in range(0, len(content), chunk_size)]
                    
                    # Combine metadata and content chunks
                    all_content_parts = content_parts + content_chunks
                    enhanced_content = "\n\n".join(all_content_parts)
                    
                    # Temporarily update document content with enhanced version
                    original_content = document.content
                    document.content = enhanced_content
                    
                    try:
                        # Generate embeddings using the enhanced content
                        embedding_result = await embedding_service.generate_document_embedding(
                            document=document,
                            use_content=True,
                            use_title=True,
                            combine_strategy="title_content"
                        )
                        
                        if embedding_result.success:
                            # Save the embedding to database
                            embedding_success = await embedding_service.update_document_embedding(
                                session=session,
                                document_id=document.id,
                                user_id=user_id,
                                force_regenerate=True
                            )
                        else:
                            embedding_success = False
                            logger.warning(f"Failed to generate embedding for document {document_id}: {embedding_result.error}")
                    
                    finally:
                        # Restore original content
                        document.content = original_content
                    
                    if embedding_success:
                        logger.info(f"Successfully generated embeddings for document {document_id}")
                        successful_docs += 1
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
        
        if bookmark_data.content and _is_clean_text_content(bookmark_data.content):
            logger.info(f"Processing clean text content for URL: {bookmark_data.url}")
            _doc = await _create_document_from_clean_text(
                bookmark_data, user_context, session
            )
            logger.info(f"Document created from clean text: {_doc.id if _doc else 'None'}")
        elif bookmark_data.content:
            logger.info(f"Processing HTML content provided by client for URL: {bookmark_data.url}")
            
            # Create bookmark first without document
            bookmark = Bookmark(
                url=bookmark_data.url,
                title=bookmark_data.title,
                description=bookmark_data.description,
                content=bookmark_data.content,  # Store the HTML content
                bookmark_metadata=bookmark_data.metadata,  # Fixed: use 'metadata' not 'bookmark_metadata'
                user_id=user_context.user.id,
                is_processed=False,
                processing_status="pending_html_processing"
            )
            
            session.add(bookmark)
            await session.commit()
            await session.refresh(bookmark)
            
            # Process HTML content in background task
            background_tasks.add_task(
                _process_html_content_to_document,
                bookmark.id,
                user_context.user.id,
                bookmark_data.content,
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
            logger.info(f"No content provided, fetching HTML content for URL: {bookmark_data.url}")
            # Create document by fetching URL content
            document_service = DocumentService(session)
            
            try:
                _doc = await document_service.create_document_from_url(
                    user_id=user_context.user.id,
                    url=bookmark_data.url,
                    title=bookmark_data.title
                )
                logger.info(f"Document created from URL fetch: {_doc.id if _doc else 'None'}")
            except Exception as e:
                logger.warning(f"Failed to create document from URL {bookmark_data.url}: {e}")
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Unable to process the provided URL"
                )
        
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


# Legacy _create_document_from_page function removed - using DocumentService instead
