"""
API routes for document management
"""

from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, status, Query, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.core.user_context import get_active_user_context, UserContext
from app.db.database import get_session
from app.services.document_service import DocumentService
from app.api.models.document_models import (
    DocumentCreateRequest,
    DocumentResponse,
    DocumentListResponse,
    DocumentUpdateRequest,
    DocumentProcessingStatusResponse,
    DocumentContentResponse,
    EntityTreeResponse
)
from app.api.errors import NotFoundError, ValidationError
from app.utils.logging import get_logger
from app.models import Document
from app.api.routes.bookmarks import (
    _process_document_content,
    _process_document_entities,
    _process_document_content_and_entities,
    _process_document_embeddings,
    _fetch_url_and_process_document,
)

router = APIRouter(prefix="/documents", tags=["documents"])

logger = get_logger(__name__)


@router.post("/", response_model=DocumentResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_document(
    request: DocumentCreateRequest,
    background_tasks: BackgroundTasks,
    user_context: UserContext = Depends(get_active_user_context),
    session: AsyncSession = Depends(get_session)
):
    """
    Create a new document from URL or direct content.

    Returns **202 Accepted** immediately. AI extraction (summary, entities,
    embeddings) always runs in the background. Poll
    `GET /documents/{id}/status` or subscribe to WebSocket notifications
    to know when processing is complete.

    Content types:
    - **URL**: stub document created instantly; content fetched + processed in background.
    - **HTML / Text**: document with content created instantly; AI extraction runs in background.
    """
    try:
        document_service = DocumentService(session)

        if request.content and request.content_type in ['html', 'text']:
            # Content provided — create document immediately, schedule AI extraction
            document = await document_service.create_document_from_content(
                user_id=user_context.user_id,
                content=request.content,
                content_type=request.content_type,
                title=request.title,
                url=str(request.url) if request.url else None,
            )
            background_tasks.add_task(
                _process_document_content_and_entities,
                document.id,
                document.title,
                document.url,
                user_context.user_id,
            )
            background_tasks.add_task(_process_document_embeddings, document.id)

        elif request.raw_html:
            # Legacy raw_html field — same as HTML path
            document = await document_service.create_document(
                user_id=user_context.user_id,
                url=str(request.url) if request.url else None,
                title=request.title or "Untitled",
                raw_html=request.raw_html,
                content_source="html",
            )
            background_tasks.add_task(
                _process_document_content_and_entities,
                document.id,
                document.title,
                document.url,
                user_context.user_id,
            )
            background_tasks.add_task(_process_document_embeddings, document.id)

        elif request.url:
            # URL only — create stub immediately, fetch + process in background
            document = await document_service.create_document_from_content(
                user_id=user_context.user_id,
                content="",
                content_type="url",
                title=request.title or "Processing…",
                url=str(request.url),
            )
            background_tasks.add_task(
                _fetch_url_and_process_document,
                document.id,
                document.title,
                str(request.url),
                user_context.user_id,
            )

        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Either URL or content must be provided",
            )

        return DocumentResponse.model_validate(document)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create document: {str(e)}",
        )


@router.get("/", response_model=DocumentListResponse)
async def get_documents(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Number of documents per page"),
    user_context: UserContext = Depends(get_active_user_context),
    session: AsyncSession = Depends(get_session)
):
    """Get paginated list of user documents"""
    
    try:
        document_service = DocumentService(session)
        
        documents, total = await document_service.get_user_documents(
            user_id=user_context.user_id,
            page=page,
            page_size=page_size
        )
        
        total_pages = (total + page_size - 1) // page_size
        
        return DocumentListResponse(
            documents=[DocumentResponse.model_validate(doc) for doc in documents],
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages
        )
        
    except Exception as e:
        from app.core.config import settings
        if settings.DISABLE_AUTH:
            logger.warning(f"Database error in get_documents (No-Auth mode): {e}")
            return DocumentListResponse(
                documents=[],
                total=0,
                page=page,
                page_size=page_size,
                total_pages=0
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve documents: {str(e)}"
        )


