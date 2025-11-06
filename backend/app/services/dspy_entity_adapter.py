"""
Adapter to convert DSPy entity extraction results to database Entity models
Bridges DSPy entity service with existing database logic
"""

from typing import List, Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.models import Entity, EntityDocument
from app.services.user_service import UserService
from app.services.embedding_service import get_embedding_service
from app.utils.logging import get_logger

logger = get_logger(__name__)


class DspyEntityAdapter:
    """
    Adapter for converting DSPy entity extraction results to database models.
    Reuses existing database logic for entity storage and relationships.
    """
    
    def __init__(self, session: AsyncSession):
        """
        Initialize the entity adapter
        
        Args:
            session: Database session for entity operations
        """
        self.session = session
    
    async def process_document_entities(
        self,
        firebase_uid: str,
        document_id: int,
        entities: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Process and store entities extracted by DSPy
        
        Args:
            firebase_uid: User's Firebase UID
            document_id: Document ID
            entities: List of entity dicts from DSPy (with name, type, description)
            
        Returns:
            Processing results dictionary
        """
        try:
            if not entities:
                return {
                    'status': 'success',
                    'message': 'No entities found in document',
                    'entities_processed': 0
                }
            
            # Get or create user
            user = await UserService.get_or_create_user(self.session, firebase_uid)
            if not user:
                logger.error(f"Failed to get or create user for Firebase UID: {firebase_uid}")
                return {
                    'status': 'error',
                    'message': 'Failed to get user',
                    'entities_processed': 0
                }
            
            # Process each entity
            processed_count = 0
            for entity_data in entities:
                try:
                    # Find or create entity
                    entity = await self._find_or_create_entity(
                        user.id, entity_data
                    )
                    
                    if entity:
                        # Create entity-document relationship
                        await self._create_entity_document_relationship(
                            entity.id, document_id
                        )
                        processed_count += 1
                        
                except Exception as e:
                    logger.error(f"Error processing entity {entity_data.get('name', 'unknown')}: {e}")
                    continue
            
            return {
                'status': 'success',
                'message': f'Processed {processed_count} entities',
                'entities_processed': processed_count,
                'entities_extracted': len(entities)
            }
            
        except Exception as e:
            logger.error(f"Error processing document entities: {e}")
            return {
                'status': 'error',
                'message': str(e),
                'entities_processed': 0
            }
    
    async def _find_or_create_entity(
        self,
        user_id: str,
        entity_data: Dict[str, Any]
    ) -> Optional[Entity]:
        """
        Find existing entity or create new one
        
        Args:
            user_id: User ID
            entity_data: Entity data from DSPy (name, type, description)
            
        Returns:
            Entity object or None
        """
        try:
            # Try to find existing entity by name and type
            query = select(Entity).where(
                and_(
                    Entity.user_id == user_id,
                    Entity.name == entity_data['name'],
                    Entity.type == entity_data['type']
                )
            )
            
            result = await self.session.execute(query)
            existing_entity = result.scalar_one_or_none()
            
            if existing_entity:
                # Check if entity has embeddings, if not generate them
                from app.models import Embedding
                emb_check = select(Embedding).where(
                    Embedding.source_type == "entity",
                    Embedding.source_id == existing_entity.id,
                    Embedding.user_id == user_id
                )
                emb_result = await self.session.execute(emb_check)
                if not emb_result.scalar_one_or_none():
                    # Entity exists but has no embeddings - generate them
                    embedding_service = get_embedding_service()
                    await embedding_service.generate_and_store_entity_embeddings(
                        session=self.session,
                        entity=existing_entity,
                        user_id=user_id,
                        force_regenerate=False
                    )
                    await self.session.flush()
                return existing_entity
            
            # Create new entity
            new_entity = Entity(
                name=entity_data['name'],
                type=entity_data['type'],
                description=entity_data['description'],
                user_id=user_id
            )
            
            self.session.add(new_entity)
            await self.session.flush()
            
            # Generate embeddings for the new entity
            embedding_service = get_embedding_service()
            await embedding_service.generate_and_store_entity_embeddings(
                session=self.session,
                entity=new_entity,
                user_id=user_id,
                force_regenerate=False
            )
            await self.session.flush()
            
            return new_entity
            
        except Exception as e:
            logger.error(f"Error finding/creating entity: {e}")
            return None
    
    async def _create_entity_document_relationship(
        self,
        entity_id: int,
        document_id: int,
        relevance: float = 1.0
    ) -> bool:
        """
        Create or update entity-document relationship
        
        Args:
            entity_id: Entity ID
            document_id: Document ID
            relevance: Relevance score (default 1.0)
            
        Returns:
            True if successful
        """
        try:
            # Check if relationship already exists
            query = select(EntityDocument).where(
                and_(
                    EntityDocument.entity_id == entity_id,
                    EntityDocument.document_id == document_id
                )
            )
            
            result = await self.session.execute(query)
            existing_relationship = result.scalar_one_or_none()
            
            if existing_relationship:
                # Update relevance if needed
                if existing_relationship.relevance != relevance:
                    existing_relationship.relevance = relevance
                    await self.session.flush()
                return True
            
            # Create new relationship
            new_relationship = EntityDocument(
                entity_id=entity_id,
                document_id=document_id,
                relevance=relevance
            )
            
            self.session.add(new_relationship)
            await self.session.flush()
            
            return True
            
        except Exception as e:
            logger.error(f"Error creating entity-document relationship: {e}")
            return False

