"""
System API routes for data management and population
"""

from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, func, text
from sqlalchemy.orm import selectinload
from pydantic import BaseModel
from datetime import datetime
import uuid

from app.core.user_context import get_active_user_context, UserContext
from app.db.database import get_session
from app.models import Document, Entity, EntityDocument, Embedding
from app.log import get_logger
from app.api.routes.bookmarks import _process_document_entities, _process_document_embeddings, _process_document_content, _process_document_entities_batch, _process_document_embeddings_batch
from asyncio import create_task

router = APIRouter(prefix="/system", tags=["system"])

logger = get_logger(__name__)


class DocumentProcessingStats(BaseModel):
    """Statistics about document processing status"""
    total_documents: int
    documents_with_entities: int
    documents_with_embeddings: int
    documents_without_entities: int
    documents_without_embeddings: int
    documents_without_both: int
    documents_without_content: int


class DocumentProcessingRequest(BaseModel):
    """Request model for triggering document processing"""
    document_ids: Optional[List[str]] = None
    user_id: Optional[str] = None
    process_entities: bool = True
    process_embeddings: bool = True
    process_content: bool = True


class DocumentProcessingResponse(BaseModel):
    """Response model for document processing"""
    message: str
    documents_processed: int
    tasks_triggered: int
    document_ids: List[int]


@router.get("/documents/stats", response_model=DocumentProcessingStats)
async def get_document_processing_stats(
    user_context: UserContext = Depends(get_active_user_context),
    session: AsyncSession = Depends(get_session)
):
    """
    Get statistics about document processing status.
    
    Returns counts of documents with/without entities and embeddings.
    """
    try:
        # Get total documents for the user
        total_docs_query = select(func.count(Document.id)).where(
            Document.user_id == user_context.user.id
        )
        total_docs_result = await session.execute(total_docs_query)
        total_documents = total_docs_result.scalar() or 0
        
        # Get documents with entities
        docs_with_entities_query = select(func.count(func.distinct(EntityDocument.document_id))).join(
            Document, EntityDocument.document_id == Document.id
        ).where(Document.user_id == user_context.user.id)
        docs_with_entities_result = await session.execute(docs_with_entities_query)
        documents_with_entities = docs_with_entities_result.scalar() or 0
        
        # Get documents with embeddings
        docs_with_embeddings_query = select(func.count(func.distinct(Embedding.source_id))).where(
            Embedding.source_type == "document",
            Embedding.user_id == user_context.user.id
        )
        docs_with_embeddings_result = await session.execute(docs_with_embeddings_query)
        documents_with_embeddings = docs_with_embeddings_result.scalar() or 0
        
        # Get documents without content (can't be processed)
        docs_without_content_query = select(func.count(Document.id)).where(
            and_(
                Document.user_id == user_context.user.id,
                or_(
                    Document.content.is_(None),
                    Document.content == "",
                    func.length(Document.content) < 10
                )
            )
        )
        docs_without_content_result = await session.execute(docs_without_content_query)
        documents_without_content = docs_without_content_result.scalar() or 0
        
        # Calculate derived stats
        documents_without_entities = total_documents - documents_with_entities
        documents_without_embeddings = total_documents - documents_with_embeddings
        
        # Documents without both entities and embeddings
        docs_without_both_query = select(func.count(Document.id)).where(
            and_(
                Document.user_id == user_context.user.id,
                Document.content.isnot(None),
                Document.content != "",
                func.length(Document.content) >= 10,
                ~Document.id.in_(
                    select(EntityDocument.document_id).distinct()
                ),
                ~Document.id.in_(
                    select(Embedding.source_id).where(
                        Embedding.source_type == "document",
                        Embedding.user_id == user_context.user.id
                    )
                )
            )
        )
        docs_without_both_result = await session.execute(docs_without_both_query)
        documents_without_both = docs_without_both_result.scalar() or 0
        
        return DocumentProcessingStats(
            total_documents=total_documents,
            documents_with_entities=documents_with_entities,
            documents_with_embeddings=documents_with_embeddings,
            documents_without_entities=documents_without_entities,
            documents_without_embeddings=documents_without_embeddings,
            documents_without_both=documents_without_both,
            documents_without_content=documents_without_content
        )
        
    except Exception as e:
        logger.error(f"Error getting document processing stats: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get processing stats: {str(e)}"
        )


