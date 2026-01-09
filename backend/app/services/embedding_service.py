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
from sqlalchemy import select, func, text, bindparam
from sqlmodel import select as sqlmodel_select
from pgvector.sqlalchemy import Vector

from app.services.gemini_service import GeminiService, GeminiModel, get_gemini_service
from app.models import Document, User, Embedding, Entity
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
            
            # DEPRECATED: This method uses the old content_vector field which has been removed.
            # Use generate_and_store_document_embeddings() instead, which stores embeddings in the Embedding table.
            logger.warning(
                "update_document_embedding() is deprecated. "
                "Use generate_and_store_document_embeddings() instead."
            )
            
            # Check if embeddings already exist in Embedding table
            stmt = select(Embedding).where(
                Embedding.source_type == "document",
                Embedding.source_id == document_id,
                Embedding.user_id == user_id
            )
            result = await session.execute(stmt)
            if result.scalar_one_or_none() and not force_regenerate:
                logger.info(f"Document {document_id} already has embeddings")
                return True
            
            # Use the new centralized method
            from app.models import Document
            doc_result = await session.execute(
                select(Document).where(Document.id == document_id)
            )
            doc = doc_result.scalar_one_or_none()
            if not doc:
                return False
            
            return await self.generate_and_store_document_embeddings(
                session=session,
                document=doc,
                user_id=user_id,
                force_regenerate=force_regenerate
            )
            
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
            
            # DEPRECATED: This method uses the old content_vector field which has been removed.
            # Use search_embeddings() instead, which searches the centralized Embedding table.
            logger.warning(
                "search_similar_documents() is deprecated. "
                "Use search_embeddings() instead."
            )
            
            # Use the new centralized search method
            embedding_results = await self.search_embeddings(
                session=session,
                query_text=query_text,
                user_id=str(user_id),
                source_types=['document'],
                limit=limit,
                similarity_threshold=similarity_threshold
            )
            
            if not embedding_results:
                return VectorSearchResult(
                    results=[],
                    total_found=0,
                    search_time=0.0,
                    success=True
                )
            
            # Get document IDs and fetch documents
            doc_ids = [r['source_id'] for r in embedding_results]
            stmt = sqlmodel_select(Document).where(
                Document.id.in_(doc_ids),
                Document.user_id == user_id
            )
            result = await session.execute(stmt)
            documents = result.scalars().all()
            
            # Create document score map
            doc_scores = {r['source_id']: r['similarity_score'] for r in embedding_results}
            
            # Sort documents by similarity score
            documents.sort(key=lambda d: doc_scores.get(d.id, 0), reverse=True)
            
            # Build results
            results = []
            for doc in documents:
                doc_data = {
                    'id': doc.id,
                    'title': doc.title,
                    'url': doc.url,
                    'similarity_score': doc_scores.get(doc.id, 0)
                }
                if include_content:
                    doc_data['content'] = doc.content
                results.append(doc_data)
            
            search_time = (datetime.now() - start_time).total_seconds()
            
            return VectorSearchResult(
                results=results,
                total_found=len(results),
                search_time=search_time,
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
            # DEPRECATED: This method uses the old content_vector field which has been removed.
            # This functionality should be refactored to use the Embedding table.
            logger.warning(
                "find_duplicate_documents() is deprecated. "
                "This method needs to be refactored to use the Embedding table."
            )
            
            # For now, return empty list as this functionality needs refactoring
            return []
            
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
            
            embeddings_to_create = []
            
            # 1. Embed document title if it exists
            if document.title and document.title.strip():
                title_text = document.title.strip()
                embedding_result = await self.generate_embedding(
                    text=title_text,
                    dimensions=self.embedding_dimensions
                )
                if embedding_result.success:
                    embeddings_to_create.append(Embedding(
                        user_id=user_id,
                        source_type="document",
                        source_id=document.id,
                        field="title",
                        text=title_text,
                        vector=embedding_result.embedding,
                        version=1
                    ))
                    logger.info(f"Generated title embedding for document {document.id}")
            
            # 2. Embed document content as chunks
            if document.content and document.content.strip():
                content_html = document.content.strip()
                plain_text_content = extract_text_from_html(content_html)
                has_html = self._has_html_structure(content_html)
                
                # Check if content has HTML structure
                if has_html:
                    # Use HTML splitter for structured content
                    try:
                        chunks = self.html_splitter.split_text(content_html)
                        logger.info(f"Chunked document {document.id} HTML content into {len(chunks)} chunks using HTMLSectionSplitter")
                    except Exception as e:
                        logger.warning(f"HTML splitter failed for document {document.id}, falling back to text splitter: {e}")
                        # Fallback to text splitter if HTML splitter fails
                        chunks = self.text_splitter.split_text(plain_text_content)
                else:
                    # Use text splitter for plain text
                    chunks = self.text_splitter.split_text(plain_text_content)
                    logger.info(f"Chunked document {document.id} plain text content into {len(chunks)} chunks using RecursiveCharacterTextSplitter")
                
                for idx, chunk in enumerate(chunks):
                    # Extract text from chunk (chunk may be a Document object from LangChain)
                    chunk_text = chunk.page_content if hasattr(chunk, 'page_content') else str(chunk)
                    if self._has_html_structure(chunk_text):
                        chunk_text = extract_text_from_html(chunk_text)
                    
                    embedding_result = await self.generate_embedding(
                        text=chunk_text,
                        dimensions=self.embedding_dimensions
                    )
                    if embedding_result.success:
                        embeddings_to_create.append(Embedding(
                            user_id=user_id,
                            source_type="document",
                            source_id=document.id,
                            field=f"content_chunk_{idx}",
                            text=chunk_text,
                            vector=embedding_result.embedding,
                            version=1
                        ))
                        logger.debug(f"Generated embedding for chunk {idx} of document {document.id}")
            
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
        entity: Entity,
        user_id: str,
        force_regenerate: bool = False
    ) -> bool:
        """
        Generate embeddings for an entity and store them in the Embedding table.
        Creates embeddings for entity name and description.
        
        Args:
            session: Database session
            entity: Entity to embed
            user_id: User ID
            force_regenerate: If True, delete existing embeddings first
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Delete existing embeddings if regenerating
            if force_regenerate:
                stmt = select(Embedding).where(
                    Embedding.source_type == "entity",
                    Embedding.source_id == entity.id,
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
                    Embedding.source_type == "entity",
                    Embedding.source_id == entity.id,
                    Embedding.user_id == user_id
                )
                result = await session.execute(stmt)
                if result.scalar_one_or_none():
                    logger.info(f"Entity {entity.id} already has embeddings")
                    return True
            
            embeddings_to_create = []
            
            # Combine name and description for embedding
            text_parts = []
            if entity.name:
                text_parts.append(entity.name.strip())
            if entity.description:
                text_parts.append(entity.description.strip())
            
            if text_parts:
                entity_text = " - ".join(text_parts)
                embedding_result = await self.generate_embedding(
                    text=entity_text,
                    dimensions=self.embedding_dimensions
                )
                if embedding_result.success:
                    embeddings_to_create.append(Embedding(
                        user_id=user_id,
                        source_type="entity",
                        source_id=entity.id,
                        field="name_description",
                        text=entity_text,
                        vector=embedding_result.embedding,
                        version=1
                    ))
                    logger.info(f"Generated embedding for entity {entity.id}")
            
            # Store embedding
            if embeddings_to_create:
                for emb in embeddings_to_create:
                    session.add(emb)
                await session.flush()
                logger.info(f"Created {len(embeddings_to_create)} embeddings for entity {entity.id}")
                return True
            else:
                logger.warning(f"No embeddings created for entity {entity.id} (no name or description)")
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
            # Following pgvector examples: https://github.com/pgvector/pgvector
            vector_str = '[' + ','.join(str(v) for v in query_vector) + ']'
            
            # Build source_types list for IN clause
            source_types_str = ','.join([f"'{st}'" for st in source_types])
            
            # Build WHERE clause
            where_clauses = [
                f"e.source_type IN ({source_types_str})",
                "e.vector IS NOT NULL",
                f"1 - (e.vector <=> '{vector_str}'::vector) >= :threshold"
            ]
            
            # Filter by user_id only if provided and auth is not disabled
            if user_id is not None and not settings.DISABLE_AUTH:
                where_clauses.append("e.user_id = :user_id")
            
            where_clause_str = " AND ".join(where_clauses)
            
            stmt = text(f"""
                SELECT 
                    e.id as embedding_id,
                    e.source_type,
                    e.source_id,
                    e.field,
                    e.text,
                    1 - (e.vector <=> '{vector_str}'::vector) as similarity_score
                FROM embedding e
                WHERE {where_clause_str}
                ORDER BY e.vector <=> '{vector_str}'::vector
                LIMIT :limit
            """)
            
            params = {
                'user_id': user_id,
                'threshold': similarity_threshold,
                'limit': limit
            }
            
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
