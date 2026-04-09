"""
Embedding Service for vector search and similarity operations
"""

import asyncio
import json
from typing import Dict, Any, List, Optional, Union
from datetime import datetime
from dataclasses import dataclass
import numpy as np

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, text, bindparam
from sqlmodel import select as sqlmodel_select
from pgvector.sqlalchemy import Vector

from app.services.gemini_service import GeminiService, GeminiModel, get_gemini_service
from app.models import Document, User, Embedding
from app.utils.logging import get_logger
from app.utils.text_utils import extract_text_from_html
from app.core.config import settings
from langchain_text_splitters import HTMLSectionSplitter, RecursiveCharacterTextSplitter

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
        self.embedding_dimensions = 1536  # Dimensions for Embedding table
        
        # Initialize LangChain text splitters
        self.html_splitter = HTMLSectionSplitter(
            headers_to_split_on=[
                ("h1", "Header 1"),
                ("h2", "Header 2"),
                ("h3", "Header 3")
            ]
        )
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=200
        )
        
        logger.info("EmbeddingService initialized")
    
    async def generate_embedding(
        self,
        text: str,
        title: Optional[str] = None,
        task_type: str = None,
        dimensions: int = None,
        model: GeminiModel = GeminiModel.FLASH
    ) -> EmbeddingResult:
        """
        Generate embedding for text content
        
        Args:
            text: Text to embed
            title: Optional title for context
            task_type: Type of embedding task (auto-selected if None)
            dimensions: Embedding dimensions (default: 1536)
            model: Gemini model to use
            
        Returns:
            EmbeddingResult with embedding data
        """
        start_time = datetime.now()
        
        # Auto-select task type based on whether title is provided
        if task_type is None:
            task_type = "RETRIEVAL_DOCUMENT" if title else "SEMANTIC_SIMILARITY"
        
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
            # Note: task_type is not currently supported by the Gemini API SDK
            embedding = await self.gemini_service.generate_embedding(
                text=text,
                title=title,
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
            
            content_text = extract_text_from_html(document.content) if document.content else ""
            
            if use_content and content_text:
                if combine_strategy == "content_only":
                    text_parts = [content_text]
                elif combine_strategy == "title_content":
                    text_parts = [f"{document.title}: {content_text}"]
                elif combine_strategy == "separate":
                    if document.title:
                        text_parts.append(f"Title: {document.title}")
                    text_parts.append(f"Content: {content_text}")
                else:
                    text_parts.append(content_text)
            
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
            
            # Generate embedding with explicit dimensions (default: 1536)
            return await self.generate_embedding(
                text=combined_text,
                title=document.title,
                dimensions=self.default_dimensions
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
            # Use Embedding table to check for existing embeddings
            if force_regenerate:
                stmt = sqlmodel_select(Document).where(
                    Document.user_id == user_id,
                    Document.content.is_not(None)
                ).limit(batch_size)
            else:
                # Find documents that don't have embeddings in Embedding table
                docs_with_embeddings = select(Embedding.source_id).where(
                    Embedding.source_type == "document",
                    Embedding.user_id == str(user_id)
                ).distinct()
                
                stmt = sqlmodel_select(Document).where(
                    Document.user_id == user_id,
                    Document.content.is_not(None),
                    ~Document.id.in_(docs_with_embeddings)
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
                    success = await self.generate_and_store_document_embeddings(
                        session=session,
                        document=document,
                        user_id=user_id,
                        force_regenerate=force_regenerate
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
    
    def _has_html_structure(self, content: str) -> bool:
        """
        Check if content contains HTML structural tags.
        
        Args:
            content: Content string to check
            
        Returns:
            True if HTML structure detected, False otherwise
        """
        if not content:
            return False
        
        # Check for common HTML structural tags
        structural_tags = [
            '<article>', '<p>', '<h1>', '<h2>', '<h3>', '<h4>', '<h5>', '<h6>',
            '<ul>', '<ol>', '<li>', '<blockquote>'
        ]
        
        content_lower = content.lower()
        return any(tag in content_lower for tag in structural_tags)
    
    async def generate_and_store_document_embeddings(
        self,
        session: AsyncSession,
        document: Document,
        user_id: str,
        force_regenerate: bool = False
    ) -> bool:
        """
        Generate embeddings for a document and store them in the Embedding table.
        This creates separate embeddings for:
        - Document title (if exists)
        - Document content chunks (each chunk is embedded separately)
        
        Args:
            session: Database session
            document: Document to embed
            user_id: User ID
            force_regenerate: If True, delete existing embeddings first
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Delete existing embeddings if regenerating
            if force_regenerate:
                stmt = select(Embedding).where(
                    Embedding.source_type == "document",
                    Embedding.source_id == document.id,
                    Embedding.user_id == user_id
                )
                result = await session.execute(stmt)
                existing_embeddings = result.scalars().all()
                for emb in existing_embeddings:
                    await session.delete(emb)
                await session.flush()
            
            # Check if embeddings already exist
            if not force_regenerate:
                stmt = select(Embedding).where(
                    Embedding.source_type == "document",
                    Embedding.source_id == document.id,
                    Embedding.user_id == user_id
                )
                result = await session.execute(stmt)
                if result.scalar_one_or_none():
                    logger.info(f"Document {document.id} already has embeddings")
                    return True
            
            # --- Collect all texts to embed (title + content chunks) ---
            # (field_name, text) pairs; order is preserved so results can be zipped back.
            tasks_meta: List[tuple] = []

            if document.title and document.title.strip():
                tasks_meta.append(("title", document.title.strip()))

            if document.content and document.content.strip():
                content_html = document.content.strip()
                plain_text_content = extract_text_from_html(content_html)
                has_html = self._has_html_structure(content_html)

                if has_html:
                    try:
                        chunks = self.html_splitter.split_text(content_html)
                        logger.info(
                            f"Chunked document {document.id} HTML into "
                            f"{len(chunks)} sections via HTMLSectionSplitter"
                        )
                    except Exception as e:
                        logger.warning(
                            f"HTML splitter failed for document {document.id}, "
                            f"falling back to text splitter: {e}"
                        )
                        chunks = self.text_splitter.split_text(plain_text_content)
                else:
                    chunks = self.text_splitter.split_text(plain_text_content)
                    logger.info(
                        f"Chunked document {document.id} plain text into "
                        f"{len(chunks)} chunks via RecursiveCharacterTextSplitter"
                    )

                for idx, chunk in enumerate(chunks):
                    chunk_text = chunk.page_content if hasattr(chunk, 'page_content') else str(chunk)
                    if self._has_html_structure(chunk_text):
                        chunk_text = extract_text_from_html(chunk_text)
                    tasks_meta.append((f"content_chunk_{idx}", chunk_text))

            if not tasks_meta:
                logger.warning(f"No content to embed for document {document.id}")
                return False

            # --- Run all embedding API calls concurrently ---
            embed_start = datetime.now()
            raw_results = await asyncio.gather(
                *[
                    self.generate_embedding(text=text, dimensions=self.embedding_dimensions)
                    for _, text in tasks_meta
                ],
                return_exceptions=True,
            )
            elapsed = (datetime.now() - embed_start).total_seconds()
            logger.info(
                f"Generated {len(tasks_meta)} embeddings for document {document.id} "
                f"concurrently in {elapsed:.2f}s"
            )

            embeddings_to_create = []
            for (field, text), result in zip(tasks_meta, raw_results):
                if isinstance(result, Exception):
                    logger.warning(
                        f"Failed to embed field '{field}' for document {document.id}: {result}"
                    )
                    continue
                if result.success:
                    embeddings_to_create.append(Embedding(
                        user_id=user_id,
                        source_type="document",
                        source_id=document.id,
                        field=field,
                        text=text,
                        vector=result.embedding,
                        version=1
                    ))

            # Store all embeddings
            if embeddings_to_create:
                for emb in embeddings_to_create:
                    session.add(emb)
                await session.flush()
                logger.info(f"Created {len(embeddings_to_create)} embeddings for document {document.id}")
                return True
            else:
                logger.warning(f"No embeddings created for document {document.id} (no title or content)")
                return False
                
        except Exception as e:
            logger.error(f"Error generating embeddings for document {document.id}: {str(e)}")
            await session.rollback()
            return False
    
    async def generate_and_store_entity_embeddings(
        self,
        session: AsyncSession,
        entity,
        user_id: str,
        force_regenerate: bool = False
    ) -> bool:
        """
        Generate embeddings for a KG node and store on its vector column.
        Also stores in the Embedding table for backward compatibility.

        Args:
            session: Database session
            entity: KGNode instance
            user_id: User ID
            force_regenerate: If True, regenerate even if vector exists

        Returns:
            True if successful, False otherwise
        """
        try:
            # KGNode stores vector directly — check if already populated
            if not force_regenerate and entity.vector is not None:
                logger.info(f"KG node {entity.id} already has embedding")
                return True

            # Combine label and description for embedding
            text_parts = []
            name = getattr(entity, 'label', None) or getattr(entity, 'name', '')
            if name:
                text_parts.append(name.strip())
            if entity.description:
                text_parts.append(entity.description.strip())
            
            if text_parts:
                entity_text = " - ".join(text_parts)
                embedding_result = await self.generate_embedding(
                    text=entity_text,
                    dimensions=self.embedding_dimensions
                )
                if embedding_result.success:
                    # Store on the KGNode vector column directly
                    entity.vector = embedding_result.embedding
                    await session.flush()
                    logger.info(f"Generated embedding for KG node {entity.id}")
                    return True

            logger.warning(f"No embedding created for KG node {entity.id} (no name or description)")
            return False
                
        except Exception as e:
            logger.error(f"Error generating embeddings for entity {entity.id}: {str(e)}")
            await session.rollback()
            return False
    
    async def search_embeddings(
        self,
        session: AsyncSession,
        query_text: str,
        user_id: str,
        source_types: Optional[List[str]] = None,
        source_id: Optional[int] = None,
        limit: int = 10,
        similarity_threshold: float = 0.7
    ) -> List[Dict[str, Any]]:
        """
        Search the Embedding table for similar content.
        
        Args:
            session: Database session
            query_text: Search query
            user_id: User ID for data isolation
            source_types: List of source types to search ('document', 'entity', or both). Default: ['document']
            source_id: Optional ID of the specific source to filter by
            limit: Maximum number of results
            similarity_threshold: Minimum similarity score
            
        Returns:
            List of dictionaries with search results including document_id, entity_id, similarity_score, text, field
        """
        try:
            if source_types is None:
                source_types = ['document']
            
            # Generate query embedding
            query_embedding_result = await self.generate_embedding(
                text=query_text,
                dimensions=self.embedding_dimensions
            )
            
            if not query_embedding_result.success:
                logger.error("Failed to generate query embedding")
                return []
            
            query_vector = query_embedding_result.embedding

            # Convert vector to pgvector format string: '[1.0, 2.0, 3.0]'
            # Passed as a named bind parameter — never interpolated into SQL.
            vector_str = '[' + ','.join(str(v) for v in query_vector) + ']'

            # Build named parameters for source_types so they are fully bound,
            # never interpolated as raw strings into the query.
            source_type_placeholders = []
            params: Dict[str, Any] = {
                'query_vector': vector_str,
                'threshold': similarity_threshold,
                'limit': limit,
            }
            for i, st in enumerate(source_types):
                param_name = f'source_type_{i}'
                params[param_name] = st
                source_type_placeholders.append(f':{param_name}')
            source_types_clause = f"e.source_type IN ({', '.join(source_type_placeholders)})"

            # Build WHERE clause — only condition strings are assembled here,
            # all runtime values are bound parameters.
            where_clauses = [
                source_types_clause,
                "e.vector IS NOT NULL",
                "1 - (e.vector <=> CAST(:query_vector AS vector)) >= :threshold",
            ]

            # Filter by user_id only if provided and auth is not disabled
            if user_id is not None and not settings.DISABLE_AUTH:
                where_clauses.append("e.user_id = :user_id")
                params['user_id'] = user_id

            # Filter by source_id if provided
            if source_id is not None:
                where_clauses.append("e.source_id = :source_id")
                params['source_id'] = source_id

            where_clause_str = " AND ".join(where_clauses)

            stmt = text(f"""
                SELECT
                    e.id as embedding_id,
                    e.source_type,
                    e.source_id,
                    e.field,
                    e.text,
                    1 - (e.vector <=> CAST(:query_vector AS vector)) as similarity_score
                FROM embedding e
                WHERE {where_clause_str}
                ORDER BY e.vector <=> CAST(:query_vector AS vector)
                LIMIT :limit
            """)
            
            result = await session.execute(stmt, params)
            
            rows = result.fetchall()
            
            # Format results
            results = []
            seen_documents = set()
            seen_entities = set()
            
            for row in rows:
                result_item = {
                    'embedding_id': row.embedding_id,
                    'source_type': row.source_type,
                    'source_id': row.source_id,
                    'field': row.field,
                    'text': row.text,
                    'similarity_score': float(row.similarity_score)
                }
                
                # Track unique documents and entities
                if row.source_type == 'document':
                    seen_documents.add(row.source_id)
                elif row.source_type == 'entity':
                    seen_entities.add(row.source_id)
                
                results.append(result_item)
            
            logger.info(f"Found {len(results)} embedding matches ({len(seen_documents)} unique documents, {len(seen_entities)} unique entities)")
            return results
            
        except Exception as e:
            logger.error(f"Error searching embeddings: {str(e)}")
            return []
    
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
            
            # Get documents with embeddings from Embedding table
            embedded_stmt = select(func.count(func.distinct(Embedding.source_id))).where(
                Embedding.user_id == str(user_id),
                Embedding.source_type == "document"
            )
            embedded_result = await session.execute(embedded_stmt)
            embedded_documents = embedded_result.scalar() or 0
            
            # Get average embedding dimensions from Embedding table
            dim_stmt = text("""
                SELECT AVG(array_length(vector, 1)) as avg_dimensions
                FROM embedding 
                WHERE user_id = :user_id AND vector IS NOT NULL AND source_type = 'document'
            """)
            dim_result = await session.execute(dim_stmt, {'user_id': str(user_id)})
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