@router.get("/documents/missing-processing")
async def get_documents_missing_processing(
    missing_entities: bool = Query(True, description="Include documents missing entities"),
    missing_embeddings: bool = Query(True, description="Include documents missing embeddings"),
    missing_content: bool = Query(False, description="Include documents missing content processing"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of documents to return"),
    user_context: UserContext = Depends(get_active_user_context),
    session: AsyncSession = Depends(get_session)
):
    """
    Get documents that are missing entities, embeddings, or content processing.
    
    This endpoint helps identify documents that need processing to populate missing data.
    """
    try:
        conditions = [Document.user_id == user_context.user.id]
        
        # Add content filter (only documents with content can be processed)
        conditions.append(
            and_(
                Document.content.isnot(None),
                Document.content != "",
                func.length(Document.content) >= 10
            )
        )
        
        # Build conditions based on what's missing
        missing_conditions = []
        
        if missing_entities:
            missing_conditions.append(
                ~Document.id.in_(
                    select(EntityDocument.document_id).distinct()
                )
            )
        
        if missing_embeddings:
            missing_conditions.append(
                ~Document.id.in_(
                    select(Embedding.source_id).where(
                        Embedding.source_type == "document",
                        Embedding.user_id == user_context.user.id
                    )
                )
            )
        
        if missing_content:
            missing_conditions.append(
                or_(
                    Document.ai_is_about.is_(None),
                    Document.ai_bullet_points.is_(None),
                    Document.ai_is_about == "",
                    Document.ai_bullet_points == ""
                )
            )
        
        if missing_conditions:
            conditions.append(or_(*missing_conditions))
        
        # Execute query
        query = select(Document).where(and_(*conditions)).limit(limit)
        result = await session.execute(query)
        documents = result.scalars().all()
        
        # Format response
        document_list = []
        for doc in documents:
            # Check what's missing for each document
            missing_items = []
            
            if missing_entities:
                entity_check = await session.execute(
                    select(func.count(EntityDocument.document_id)).where(
                        EntityDocument.document_id == doc.id
                    )
                )
                has_entities = entity_check.scalar() > 0
                if not has_entities:
                    missing_items.append("entities")
            
            if missing_embeddings:
                embedding_check = await session.execute(
                    select(func.count(Embedding.id)).where(
                        and_(
                            Embedding.source_id == doc.id,
                            Embedding.source_type == "document",
                            Embedding.user_id == user_context.user.id
                        )
                    )
                )
                has_embeddings = embedding_check.scalar() > 0
                if not has_embeddings:
                    missing_items.append("embeddings")
            
            if missing_content:
                has_content = (
                    doc.ai_is_about and 
                    doc.ai_bullet_points and 
                    doc.ai_is_about.strip() != "" and 
                    doc.ai_bullet_points.strip() != ""
                )
                if not has_content:
                    missing_items.append("content")
            
            document_list.append({
                "id": str(doc.id),
                "title": doc.title,
                "url": doc.url,
                "created_at": doc.created_at.isoformat() if doc.created_at else None,
                "missing": missing_items,
                "content_length": len(doc.content) if doc.content else 0
            })
        
        return {
            "documents": document_list,
            "total_found": len(document_list),
            "limit": limit,
            "filters": {
                "missing_entities": missing_entities,
                "missing_embeddings": missing_embeddings,
                "missing_content": missing_content
            }
        }
        
    except Exception as e:
        logger.error(f"Error getting documents missing processing: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get documents: {str(e)}"
        )


@router.post("/documents/process", response_model=DocumentProcessingResponse)
async def trigger_document_processing(
    request: DocumentProcessingRequest,
    background_tasks: BackgroundTasks,
    user_context: UserContext = Depends(get_active_user_context),
    session: AsyncSession = Depends(get_session)
):
    """
    Trigger background processing for documents that are missing entities, embeddings, or content.
    
    This endpoint is designed for data population after code fixes or updates.
    """
    try:
        document_ids = []
        tasks_triggered = 0
        
        if request.document_ids:
            # Process specific documents
            for doc_id_str in request.document_ids:
                try:
                    doc_id = uuid.UUID(doc_id_str)
                    
                    # Verify document exists and belongs to user
                    doc_query = select(Document).where(
                        and_(
                            Document.id == doc_id,
                            Document.user_id == user_context.user.id
                        )
                    )
                    doc_result = await session.execute(doc_query)
                    document = doc_result.scalar_one_or_none()
                    
                    if not document:
                        logger.warning(f"Document {doc_id} not found or not accessible to user {user_context.user.id}")
                        continue
                    
                    if not document.content or len(document.content.strip()) < 10:
                        logger.warning(f"Document {doc_id} has insufficient content for processing")
                        continue
                    
                    document_ids.append(doc_id_str)
                    
                    # Trigger background tasks based on request
                    if request.process_content:
                        background_tasks.add_task(
                            _process_document_content,
                            str(doc_id),
                            document.title,
                            document.url,
                            user_context.user.id
                        )
                        tasks_triggered += 1
                    
                    if request.process_entities:
                        background_tasks.add_task(
                            _process_document_entities,
                            str(doc_id),
                            user_context.user.id
                        )
                        tasks_triggered += 1
                    
                    if request.process_embeddings:
                        background_tasks.add_task(
                            _process_document_embeddings,
                            str(doc_id)
                        )
                        tasks_triggered += 1
                        
                except ValueError:
                    logger.warning(f"Invalid document ID format: {doc_id_str}")
                    continue
                    
        else:
            # Process all documents missing the specified processing
            conditions = [Document.user_id == user_context.user.id]
            
            # Only process documents with content
            conditions.append(
                and_(
                    Document.content.isnot(None),
                    Document.content != "",
                    func.length(Document.content) >= 10
                )
            )
            
            # Build conditions based on what needs processing
            missing_conditions = []
            
            if request.process_entities:
                missing_conditions.append(
                    ~Document.id.in_(
                        select(EntityDocument.document_id).distinct()
                    )
                )
            
            if request.process_embeddings:
                missing_conditions.append(
                    ~Document.id.in_(
                        select(Embedding.source_id).where(
                            Embedding.source_type == "document",
                            Embedding.user_id == user_context.user.id
                        )
                    )
                )
            
            if request.process_content:
                missing_conditions.append(
                    or_(
                        Document.ai_is_about.is_(None),
                        Document.ai_bullet_points.is_(None),
                        Document.ai_is_about == "",
                        Document.ai_bullet_points == ""
                    )
                )
            
            if missing_conditions:
                conditions.append(or_(*missing_conditions))
            
            # Get documents to process
            query = select(Document).where(and_(*conditions)).limit(100)  # Limit to prevent overload
            result = await session.execute(query)
            documents = result.scalars().all()
            
            for document in documents:
                document_ids.append(str(document.id))
                
                # Trigger background tasks
                if request.process_content:
                    background_tasks.add_task(
                        _process_document_content,
                        str(document.id),
                        document.title,
                        document.url,
                        user_context.user.id
                    )
                    tasks_triggered += 1
                
                if request.process_entities:
                    background_tasks.add_task(
                        _process_document_entities,
                        str(document.id),
                        user_context.user.id
                    )
                    tasks_triggered += 1
                
                if request.process_embeddings:
                    background_tasks.add_task(
                        _process_document_embeddings,
                        str(document.id)
                    )
                    tasks_triggered += 1
        
        logger.info(f"Triggered processing for {len(document_ids)} documents with {tasks_triggered} background tasks")
        
        return DocumentProcessingResponse(
            message=f"Processing triggered for {len(document_ids)} documents",
            documents_processed=len(document_ids),
            tasks_triggered=tasks_triggered,
            document_ids=document_ids
        )
        
    except Exception as e:
        logger.error(f"Error triggering document processing: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to trigger processing: {str(e)}"
        )


@router.post("/documents/process-missing-entities")
async def process_missing_entities(
    background_tasks: BackgroundTasks,
    user_context: UserContext = Depends(get_active_user_context),
    session: AsyncSession = Depends(get_session)
):
    """
    Process documents that are missing entities.
    
    Finds all documents for the user that don't have entities and triggers entity extraction.
    """
    try:
        # Find documents missing entities
        conditions = [
            Document.user_id == user_context.user.id,
            Document.content.isnot(None),
            Document.content != "",
            func.length(Document.content) >= 10,
            ~Document.id.in_(
                select(EntityDocument.document_id).distinct()
            )
        ]
        
        # Get documents to process
        query = select(Document).where(and_(*conditions)).limit(100)
        result = await session.execute(query)
        documents = result.scalars().all()
        
        if not documents:
            return {
                "message": "No documents found that need entity processing",
                "documents_processed": 0,
                "document_ids": []
            }
        
        document_ids = [str(doc.id) for doc in documents]
        
        # Trigger single background task for all documents
        background_tasks.add_task(
            _process_document_entities_batch,
            document_ids,
            user_context.user.id
        )
        
        logger.info(f"Triggered entity processing for {len(document_ids)} documents")
        
        return {
            "message": f"Entity processing triggered for {len(document_ids)} documents",
            "documents_processed": len(document_ids),
            "document_ids": document_ids
        }
        
    except Exception as e:
        logger.error(f"Error processing missing entities: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process missing entities: {str(e)}"
        )


@router.post("/documents/process-missing-embeddings")
async def process_missing_embeddings(
    background_tasks: BackgroundTasks,
    user_context: UserContext = Depends(get_active_user_context),
    session: AsyncSession = Depends(get_session)
):
    """
    Process documents that are missing embeddings.
    
    Finds all documents for the user that don't have embeddings and triggers embedding generation.
    """
    try:
        # Find documents missing embeddings
        conditions = [
            Document.user_id == user_context.user.id,
            Document.content.isnot(None),
            Document.content != "",
            func.length(Document.content) >= 10,
            ~Document.id.in_(
                select(Embedding.source_id).where(
                    Embedding.source_type == "document",
                    Embedding.user_id == user_context.user.id
                )
            )
        ]
        
        # Get documents to process
        query = select(Document).where(and_(*conditions)).limit(100)
        result = await session.execute(query)
        documents = result.scalars().all()
        
        if not documents:
            return {
                "message": "No documents found that need embedding processing",
                "documents_processed": 0,
                "document_ids": []
            }
        
        document_ids = [str(doc.id) for doc in documents]
        
        # Trigger single background task for all documents
        background_tasks.add_task(
            _process_document_embeddings_batch,
            document_ids,
            user_context.user.id
        )
        
        logger.info(f"Triggered embedding processing for {len(document_ids)} documents")
        
        return {
            "message": f"Embedding processing triggered for {len(document_ids)} documents",
            "documents_processed": len(document_ids),
            "document_ids": document_ids
        }
        
    except Exception as e:
        logger.error(f"Error processing missing embeddings: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process missing embeddings: {str(e)}"
        )


@router.get("/health")
async def system_health_check():
    """
    Simple health check endpoint for the system routes.
    """
    return {
        "status": "healthy",
        "service": "system",
        "timestamp": datetime.now().isoformat()
    }