@router.get("/all", response_model=List[DocumentResponse])
async def get_all_documents(
    user_context: UserContext = Depends(get_active_user_context),
    session: AsyncSession = Depends(get_session)
):
    """Get all documents for the user"""
    
    try:
        document_service = DocumentService(session)
        
        documents = await document_service.get_user_documents_all(
            user_id=user_context.user_id
        )
        
        return [DocumentResponse.model_validate(doc) for doc in documents]
        
    except Exception as e:
        from app.core.config import settings
        if settings.DISABLE_AUTH:
            logger.warning(f"Database error in get_all_documents (No-Auth mode): {e}")
            return []
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve all documents: {str(e)}"
        )


@router.get("/search", response_model=DocumentListResponse)
async def search_documents(
    query: str = Query(..., description="Search query text"),
    limit: int = Query(20, ge=1, le=100, description="Maximum number of results"),
    similarity_threshold: float = Query(0.6, ge=0.0, le=1.0, description="Minimum similarity score (0.0-1.0)"),
    user_context: UserContext = Depends(get_active_user_context),
    session: AsyncSession = Depends(get_session)
):
    """
    Search documents using embedding-based semantic search.
    
    This endpoint uses vector embeddings to find documents semantically related to the query text.
    Results are ranked by similarity score and returned in the same format as the regular document list.
    
    **Query Parameters:**
    - `query` (required): The search text to find related documents
    - `limit` (optional, default=20): Maximum number of results to return (1-100)
    - `similarity_threshold` (optional, default=0.6): Minimum similarity score (0.0-1.0)
    
    **Response:**
    Returns a DocumentListResponse with documents ranked by semantic similarity to the query.
    """
    
    try:
        from app.services.embedding_service import get_embedding_service
        
        document_service = DocumentService(session)
        embedding_service = get_embedding_service()
        
        # Use the existing method that searches embeddings and returns documents
        documents = await document_service.get_relevant_documents_for_chat(
            user_id=user_context.user_id,
            query=query,
            scope_type="all_library",
            scope_id=None,
            limit=limit,
            similarity_threshold=similarity_threshold
        )
        
        # Create response with same structure as get_documents
        return DocumentListResponse(
            documents=[DocumentResponse.model_validate(doc) for doc in documents],
            total=len(documents),
            page=1,
            page_size=len(documents),
            total_pages=1
        )
        
    except Exception as e:
        logger.error(f"Error searching documents: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to search documents: {str(e)}"
        )


@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: int,  # Document ID is now int
    user_context: UserContext = Depends(get_active_user_context),
    session: AsyncSession = Depends(get_session)
):
    """Get a specific document by ID"""
    
    try:
        document_service = DocumentService(session)
        
        document = await document_service.get_document_by_id(
            user_id=user_context.user_id,
            document_id=document_id
        )
        
        if not document:
            raise NotFoundError(f"Document {document_id} not found")
        
        return DocumentResponse.model_validate(document)
        
    except NotFoundError:
        raise
    except Exception as e:
        logger.error(f"Failed to retrieve document: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve document: {str(e)}"
        )


@router.get("/{document_id}/status", response_model=DocumentProcessingStatusResponse)
async def get_document_status(
    document_id: int,
    user_context: UserContext = Depends(get_active_user_context),
    session: AsyncSession = Depends(get_session)
):
    """
    Lightweight polling endpoint for document processing state.

    Returns one of:
    - `"processing"` — AI extraction is still running (ai_markdown_content not yet populated)
    - `"ready"` — AI extraction complete (ai_markdown_content and ai_is_about populated)
    - `"failed"` — URL fetch or processing failed (check document_metadata for details)
    """
    try:
        document_service = DocumentService(session)
        document = await document_service.get_document_by_id(
            user_id=user_context.user_id,
            document_id=document_id,
        )
        if not document:
            raise NotFoundError(f"Document {document_id} not found")

        if document.document_metadata and document.document_metadata.get("fetch_error"):
            derived_status = "failed"
        elif document.ai_markdown_content and document.ai_markdown_content.strip():
            derived_status = "ready"
        else:
            derived_status = "processing"

        return DocumentProcessingStatusResponse(
            id=document.id,
            status=derived_status,
            updated_at=document.updated_at,
            document_metadata=document.document_metadata,
        )

    except NotFoundError:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve document status: {str(e)}",
        )


