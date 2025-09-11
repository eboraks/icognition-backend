"""
API routes for document management
"""

from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, status, Query, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.user_context import get_active_user_context, UserContext
from app.db.database import get_session
from app.services.document_service import DocumentService
from app.api.models.document_models import (
    DocumentCreateRequest,
    DocumentResponse,
    DocumentListResponse,
    DocumentUpdateRequest,
    DocumentProcessingStatusResponse,
    DocumentContentResponse
)
from app.api.errors import NotFoundError, ValidationError

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("/", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def create_document(
    request: DocumentCreateRequest,
    user_context: UserContext = Depends(get_active_user_context),
    session: AsyncSession = Depends(get_session)
):
    """
    Create a new document bookmark from URL or direct content.
    
    This endpoint supports three ways to create documents:
    
    1. **URL-based**: Provide a URL to fetch content from the web
    2. **HTML content**: Provide raw HTML content directly
    3. **Text content**: Provide plain text content directly
    
    **Request Body:**
    - `url` (optional): URL of the web page to bookmark
    - `title` (optional): Title of the document
    - `content` (optional): Direct content (HTML or text) from the user
    - `content_type` (default: "url"): Content source type - "url", "html", or "text"
    - `raw_html` (optional, deprecated): Legacy field for raw HTML content
    
    **Validation Rules:**
    - Either `url` or `content` must be provided
    - If `content_type` is not "url", then `content` is required
    - `content_type` must be one of: "url", "html", "text"
    
    **Examples:**
    
    URL-based document:
    ```json
    {
        "url": "https://example.com/article",
        "title": "My Article"
    }
    ```
    
    HTML content:
    ```json
    {
        "content": "<html><body><h1>Title</h1><p>Content here</p></body></html>",
        "content_type": "html",
        "title": "My Document"
    }
    ```
    
    Text content:
    ```json
    {
        "content": "This is plain text content",
        "content_type": "text",
        "title": "My Text Document"
    }
    ```
    
    **Response:**
    Returns the created document with processing status and metadata.
    """
    
    try:
        document_service = DocumentService(session)
        
        # Handle direct content submission
        if request.content and request.content_type in ['html', 'text']:
            document = await document_service.create_document_from_content(
                firebase_uid=user_context.firebase_uid,
                content=request.content,
                content_type=request.content_type,
                title=request.title,
                url=str(request.url) if request.url else None
            )
        # Handle legacy raw_html field (for backward compatibility)
        elif request.raw_html:
            document = await document_service.create_document(
                firebase_uid=user_context.firebase_uid,
                url=str(request.url) if request.url else None,
                title=request.title or "Untitled",
                raw_html=request.raw_html,
                content_source="html"
            )
        # Handle URL-based document creation
        elif request.url:
            document = await document_service.create_document_from_url(
                firebase_uid=user_context.firebase_uid,
                url=str(request.url),
                title=request.title
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Either URL or content must be provided"
            )
        
        return DocumentResponse.from_orm(document)
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create document: {str(e)}"
        )


@router.get("/", response_model=DocumentListResponse)
async def get_documents(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Number of documents per page"),
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by processing status"),
    user_context: UserContext = Depends(get_active_user_context),
    session: AsyncSession = Depends(get_session)
):
    """Get paginated list of user documents"""
    
    try:
        document_service = DocumentService(session)
        
        documents, total = await document_service.get_user_documents(
            firebase_uid=user_context.firebase_uid,
            page=page,
            page_size=page_size,
            status=status_filter
        )
        
        total_pages = (total + page_size - 1) // page_size
        
        return DocumentListResponse(
            documents=[DocumentResponse.from_orm(doc) for doc in documents],
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve documents: {str(e)}"
        )


@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: int,
    user_context: UserContext = Depends(get_active_user_context),
    session: AsyncSession = Depends(get_session)
):
    """Get a specific document by ID"""
    
    try:
        document_service = DocumentService(session)
        
        document = await document_service.get_document_by_id(
            firebase_uid=user_context.firebase_uid,
            document_id=document_id
        )
        
        if not document:
            raise NotFoundError(f"Document {document_id} not found")
        
        return DocumentResponse.from_orm(document)
        
    except NotFoundError:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve document: {str(e)}"
        )


