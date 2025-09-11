"""
API routes for document management
"""

from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, status, Query
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
