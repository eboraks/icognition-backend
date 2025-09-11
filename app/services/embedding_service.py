"""
Embedding Service for vector search and similarity operations
"""

import asyncio
import json
from typing import Dict, Any, List, Optional, Tuple, Union
from datetime import datetime
from dataclasses import dataclass
import numpy as np

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, text
from sqlmodel import select as sqlmodel_select

from app.services.gemini_service import GeminiService, GeminiModel, get_gemini_service
from app.db.models import Document, User
from app.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class EmbeddingResult:
    """Result of embedding generation"""
    embedding: List[float]
    dimensions: int
    model_used: str
    text_length: int
    generation_time: float
    success: bool
    error: Optional[str] = None


@dataclass
class SimilarityResult:
    """Result of similarity search"""
    document_id: int
    title: str
    url: str
    similarity_score: float
    content_preview: str
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class VectorSearchResult:
    """Result of vector search operation"""
    results: List[SimilarityResult]
    total_found: int
    search_time: float
    query_embedding: Optional[List[float]] = None
    success: bool = True
    error: Optional[str] = None


class EmbeddingService:
    """
    Service for generating embeddings and performing vector search operations
    """
    
    def __init__(self, gemini_service: Optional[GeminiService] = None):
        """
        Initialize the embedding service
        
        Args:
            gemini_service: Gemini service instance. If None, uses global instance
        """
        self.gemini_service = gemini_service or get_gemini_service()
        self.default_dimensions = 1536
        logger.info("EmbeddingService initialized")
    
    async def generate_embedding(
        self,
        text: str,
        title: Optional[str] = None,
        task_type: str = "SEMANTIC_SIMILARITY",
        dimensions: int = None,
        model: GeminiModel = GeminiModel.FLASH
    ) -> EmbeddingResult:
        """
        Generate embedding for text content
        
        Args:
            text: Text to embed
            title: Optional title for context
            task_type: Type of embedding task
            dimensions: Embedding dimensions (default: 1536)
            model: Gemini model to use
            
        Returns:
            EmbeddingResult with embedding data
        """
        start_time = datetime.now()
        
        if not text or not text.strip():
            return EmbeddingResult(
                embedding=[],
                dimensions=0,
                model_used="none",
                text_length=0,
                generation_time=0.0,
                success=False,
                error="Text cannot be empty"
            )
        
        try:
            dimensions = dimensions or self.default_dimensions
            
            logger.info(f"Generating embedding for text of length {len(text)}")
            
            # Generate embedding using Gemini service
            embedding = await self.gemini_service.generate_embedding(
                text=text,
                title=title,
                task_type=task_type,
                output_dimensionality=dimensions
            )
            
            generation_time = (datetime.now() - start_time).total_seconds()
            
            return EmbeddingResult(
                embedding=embedding,
                dimensions=len(embedding),
                model_used=f"{model.value}-embedding",
                text_length=len(text),
                generation_time=generation_time,
                success=True
            )
            
        except Exception as e:
            generation_time = (datetime.now() - start_time).total_seconds()
            logger.error(f"Error generating embedding: {str(e)}")
            
            return EmbeddingResult(
                embedding=[],
                dimensions=0,
                model_used="none",
                text_length=len(text),
                generation_time=generation_time,
                success=False,
                error=str(e)
            )
    
    async def generate_document_embedding(
        self,
        document: Document,
        use_content: bool = True,
        use_title: bool = True,
        combine_strategy: str = "content_only"
    ) -> EmbeddingResult:
        """
        Generate embedding for a document
        
        Args:
            document: Document to generate embedding for
            use_content: Whether to include document content
            use_title: Whether to include document title
            combine_strategy: How to combine title and content
            
        Returns:
            EmbeddingResult with embedding data
        """
        try:
            # Prepare text for embedding
            text_parts = []
            
            if use_title and document.title:
                text_parts.append(f"Title: {document.title}")
            
            if use_content and document.content:
                if combine_strategy == "content_only":
                    text_parts = [document.content]
                elif combine_strategy == "title_content":
                    text_parts = [f"{document.title}: {document.content}"]
                elif combine_strategy == "separate":
                    if document.title:
                        text_parts.append(f"Title: {document.title}")
                    text_parts.append(f"Content: {document.content}")
                else:
                    text_parts.append(document.content)
            
            if not text_parts:
                return EmbeddingResult(
                    embedding=[],
                    dimensions=0,
                    model_used="none",
                    text_length=0,
                    generation_time=0.0,
                    success=False,
                    error="No content available for embedding"
                )
            
            # Combine text parts
            combined_text = "\n\n".join(text_parts)
            
            # Generate embedding
            return await self.generate_embedding(
                text=combined_text,
                title=document.title,
                task_type="SEMANTIC_SIMILARITY"
            )
            
        except Exception as e:
            logger.error(f"Error generating document embedding: {str(e)}")
            return EmbeddingResult(
                embedding=[],
                dimensions=0,
                model_used="none",
                text_length=0,
                generation_time=0.0,
                success=False,
                error=str(e)
            )
    
    async def update_document_embedding(
        self,
        session: AsyncSession,
        document_id: int,
        user_id: int,
        force_regenerate: bool = False
    ) -> bool:
        """
        Update embedding for a document
        
        Args:
            session: Database session
            document_id: ID of document to update
            user_id: User ID for data isolation
            force_regenerate: Whether to regenerate even if embedding exists
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Get document
            stmt = sqlmodel_select(Document).where(
                Document.id == document_id,
                Document.user_id == user_id
            )
            result = await session.execute(stmt)
            document = result.scalar_one_or_none()
            
            if not document:
                logger.warning(f"Document {document_id} not found for user {user_id}")
                return False
            
            # Check if embedding already exists
            if document.content_vector and not force_regenerate:
                logger.info(f"Document {document_id} already has embedding")
                return True
            
            # Generate new embedding
            embedding_result = await self.generate_document_embedding(document)
            
            if not embedding_result.success:
                logger.error(f"Failed to generate embedding for document {document_id}")
                return False
            
            # Update document with embedding
            document.content_vector = embedding_result.embedding
            document.status = "embedded"
            
            # Update document metadata
            if not document.document_metadata:
                document.document_metadata = {}
            
            document.document_metadata.update({
                'embedding_info': {
                    'model_used': embedding_result.model_used,
                    'dimensions': embedding_result.dimensions,
                    'generation_time': embedding_result.generation_time,
                    'text_length': embedding_result.text_length,
                    'generated_at': datetime.now().isoformat()
                }
            })
            
            await session.commit()
            logger.info(f"Successfully updated embedding for document {document_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error updating document embedding: {str(e)}")
            await session.rollback()
            return False
    
    async def search_similar_documents(
        self,
        session: AsyncSession,
        query_text: str,
        user_id: int,
        limit: int = 10,
        similarity_threshold: float = 0.7,
        include_content: bool = False
    ) -> VectorSearchResult:
        """
        Search for documents similar to query text
        
        Args:
            session: Database session
            query_text: Text to search for
            user_id: User ID for data isolation
            limit: Maximum number of results
            similarity_threshold: Minimum similarity score
            include_content: Whether to include full content in results
            
        Returns:
            VectorSearchResult with similar documents
        """
        start_time = datetime.now()
        
        try:
            # Generate embedding for query
            query_embedding_result = await self.generate_embedding(query_text)
            
            if not query_embedding_result.success:
                return VectorSearchResult(
                    results=[],
                    total_found=0,
                    search_time=0.0,
                    success=False,
                    error=f"Failed to generate query embedding: {query_embedding_result.error}"
                )
            
            query_embedding = query_embedding_result.embedding
            
            # Perform vector similarity search
            # Using cosine similarity with pgvector
            stmt = text("""
                SELECT 
                    d.id,
                    d.title,
                    d.url,
                    d.content,
                    d.document_metadata,
                    1 - (d.content_vector <=> :query_vector) as similarity_score
                FROM documents d
                WHERE d.user_id = :user_id 
                AND d.content_vector IS NOT NULL
                AND 1 - (d.content_vector <=> :query_vector) >= :threshold
                ORDER BY d.content_vector <=> :query_vector
                LIMIT :limit
            """)
            
            result = await session.execute(stmt, {
                'query_vector': query_embedding,
                'user_id': user_id,
                'threshold': similarity_threshold,
                'limit': limit
            })
            
            rows = result.fetchall()
            search_time = (datetime.now() - start_time).total_seconds()
            
            # Process results
            similar_docs = []
            for row in rows:
                content_preview = row.content[:200] + "..." if len(row.content) > 200 else row.content
                
                metadata = None
                if row.document_metadata:
                    try:
                        metadata = json.loads(row.document_metadata) if isinstance(row.document_metadata, str) else row.document_metadata
                    except (json.JSONDecodeError, TypeError):
                        metadata = None
                
                similar_docs.append(SimilarityResult(
                    document_id=row.id,
                    title=row.title,
                    url=row.url,
                    similarity_score=float(row.similarity_score),
                    content_preview=content_preview,
                    metadata=metadata
                ))
            
            logger.info(f"Found {len(similar_docs)} similar documents for query")
            
            return VectorSearchResult(
                results=similar_docs,
                total_found=len(similar_docs),
                search_time=search_time,
                query_embedding=query_embedding,
                success=True
            )
            
        except Exception as e:
            search_time = (datetime.now() - start_time).total_seconds()
            logger.error(f"Error searching similar documents: {str(e)}")
            
            return VectorSearchResult(
                results=[],
                total_found=0,
                search_time=search_time,
                success=False,
                error=str(e)
            )
    
    async def find_duplicate_documents(
        self,
        session: AsyncSession,
        user_id: int,
        similarity_threshold: float = 0.95,
        limit: int = 50
    ) -> List[Tuple[Document, Document, float]]:
        """
        Find duplicate documents based on content similarity
        
        Args:
            session: Database session
            user_id: User ID for data isolation
            similarity_threshold: Minimum similarity for duplicates
            limit: Maximum number of comparisons
            
        Returns:
            List of tuples (doc1, doc2, similarity_score)
        """
        try:
            # Get documents with embeddings
            stmt = sqlmodel_select(Document).where(
                Document.user_id == user_id,
                Document.content_vector.is_not(None)
            ).limit(limit)
            
            result = await session.execute(stmt)
            documents = result.scalars().all()
            
            if len(documents) < 2:
                return []
            
            duplicates = []
            
            # Compare each document with others
            for i, doc1 in enumerate(documents):
                for doc2 in documents[i+1:]:
                    if doc1.id == doc2.id:
                        continue
                    
                    # Calculate similarity
                    similarity = self._calculate_cosine_similarity(
                        doc1.content_vector,
                        doc2.content_vector
                    )
                    
                    if similarity >= similarity_threshold:
                        duplicates.append((doc1, doc2, similarity))
            
            logger.info(f"Found {len(duplicates)} duplicate document pairs")
            return duplicates
            
        except Exception as e:
            logger.error(f"Error finding duplicate documents: {str(e)}")
            return []
    
    async def batch_update_embeddings(
        self,
        session: AsyncSession,
        user_id: int,
        batch_size: int = 10,
        force_regenerate: bool = False
    ) -> Dict[str, Any]:
        """
        Update embeddings for multiple documents in batch
        
        Args:
            session: Database session
            user_id: User ID for data isolation
            batch_size: Number of documents to process per batch
            force_regenerate: Whether to regenerate existing embeddings
            
        Returns:
            Dictionary with batch processing results
        """
        try:
            # Get documents without embeddings or force regenerate
            if force_regenerate:
                stmt = sqlmodel_select(Document).where(
                    Document.user_id == user_id,
                    Document.content.is_not(None)
                ).limit(batch_size)
            else:
                stmt = sqlmodel_select(Document).where(
                    Document.user_id == user_id,
                    Document.content.is_not(None),
                    Document.content_vector.is_(None)
                ).limit(batch_size)
            
            result = await session.execute(stmt)
            documents = result.scalars().all()
            
            if not documents:
                return {
                    'processed': 0,
                    'successful': 0,
                    'failed': 0,
                    'errors': []
                }
            
            successful = 0
            failed = 0
            errors = []
            
            for document in documents:
                try:
                    success = await self.update_document_embedding(
                        session, document.id, user_id, force_regenerate
                    )
                    if success:
                        successful += 1
                    else:
                        failed += 1
                        errors.append(f"Failed to update document {document.id}")
                except Exception as e:
                    failed += 1
                    errors.append(f"Error updating document {document.id}: {str(e)}")
            
            logger.info(f"Batch processing completed: {successful} successful, {failed} failed")
            
            return {
                'processed': len(documents),
                'successful': successful,
                'failed': failed,
                'errors': errors
            }
            
        except Exception as e:
            logger.error(f"Error in batch update embeddings: {str(e)}")
            return {
                'processed': 0,
                'successful': 0,
                'failed': 0,
                'errors': [str(e)]
            }
    
    def _calculate_cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """Calculate cosine similarity between two vectors"""
        try:
            if not vec1 or not vec2 or len(vec1) != len(vec2):
                return 0.0
            
            # Convert to numpy arrays for efficient calculation
            a = np.array(vec1)
            b = np.array(vec2)
            
            # Calculate cosine similarity
            dot_product = np.dot(a, b)
            norm_a = np.linalg.norm(a)
            norm_b = np.linalg.norm(b)
            
            if norm_a == 0 or norm_b == 0:
                return 0.0
            
            similarity = dot_product / (norm_a * norm_b)
            return float(similarity)
            
        except Exception as e:
            logger.error(f"Error calculating cosine similarity: {str(e)}")
            return 0.0
    
    async def get_embedding_statistics(
        self,
        session: AsyncSession,
        user_id: int
    ) -> Dict[str, Any]:
        """
        Get statistics about embeddings for a user
        
        Args:
            session: Database session
            user_id: User ID for data isolation
            
        Returns:
            Dictionary with embedding statistics
        """
        try:
            # Count documents with and without embeddings
            total_stmt = sqlmodel_select(func.count(Document.id)).where(
                Document.user_id == user_id
            )
            total_result = await session.execute(total_stmt)
            total_documents = total_result.scalar()
            
            embedded_stmt = sqlmodel_select(func.count(Document.id)).where(
                Document.user_id == user_id,
                Document.content_vector.is_not(None)
            )
            embedded_result = await session.execute(embedded_stmt)
            embedded_documents = embedded_result.scalar()
            
            # Get average embedding dimensions
            dim_stmt = text("""
                SELECT AVG(array_length(content_vector, 1)) as avg_dimensions
                FROM documents 
                WHERE user_id = :user_id AND content_vector IS NOT NULL
            """)
            dim_result = await session.execute(dim_stmt, {'user_id': user_id})
            avg_dimensions = dim_result.scalar() or 0
            
            return {
                'total_documents': total_documents,
                'embedded_documents': embedded_documents,
                'documents_without_embeddings': total_documents - embedded_documents,
                'embedding_coverage': embedded_documents / total_documents if total_documents > 0 else 0,
                'average_dimensions': float(avg_dimensions) if avg_dimensions else 0
            }
            
        except Exception as e:
            logger.error(f"Error getting embedding statistics: {str(e)}")
            return {
                'total_documents': 0,
                'embedded_documents': 0,
                'documents_without_embeddings': 0,
                'embedding_coverage': 0,
                'average_dimensions': 0,
                'error': str(e)
            }


# Global service instance
_embedding_service: Optional[EmbeddingService] = None


def get_embedding_service() -> EmbeddingService:
    """Get the global embedding service instance"""
    global _embedding_service
    if _embedding_service is None:
        _embedding_service = EmbeddingService()
    return _embedding_service


def initialize_embedding_service(gemini_service: Optional[GeminiService] = None) -> EmbeddingService:
    """Initialize the global embedding service instance"""
    global _embedding_service
    _embedding_service = EmbeddingService(gemini_service)
    return _embedding_service