@router.put("/{document_id}", response_model=DocumentResponse)
async def update_document(
    document_id: int,
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
            firebase_uid=user_context.firebase_uid,
            document_id=document_id,
            **update_data
        )
        
        if not document:
            raise NotFoundError(f"Document {document_id} not found")
        
        return DocumentResponse.from_orm(document)
        
    except NotFoundError:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update document: {str(e)}"
        )


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: int,
    user_context: UserContext = Depends(get_active_user_context),
    session: AsyncSession = Depends(get_session)
):
    """Delete a document"""
    
    try:
        document_service = DocumentService(session)
        
        success = await document_service.delete_document(
            firebase_uid=user_context.firebase_uid,
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
            firebase_uid=user_context.firebase_uid,
            url=url
        )
        
        return [DocumentResponse.from_orm(doc) for doc in documents]
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve documents by URL: {str(e)}"
        )


@router.get("/status/{status}", response_model=List[DocumentResponse])
async def get_documents_by_status(
    status: str,
    user_context: UserContext = Depends(get_active_user_context),
    session: AsyncSession = Depends(get_session)
):
    """Get all documents with a specific processing status"""
    
    try:
        document_service = DocumentService(session)
        
        documents = await document_service.get_documents_by_status(
            firebase_uid=user_context.firebase_uid,
            status=status
        )
        
        return [DocumentResponse.from_orm(doc) for doc in documents]
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve documents by status: {str(e)}"
        )


@router.get("/{document_id}/content", response_model=DocumentContentResponse)
async def get_document_content(
    document_id: int,
    user_context: UserContext = Depends(get_active_user_context),
    session: AsyncSession = Depends(get_session)
):
    """Get document content for analysis"""
    
    try:
        document_service = DocumentService(session)
        
        document = await document_service.get_document_by_id(
            firebase_uid=user_context.firebase_uid,
            document_id=document_id
        )
        
        if not document:
            raise NotFoundError(f"Document {document_id} not found")
        
        return DocumentContentResponse.from_orm(document)
        
    except NotFoundError:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve document content: {str(e)}"
        )


@router.patch("/{document_id}/status", response_model=DocumentProcessingStatusResponse)
async def update_document_status(
    document_id: int,
    status: str,
    user_context: UserContext = Depends(get_active_user_context),
    session: AsyncSession = Depends(get_session)
):
    """Update document processing status"""
    
    try:
        document_service = DocumentService(session)
        
        document = await document_service.update_document_status(
            firebase_uid=user_context.firebase_uid,
            document_id=document_id,
            status=status
        )
        
        if not document:
            raise NotFoundError(f"Document {document_id} not found")
        
        return DocumentProcessingStatusResponse.from_orm(document)
        
    except NotFoundError:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update document status: {str(e)}"
        )


@router.post("/{document_id}/fetch", response_model=DocumentResponse)
async def fetch_document_content(
    document_id: int,
    user_context: UserContext = Depends(get_active_user_context),
    session: AsyncSession = Depends(get_session)
):
    """Manually trigger content fetching for an existing document"""
    
    try:
        document_service = DocumentService(session)
        
        document = await document_service.fetch_and_update_document(
            firebase_uid=user_context.firebase_uid,
            document_id=document_id
        )
        
        if not document:
            raise NotFoundError(f"Document {document_id} not found")
        
        return DocumentResponse.from_orm(document)
        
    except NotFoundError:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch document content: {str(e)}"
        )


@router.post("/{document_id}/embed", response_model=DocumentResponse)
async def generate_document_embedding(
    document_id: int,
    user_context: UserContext = Depends(get_active_user_context),
    session: AsyncSession = Depends(get_session)
):
    """Generate embedding for a document"""
    
    try:
        from app.services.embedding_service import get_embedding_service
        
        embedding_service = get_embedding_service()
        
        success = await embedding_service.update_document_embedding(
            session=session,
            document_id=document_id,
            user_id=user_context.user_id,
            force_regenerate=False
        )
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to generate document embedding"
            )
        
        # Get updated document
        document_service = DocumentService(session)
        document = await document_service.get_by_id(
            firebase_uid=user_context.firebase_uid,
            document_id=document_id
        )
        
        if not document:
            raise NotFoundError(f"Document {document_id} not found")
        
        return DocumentResponse.from_orm(document)
        
    except NotFoundError:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate embedding: {str(e)}"
        )