@router.put("/{document_id}", response_model=DocumentResponse)
async def update_document(
    document_id: int,  # Integer ID as stored in database
    request: DocumentUpdateRequest,
    user_context: UserContext = Depends(get_active_user_context),
    session: AsyncSession = Depends(get_session)
):
    """Update document metadata"""
    
    try:
        document_service = DocumentService(session)
        
        # Convert request to dict, excluding None values
        update_data = request.dict(exclude_unset=True)
        
        document = await document_service.update_document(
            user_id=user_context.user_id,
            document_id=document_id,
            **update_data
        )
        
        if not document:
            raise NotFoundError(f"Document {document_id} not found")
        
        return DocumentResponse.model_validate(document)
        
    except NotFoundError:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update document: {str(e)}"
        )


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: int,  # Integer ID as stored in database
    user_context: UserContext = Depends(get_active_user_context),
    session: AsyncSession = Depends(get_session)
):
    """Delete a document"""
    
    try:
        document_service = DocumentService(session)
        
        success = await document_service.delete_document(
            user_id=user_context.user_id,
            document_id=document_id
        )
        
        if not success:
            raise NotFoundError(f"Document {document_id} not found")
        
    except NotFoundError:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete document: {str(e)}"
        )


@router.get("/url/{url:path}", response_model=List[DocumentResponse])
async def get_documents_by_url(
    url: str,
    user_context: UserContext = Depends(get_active_user_context),
    session: AsyncSession = Depends(get_session)
):
    """Get all documents for a specific URL"""
    
    try:
        document_service = DocumentService(session)
        
        documents = await document_service.get_documents_by_url(
            user_id=user_context.user_id,
            url=url
        )
        
        return [DocumentResponse.model_validate(doc) for doc in documents]
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve documents by URL: {str(e)}"
        )


@router.get("/{document_id}/content", response_model=DocumentContentResponse)
async def get_document_content(
    document_id: int,  # Document ID is now int
    user_context: UserContext = Depends(get_active_user_context),
    session: AsyncSession = Depends(get_session)
):
    """Get document content for analysis"""
    
    try:
        document_service = DocumentService(session)
        
        document = await document_service.get_document_by_id(
            user_id=user_context.user_id,
            document_id=document_id
        )
        
        if not document:
            raise NotFoundError(f"Document {document_id} not found")
        
        return DocumentContentResponse.model_validate(document)
        
    except NotFoundError:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve document content: {str(e)}"
        )


@router.patch("/{document_id}/metadata", response_model=DocumentResponse)
async def update_document_metadata(
    document_id: int,  # Integer ID as stored in database
    metadata_updates: dict,
    user_context: UserContext = Depends(get_active_user_context),
    session: AsyncSession = Depends(get_session)
):
    """Update document metadata"""
    
    try:
        document_service = DocumentService(session)
        
        document = await document_service.update_document_metadata(
            user_id=user_context.user_id,
            document_id=document_id,
            **metadata_updates
        )
        
        if not document:
            raise NotFoundError(f"Document {document_id} not found")
        
        return DocumentResponse.model_validate(document)
        
    except NotFoundError:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update document metadata: {str(e)}"
        )


