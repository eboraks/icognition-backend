import asyncio
import logging
from typing import List
from sqlmodel import Session
from sqlalchemy.orm import Session
from sqlalchemy import (
    and_,
    func,
    or_,
    select,
    text,
)

from app.models import Document, Embedding, Entity, Source
from app.gemini_client import GeminiClient
import re
from app.db_connector import get_engine


engine = get_engine()

logger = logging.getLogger(__name__)

class EmbeddingHandler:
    def __init__(self):
        self.gemini_client = GeminiClient()
        self.max_words = 1370
        self.max_chars = 8190

    def _chunk_text(self, text: str) -> List[str]:
        """
        Split text into chunks that are within the model's limits.
        Tries to split at sentence boundaries when possible.
        
        Args:
            text: The text to chunk
            
        Returns:
            List of text chunks
        """
        if not text:
            return []
            
        # First check if text is already within limits
        if len(text.split()) <= self.max_words and len(text) <= self.max_chars:
            return [text]
            
        chunks = []
        current_chunk = ""
        current_word_count = 0
        
        # Split into sentences first
        sentences = re.split(r'(?<=[.!?])\s+', text)
        
        for sentence in sentences:
            sentence_word_count = len(sentence.split())
            
            # If adding this sentence would exceed limits, save current chunk and start new one
            if current_word_count + sentence_word_count > self.max_words or len(current_chunk + sentence) > self.max_chars:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                current_chunk = sentence
                current_word_count = sentence_word_count
            else:
                current_chunk += " " + sentence
                current_word_count += sentence_word_count
                
        # Add the last chunk if it exists
        if current_chunk:
            chunks.append(current_chunk.strip())
            
        return chunks

    
    def _find_documents_without_embeddings(self, user_id: str):
        with Session(engine) as session:
            documents = session.scalars(
                select(Document)
                .join(Source, Document.id == Source.document_id)
                .where(
                    Source.user_id == user_id,
                    Document.source_text_in_html != None
                )
            ).all()
            embeddings_ids = session.scalars(select(Embedding.source_id).where(Embedding.source_type == "document", Embedding.user_id == user_id)).all()
            documents = [document for document in documents if document.id not in embeddings_ids]
            
            for document in documents:
                self.create_embedding_for_document(document, user_id)
    
    
    
    def create_embedding_for_entity(self, entity: Entity, user_id: str):
        self.create_embedding(
                user_id= user_id,
                source_id= entity.id,
                source_type="entity",
                text=entity.name + " " + entity.description,
                field="description"
            )
        
    def create_embedding_for_document(self, document: Document, user_id: str):
          self.create_embedding(
                user_id= user_id,
                source_id= document.id,
                source_type="document",
                text=document.get_source_text_as_string(),
                field="source_text_in_html"
             )
    
    def update_search_vectors(self):
        ## Update search_vector for embeddings that don't have it
        with Session(engine) as session:
            q = text(
                """UPDATE public.embedding
                    SET search_vector = to_tsvector('english', text)
                    WHERE search_vector IS NULL;"""
            )
            session.execute(q)
            session.commit()

    
    
    def create_embedding(
        self,
        user_id: str,
        source_id: str,
        source_type: str,
        text: str,
        field: str,
        version: int = 1
    ):
        """
        Create embeddings for the given text, handling chunking if needed.
        
        Args:
            user_id: User ID
            source_id: Source ID (Document or Entity ID)
            source_type: Type of source ('document' or 'entity')
            text: Text to embed
            field: Field name (e.g., 'title', 'description')
            version: Embedding version
            
        Returns:
            List of created Embedding instances
        """
        try:
            # Chunk the text if needed
            chunks = self._chunk_text(text)
            embeddings = []
            
            for i, chunk in enumerate(chunks):
                # Generate embedding for this chunk
                vector = asyncio.run(self.gemini_client.generate_embedding(
                    content=chunk,
                    title=str(source_id), 
                    task_type="RETRIEVAL_DOCUMENT",
                    output_dimensionality=768
                ))
                
                if not vector:
                    logger.error(f"Failed to generate embedding for chunk {i} of {field}")
                    continue
                    
                # Create Embedding instance
                embedding = Embedding(
                    user_id=user_id,
                    source_id=source_id,
                    source_type=source_type,
                    field=field,
                    text=chunk,
                    version=version,
                    vector=vector
                )
                
                embeddings.append(embedding)
                
            # Commit all embeddings
            with Session(engine) as db:
                db.add_all(embeddings)
                db.commit()
            
            self.update_search_vectors()
            
        except Exception as e:
            logger.error(f"Error creating embeddings: {str(e)}")
            raise

    async def update_embedding(
        self,
        db: Session,
        user_id: str,
        source_id: str,
        source_type: str,
        text: str,
        field: str,
        version: int = 1
    ) -> List[Embedding]:
        """
        Update existing embeddings for a source and field.
        First deletes old embeddings, then creates new ones.
        
        Args:
            db: Database session
            user_id: User ID
            source_id: Source ID
            source_type: Source type
            text: New text to embed
            field: Field name
            version: Embedding version
            
        Returns:
            List of new Embedding instances
        """
        try:
            # Delete existing embeddings for this source/field
            db.query(Embedding).filter(
                Embedding.source_id == source_id,
                Embedding.source_type == source_type,
                Embedding.field == field
            ).delete()
            
            # Create new embeddings
            return await self.create_embedding(
                db=db,
                user_id=user_id,
                source_id=source_id,
                source_type=source_type,
                text=text,
                field=field,
                version=version
            )
            
        except Exception as e:
            logger.error(f"Error updating embeddings: {str(e)}")
            db.rollback()
            raise 