@router.post("/search/similar", response_model=List[DocumentResponse])
async def search_similar_documents(
    query: str,
    limit: int = 10,
    similarity_threshold: float = 0.7,
    user_context: UserContext = Depends(get_active_user_context),
    session: AsyncSession = Depends(get_session)
):
    """Search for documents similar to query text using vector similarity"""
    
    try:
        from app.services.embedding_service import get_embedding_service
        
        embedding_service = get_embedding_service()
        
        search_result = await embedding_service.search_similar_documents(
            session=session,
            query_text=query,
            user_id=user_context.user_id,
            limit=limit,
            similarity_threshold=similarity_threshold
        )
        
        if not search_result.success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Search failed: {search_result.error}"
            )
        
        # Get full documents for the results
        document_service = DocumentService(session)
        documents = []
        
        for similarity_result in search_result.results:
            document = await document_service.get_by_id(
                firebase_uid=user_context.firebase_uid,
                document_id=similarity_result.document_id
            )
            if document:
                documents.append(document)
        
        return [DocumentResponse.from_orm(doc) for doc in documents]
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to search similar documents: {str(e)}"
        )


@router.post("/batch/embeddings")
async def batch_update_embeddings(
    batch_size: int = 10,
    force_regenerate: bool = False,
    user_context: UserContext = Depends(get_active_user_context),
    session: AsyncSession = Depends(get_session)
):
    """Update embeddings for multiple documents in batch"""
    
    try:
        from app.services.embedding_service import get_embedding_service
        
        embedding_service = get_embedding_service()
        
        result = await embedding_service.batch_update_embeddings(
            session=session,
            user_id=user_context.user_id,
            batch_size=batch_size,
            force_regenerate=force_regenerate
        )
        
        return {
            "message": "Batch embedding update completed",
            "results": result
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update embeddings: {str(e)}"
        )


@router.get("/embeddings/stats")
async def get_embedding_statistics(
    user_context: UserContext = Depends(get_active_user_context),
    session: AsyncSession = Depends(get_session)
):
    """Get statistics about document embeddings"""
    
    try:
        from app.services.embedding_service import get_embedding_service
        
        embedding_service = get_embedding_service()
        
        stats = await embedding_service.get_embedding_statistics(
            session=session,
            user_id=user_context.user_id
        )
        
        return stats
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get embedding statistics: {str(e)}"
        )


@router.post("/{document_id}/validate", response_model=DocumentResponse)
async def validate_document_content(
    document_id: int,
    user_context: UserContext = Depends(get_active_user_context),
    session: AsyncSession = Depends(get_session)
):
    """Manually trigger content validation for an existing document"""
    
    try:
        document_service = DocumentService(session)
        
        # Get the document
        document = await document_service.get_by_id(
            firebase_uid=user_context.firebase_uid,
            document_id=document_id
        )
        
        if not document:
            raise NotFoundError(f"Document {document_id} not found")
        
        if not document.content:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Document has no content to validate"
            )
        
        # Validate the content
        await document_service._validate_document_content(document)
        
        # Commit changes
        await session.commit()
        await session.refresh(document)
        
        return DocumentResponse.from_orm(document)
        
    except NotFoundError:
        raise
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to validate document content: {str(e)}"
        )


@router.get("/{document_id}/validation-report")
async def get_document_validation_report(
    document_id: int,
    user_context: UserContext = Depends(get_active_user_context),
    session: AsyncSession = Depends(get_session)
):
    """Get detailed validation report for a document"""
    
    try:
        document_service = DocumentService(session)
        
        # Get the document
        document = await document_service.get_by_id(
            firebase_uid=user_context.firebase_uid,
            document_id=document_id
        )
        
        if not document:
            raise NotFoundError(f"Document {document_id} not found")
        
        # Get validation data from metadata
        validation_data = document.document_metadata.get('content_validation') if document.document_metadata else None
        
        if not validation_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No validation data found for this document"
            )
        
        return {
            "document_id": document_id,
            "title": document.title,
            "url": document.url,
            "status": document.status,
            "validation_report": validation_data
        }
        
    except NotFoundError:
        raise
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get validation report: {str(e)}"
        )


