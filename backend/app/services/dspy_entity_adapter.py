from typing import List, Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_

from app.models import Entity, EntityDocument
from app.services.user_service import UserService
from app.services.embedding_service import get_embedding_service
from app.services.wikidata_service import get_wikidata_service
from app.utils.logging import get_logger

logger = get_logger(__name__)


class DspyEntityAdapter:
    """
    Adapter for converting DSPy entity extraction results to database models.
    Refactored to support global shared entities and Wikidata anchoring.
    """
    
    def __init__(self, session: AsyncSession):
        """
        Initialize the entity adapter
        
        Args:
            session: Database session for entity operations
        """
        self.session = session
        self.wikidata_service = get_wikidata_service()
    
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
                    # Find or create entity (Global)
                    entity = await self._find_or_create_entity(
                        entity_data
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
        entity_data: Dict[str, Any]
    ) -> Optional[Entity]:
        """
        Find existing entity (globally) or create new one with Wikidata anchoring.
        
        Args:
            entity_data: Entity data from DSPy (name, type, description)
            
        Returns:
            Entity object or None
        """
        try:
            name = entity_data['name']
            entity_type = entity_data['type']
            description = entity_data['description']
            
            # 1. Exact Match (Global) by name and type
            query = select(Entity).where(
                and_(
                    Entity.name == name,
                    Entity.type == entity_type
                )
            )
            result = await self.session.execute(query)
            existing_entity = result.scalar_one_or_none()
            
            if existing_entity:
                # If it has wikidata_id, we're good. If not, maybe try to enrich?
                if not existing_entity.wikidata_id:
                    await self._enrich_entity_with_wikidata(existing_entity)
                return existing_entity
            
            # 2. Semantic Match (Global) via Embeddings
            embedding_service = get_embedding_service()
            candidate_text = f"{name} - {description}"
            
            # Search globally (user_id=None)
            semantic_matches = await embedding_service.search_embeddings(
                session=self.session,
                query_text=candidate_text,
                user_id=None,
                source_types=['entity'],
                limit=3,
                similarity_threshold=0.9  # High threshold for deduplication
            )
            
            if semantic_matches:
                match = semantic_matches[0]
                logger.info(f"Semantic match found for '{name}': {match['text']} (score: {match['similarity_score']})")
                
                # Fetch the existing entity
                ent_query = select(Entity).where(Entity.id == match['source_id'])
                ent_result = await self.session.execute(ent_query)
                matched_entity = ent_result.scalar_one_or_none()
                
                if matched_entity:
                    if not matched_entity.wikidata_id:
                        await self._enrich_entity_with_wikidata(matched_entity)
                    return matched_entity
            
            # 3. Wikidata Anchoring for new entity
            wikidata_id = None
            wikidata_data = None
            
            wikidata_results = await self.wikidata_service.search_entities(name, limit=3)
            if wikidata_results:
                # Basic disambiguation: pick the best match based on label/description
                # For now, just pick the first one if it's a good name match
                best_match = wikidata_results[0]
                wikidata_id = best_match.wikidata_id
                wikidata_data = best_match
            
            # 4. Check if we already have this wikidata_id globally
            if wikidata_id:
                wd_query = select(Entity).where(Entity.wikidata_id == wikidata_id)
                wd_result = await self.session.execute(wd_query)
                wd_entity = wd_result.scalar_one_or_none()
                if wd_entity:
                    logger.info(f"Found existing entity by Wikidata ID: {wikidata_id}")
                    return wd_entity
            
            # 5. Create new global entity
            new_entity = Entity(
                name=name,
                type=entity_type,
                description=description,
                wikidata_id=wikidata_id,
                wikidata_label=wikidata_data.label if wikidata_data else None,
                wikidata_description=wikidata_data.description if wikidata_data else None,
                wikidata_url=wikidata_data.url if wikidata_data else None,
                aliases=wikidata_data.aliases if wikidata_data else [],
                user_id=None # Global
            )
            
            self.session.add(new_entity)
            await self.session.flush()
            
            # Generate and store embedding for the new entity
            await embedding_service.generate_and_store_entity_embeddings(
                session=self.session,
                entity=new_entity,
                user_id="global", # Embeddings for global entities use "global" tag
                force_regenerate=False
            )
            await self.session.flush()
            
            return new_entity
            
        except Exception as e:
            logger.error(f"Error finding/creating entity: {e}")
            return None

    async def _enrich_entity_with_wikidata(self, entity: Entity) -> bool:
        """Attempt to enrich an existing entity with Wikidata info"""
        try:
            wikidata_results = await self.wikidata_service.search_entities(entity.name, limit=1)
            if wikidata_results:
                match = wikidata_results[0]
                entity.wikidata_id = match.wikidata_id
                entity.wikidata_label = match.label
                entity.wikidata_description = match.description
                entity.wikidata_url = match.url
                entity.aliases = match.aliases
                await self.session.flush()
                return True
            return False
        except Exception as e:
            logger.error(f"Error enriching entity {entity.id} with Wikidata: {e}")
            return False
    
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