@router.post("/{document_id}/fetch", response_model=DocumentResponse)
async def fetch_document_content(
    document_id: int,  # Integer ID as stored in database
    user_context: UserContext = Depends(get_active_user_context),
    session: AsyncSession = Depends(get_session)
):
    """Manually trigger content fetching for an existing document"""
    
    try:
        document_service = DocumentService(session)
        
        document = await document_service.fetch_and_update_document(
            user_id=user_context.user_id,
            document_id=document_id
        )
        
        if not document:
            raise NotFoundError(f"Document {document_id} not found")
        
        return DocumentResponse.model_validate(document)
        
    except NotFoundError:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch document content: {str(e)}"
        )


@router.post("/{document_id}/reprocess", response_model=DocumentResponse)
async def reprocess_document_content(
    document_id: int,
    refetch: bool = Query(False, description="Refetch content from the original URL before reprocessing"),
    background_tasks: BackgroundTasks = None,
    user_context: UserContext = Depends(get_active_user_context),
    session: AsyncSession = Depends(get_session)
):
    """
    Re-run content extraction, validation, embedding generation, AI summary, bullet points, and entity extraction for an existing document.
    """
    try:
        document_service = DocumentService(session)
        
        document = await document_service.reprocess_document_content(
            user_id=user_context.user_id,
            document_id=document_id,
            refetch_from_source=refetch
        )
        
        if not document:
            raise NotFoundError(f"Document {document_id} not found")
        
        # Trigger background tasks for AI-generated content (summary, bullet points, and entities)
        # These will regenerate the AI summary, bullet points, and extract entities
        if background_tasks:
            logger.info(f"Triggering background tasks for AI content regeneration for document {document_id}")
            
            # Task 1: Summary & Bullet Points
            background_tasks.add_task(
                _process_document_content,
                str(document_id),
                document.title,
                document.url,
                user_context.user_id
            )
            
            # Task 2: Entity Extraction
            background_tasks.add_task(
                _process_document_entities,
                str(document_id),
                user_context.user_id
            )
        
        return DocumentResponse.model_validate(document)
    
    except NotFoundError:
        raise
    except Exception as e:
        logger.error(f"Failed to reprocess document {document_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to reprocess document: {str(e)}"
        )


@router.get("/entities/tree", response_model=EntityTreeResponse)
async def get_entity_tree(
    user_context: UserContext = Depends(get_active_user_context),
    session: AsyncSession = Depends(get_session)
):
    """Get entity tree structure for filtering, grouped by entity type"""
    
    try:
        document_service = DocumentService(session)
        
        tree_data = await document_service.get_entity_tree(
            user_id=user_context.user_id
        )
        
        return EntityTreeResponse(tree=tree_data)
        
    except Exception as e:
        from app.core.config import settings
        if settings.DISABLE_AUTH:
            logger.warning(f"Database error in get_entity_tree (No-Auth mode): {e}")
            return EntityTreeResponse(tree=[])
        logger.error(f"Failed to retrieve entity tree: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve entity tree: {str(e)}"
        )


@router.post("/{document_id}/embed", response_model=DocumentResponse)
async def generate_document_embedding(
    document_id: int,  # Integer ID as stored in database
    user_context: UserContext = Depends(get_active_user_context),
    session: AsyncSession = Depends(get_session)
):
    """Generate embedding for a document and store in Embedding table"""
    
    try:
        from app.services.embedding_service import get_embedding_service
        
        embedding_service = get_embedding_service()
        
        # Get the document first
        document_service = DocumentService(session)
        document = await document_service.get_document_by_id(
            user_id=user_context.user_id,
            document_id=document_id
        )
        
        if not document:
            raise NotFoundError(f"Document {document_id} not found")
        
        # Generate and store embeddings in the Embedding table
        success = await embedding_service.generate_and_store_document_embeddings(
            session=session,
            document=document,
            user_id=user_context.user_id,
            force_regenerate=False
        )
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to generate document embedding"
            )
        
        await session.commit()
        
        return DocumentResponse.model_validate(document)
        
    except NotFoundError:
        raise
    except Exception as e:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate embedding: {str(e)}"
        )