@router.post("/{document_id}/analyze")
async def analyze_document_content(
    document_id: int,
    analysis_type: str = Query("bullet_points", description="Type of analysis to perform"),
    user_context: UserContext = Depends(get_active_user_context),
    session: AsyncSession = Depends(get_session)
):
    """Trigger content analysis for a document (background task)"""
    
    try:
        document_service = DocumentService(session)
        
        # Verify document exists and belongs to user
        document = await document_service.get_document_by_id(
            firebase_uid=user_context.firebase_uid,
            document_id=document_id
        )
        
        if not document:
            raise NotFoundError(f"Document {document_id} not found")
        
        if not document.content or not document.content.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Document has no content to analyze"
            )
        
        # Get task manager and start analysis
        from app.services.content_analysis_task_manager import get_content_analysis_task_manager
        task_manager = get_content_analysis_task_manager()
        
        result = await task_manager.analyze_document_async(
            firebase_uid=user_context.firebase_uid,
            document_id=document_id,
            analysis_type=analysis_type
        )
        
        return {
            "message": "Content analysis started",
            "document_id": document_id,
            "analysis_type": analysis_type,
            "task_id": result.get('task_id'),
            "status": result.get('status')
        }
        
    except NotFoundError:
        raise
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start content analysis: {str(e)}"
        )


@router.get("/{document_id}/analysis-report")
async def get_document_analysis_report(
    document_id: int,
    user_context: UserContext = Depends(get_active_user_context),
    session: AsyncSession = Depends(get_session)
):
    """Get content analysis report for a document"""
    
    try:
        document_service = DocumentService(session)
        
        # Get the document
        document = await document_service.get_document_by_id(
            firebase_uid=user_context.firebase_uid,
            document_id=document_id
        )
        
        if not document:
            raise NotFoundError(f"Document {document_id} not found")
        
        # Get analysis data from metadata
        analysis_data = document.document_metadata.get('content_analysis') if document.document_metadata else None
        
        if not analysis_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No analysis data found for this document"
            )
        
        return {
            "document_id": document_id,
            "title": document.title,
            "url": document.url,
            "status": document.status,
            "analysis_report": analysis_data
        }
        
    except NotFoundError:
        raise
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get analysis report: {str(e)}"
        )


@router.post("/batch/analyze")
async def batch_analyze_documents(
    document_ids: Optional[List[int]] = None,
    analysis_type: str = Query("bullet_points", description="Type of analysis to perform"),
    user_context: UserContext = Depends(get_active_user_context),
    session: AsyncSession = Depends(get_session)
):
    """Trigger batch content analysis for multiple documents (background task)"""
    
    try:
        # Get task manager and start batch analysis
        from app.services.content_analysis_task_manager import get_content_analysis_task_manager
        task_manager = get_content_analysis_task_manager()
        
        result = await task_manager.batch_analyze_documents_async(
            firebase_uid=user_context.firebase_uid,
            document_ids=document_ids,
            analysis_type=analysis_type
        )
        
        return {
            "message": "Batch content analysis started",
            "analysis_type": analysis_type,
            "task_id": result.get('task_id'),
            "status": result.get('status')
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start batch analysis: {str(e)}"
        )


@router.get("/analysis/tasks")
async def get_analysis_tasks(
    user_context: UserContext = Depends(get_active_user_context)
):
    """Get all analysis tasks for the current user"""
    
    try:
        from app.services.content_analysis_task_manager import get_content_analysis_task_manager
        task_manager = get_content_analysis_task_manager()
        
        tasks = task_manager.get_all_tasks(firebase_uid=user_context.firebase_uid)
        
        return {
            "tasks": tasks,
            "total": len(tasks)
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get analysis tasks: {str(e)}"
        )


@router.get("/analysis/tasks/{task_id}")
async def get_analysis_task_status(
    task_id: str,
    user_context: UserContext = Depends(get_active_user_context)
):
    """Get status of a specific analysis task"""
    
    try:
        from app.services.content_analysis_task_manager import get_content_analysis_task_manager
        task_manager = get_content_analysis_task_manager()
        
        task_status = task_manager.get_task_status(task_id)
        
        if not task_status:
            raise NotFoundError(f"Task {task_id} not found")
        
        # Verify task belongs to user
        if task_status.get('firebase_uid') != user_context.firebase_uid:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to access this task"
            )
        
        return task_status
        
    except NotFoundError:
        raise
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get task status: {str(e)}"
        )


@router.delete("/analysis/tasks/{task_id}")
async def cancel_analysis_task(
    task_id: str,
    user_context: UserContext = Depends(get_active_user_context)
):
    """Cancel a running analysis task"""
    
    try:
        from app.services.content_analysis_task_manager import get_content_analysis_task_manager
        task_manager = get_content_analysis_task_manager()
        
        # Verify task belongs to user
        task_status = task_manager.get_task_status(task_id)
        if not task_status:
            raise NotFoundError(f"Task {task_id} not found")
        
        if task_status.get('firebase_uid') != user_context.firebase_uid:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to access this task"
            )
        
        success = task_manager.cancel_task(task_id)
        
        if success:
            return {"message": f"Task {task_id} cancelled successfully"}
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Task could not be cancelled (may not be running)"
            )
        
    except NotFoundError:
        raise
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to cancel task: {str(e)}"
        )


@router.get("/analysis/statistics")
async def get_analysis_statistics(
    user_context: UserContext = Depends(get_active_user_context)
):
    """Get analysis task statistics"""
    
    try:
        from app.services.content_analysis_task_manager import get_content_analysis_task_manager
        task_manager = get_content_analysis_task_manager()
        
        stats = task_manager.get_task_statistics()
        
        return stats
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get analysis statistics: {str(e)}"
        )


@router.post("/{document_id}/extract-entities")
async def extract_document_entities(
    document_id: int,
    background_tasks: BackgroundTasks,
    user_context: UserContext = Depends(get_active_user_context),
    session: AsyncSession = Depends(get_session)
):
    """Extract entities from a document using Gemini AI"""
    
    try:
        document_service = DocumentService(session)
        
        # Get the document
        document = await document_service.get_by_id(
            firebase_uid=user_context.firebase_uid,
            document_id=document_id
        )
        
        if not document:
            raise NotFoundError(f"Document {document_id} not found")
        
        if not document.content:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Document has no content to extract entities from"
            )
        
        # Import here to avoid circular imports
        from app.services.entity_extraction_task_manager import get_entity_extraction_task_manager
        
        # Get task manager
        task_manager = get_entity_extraction_task_manager()
        
        # Start background task
        task_id = f"entity_extraction_{user_context.firebase_uid}_{document_id}"
        
        # Add background task
        background_tasks.add_task(
            task_manager.extract_entities_async,
            user_context.firebase_uid,
            document_id,
            document.content
        )
        
        return {
            "message": "Entity extraction started",
            "task_id": task_id,
            "document_id": document_id,
            "status": "processing"
        }
        
    except NotFoundError:
        raise
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error starting entity extraction: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start entity extraction: {str(e)}"
        )


@router.get("/{document_id}/entities")
async def get_document_entities(
    document_id: int,
    user_context: UserContext = Depends(get_active_user_context),
    session: AsyncSession = Depends(get_session)
):
    """Get entities extracted from a document"""
    
    try:
        document_service = DocumentService(session)
        
        # Get the document
        document = await document_service.get_by_id(
            firebase_uid=user_context.firebase_uid,
            document_id=document_id
        )
        
        if not document:
            raise NotFoundError(f"Document {document_id} not found")
        
        # Import here to avoid circular imports
        from app.db.models import Entity, EntityDocument
        
        # Get entities for this document
        query = select(Entity).join(EntityDocument).where(
            and_(
                EntityDocument.document_id == document_id,
                Entity.user_id == document.user_id
            )
        )
        
        result = await session.execute(query)
        entities = result.scalars().all()
        
        return {
            "document_id": document_id,
            "entities": [
                {
                    "id": entity.id,
                    "name": entity.name,
                    "type": entity.type,
                    "description": entity.description,
                    "wikidata_id": entity.wikidata_id,
                    "relevance": 1.0  # Default relevance
                }
                for entity in entities
            ],
            "count": len(entities)
        }
        
    except NotFoundError:
        raise
    except Exception as e:
        logger.error(f"Error getting document entities: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get document entities: {str(e)}"
        )


@router.get("/entity-extraction/{task_id}/status")
async def get_entity_extraction_status(
    task_id: str,
    user_context: UserContext = Depends(get_active_user_context)
):
    """Get status of an entity extraction task"""
    
    try:
        # Import here to avoid circular imports
        from app.services.entity_extraction_task_manager import get_entity_extraction_task_manager
        
        # Get task manager
        task_manager = get_entity_extraction_task_manager()
        
        # Get task status
        status = task_manager.get_task_status(task_id)
        
        if not status:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Task {task_id} not found"
            )
        
        return status
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting task status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get task status: {str(e)}"
        )
