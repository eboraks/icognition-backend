"""
Entity Extraction Service for extracting entities from document content using Gemini AI
"""

import asyncio
import json
import re
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_

from app.db.models import Entity, EntityDocument, Document, User
from app.services.base_service import UserIsolatedService
from app.services.gemini_service import get_gemini_service, GeminiModel
from app.services.user_service import UserService
from app.utils.logging import get_logger

logger = get_logger(__name__)


class EntityExtractionService(UserIsolatedService[Entity]):
    """Service for extracting entities from document content using Gemini AI"""

    def __init__(self, session: AsyncSession):
        super().__init__(Entity)
        self.session = session
        self.gemini_service = get_gemini_service()

    async def extract_entities_from_content(
        self,
        content: str,
        firebase_uid: str,
        document_id: int
    ) -> List[Dict[str, Any]]:
        """
        Extract entities from document content using Gemini AI
        
        Args:
            content: The document content to extract entities from
            firebase_uid: Firebase UID of the user
            document_id: ID of the document being processed
            
        Returns:
            List of extracted entity dictionaries
        """
        try:
            # Create a structured prompt for entity extraction
            prompt = self._create_entity_extraction_prompt(content)
            
            # Get response from Gemini AI
            response = await self.gemini_service.generate_content(
                prompt=prompt,
                model=GeminiModel.GEMINI_PRO
            )
            
            # Parse the response to extract entities
            entities = self._parse_entity_response(response)
            
            logger.info(f"Extracted {len(entities)} entities from document {document_id}")
            return entities
            
        except Exception as e:
            logger.error(f"Error extracting entities from document {document_id}: {str(e)}")
            return []

    def _create_entity_extraction_prompt(self, content: str) -> str:
        """Create a structured prompt for entity extraction"""
        return f"""
Extract entities from the following content. For each entity, provide:
1. Name (exact text as it appears)
2. Type (choose from: Person, Product, Company, Location, Event, Technology, Topic)
3. Description (brief 1-2 sentence description)

Return the results in JSON format with this structure:
{{
    "entities": [
        {{
            "name": "Entity Name",
            "type": "Entity Type",
            "description": "Brief description of the entity"
        }}
    ]
}}

Content to analyze:
{content[:4000]}  # Limit content to avoid token limits
"""

    def _parse_entity_response(self, response: str) -> List[Dict[str, Any]]:
        """Parse the Gemini AI response to extract entities"""
        try:
            # Try to extract JSON from the response
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                json_str = json_match.group()
                data = json.loads(json_str)
                entities = data.get('entities', [])
                
                # Validate and clean entities
                cleaned_entities = []
                for entity in entities:
                    if self._validate_entity(entity):
                        cleaned_entities.append(self._clean_entity(entity))
                
                return cleaned_entities
            else:
                # Fallback: try to parse entities from text format
                return self._parse_text_format_entities(response)
                
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse JSON response: {e}")
            return self._parse_text_format_entities(response)
        except Exception as e:
            logger.error(f"Error parsing entity response: {e}")
            return []

    def _validate_entity(self, entity: Dict[str, Any]) -> bool:
        """Validate that an entity has required fields"""
        required_fields = ['name', 'type', 'description']
        return all(field in entity and entity[field] for field in required_fields)

    def _clean_entity(self, entity: Dict[str, Any]) -> Dict[str, Any]:
        """Clean and normalize entity data"""
        return {
            'name': entity['name'].strip(),
            'type': entity['type'].strip().title(),
            'description': entity['description'].strip()
        }

    def _parse_text_format_entities(self, response: str) -> List[Dict[str, Any]]:
        """Fallback parser for text format responses"""
        entities = []
        lines = response.split('\n')
        
        current_entity = {}
        for line in lines:
            line = line.strip()
            if not line:
                if current_entity and self._validate_entity(current_entity):
                    entities.append(self._clean_entity(current_entity))
                current_entity = {}
                continue
                
            # Try to parse entity information from text
            if line.startswith('Name:') or line.startswith('Entity:'):
                current_entity['name'] = line.split(':', 1)[1].strip()
            elif line.startswith('Type:'):
                current_entity['type'] = line.split(':', 1)[1].strip()
            elif line.startswith('Description:'):
                current_entity['description'] = line.split(':', 1)[1].strip()
        
        # Add the last entity if it exists
        if current_entity and self._validate_entity(current_entity):
            entities.append(self._clean_entity(current_entity))
        
        return entities

    async def process_document_entities(
        self,
        firebase_uid: str,
        document_id: int,
        content: str
    ) -> Dict[str, Any]:
        """
        Process entities for a document: extract, match, and store
        
        Args:
            firebase_uid: Firebase UID of the user
            document_id: ID of the document
            content: Document content
            
        Returns:
            Processing results dictionary
        """
        try:
            # Extract entities from content
            extracted_entities = await self.extract_entities_from_content(
                content, firebase_uid, document_id
            )
            
            if not extracted_entities:
                return {
                    'status': 'success',
                    'message': 'No entities found in document',
                    'entities_processed': 0
                }
            
            # Process each entity
            processed_count = 0
            for entity_data in extracted_entities:
                try:
                    # Find or create entity
                    entity = await self._find_or_create_entity(
                        firebase_uid, entity_data
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
                'entities_extracted': len(extracted_entities)
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
        firebase_uid: str,
        entity_data: Dict[str, Any]
    ) -> Optional[Entity]:
        """Find existing entity or create new one"""
        try:
            user = await UserService.get_or_create_user(self.session, firebase_uid)
            
            # Try to find existing entity by name and type
            query = select(Entity).where(
                and_(
                    Entity.user_id == user.id,
                    Entity.name == entity_data['name'],
                    Entity.type == entity_data['type']
                )
            )
            
            result = await self.session.execute(query)
            existing_entity = result.scalar_one_or_none()
            
            if existing_entity:
                return existing_entity
            
            # Create new entity
            new_entity = Entity(
                name=entity_data['name'],
                type=entity_data['type'],
                description=entity_data['description'],
                user_id=user.id
            )
            
            self.session.add(new_entity)
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
        """Create relationship between entity and document"""
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
                return True
            
            # Create new relationship
            relationship = EntityDocument(
                entity_id=entity_id,
                document_id=document_id,
                relevance=relevance
            )
            
            self.session.add(relationship)
            return True
            
        except Exception as e:
            logger.error(f"Error creating entity-document relationship: {e}")
            return False

    async def get_documents_ready_for_entity_extraction(
        self,
        firebase_uid: str,
        limit: int = 10
    ) -> List[Document]:
        """Get documents that are ready for entity extraction"""
        try:
            user = await UserService.get_or_create_user(self.session, firebase_uid)
            
            # Get documents that have content but haven't had entities extracted
            query = select(Document).where(
                and_(
                    Document.user_id == user.id,
                    Document.content.isnot(None),
                    Document.content != '',
                    Document.status.in_(['processed', 'validated', 'embedded'])
                )
            ).limit(limit)
            
            result = await self.session.execute(query)
            return result.scalars().all()
            
        except Exception as e:
            logger.error(f"Error getting documents for entity extraction: {e}")
            return []


def get_entity_extraction_service(session: AsyncSession) -> EntityExtractionService:
    """Get an instance of EntityExtractionService"""
    return EntityExtractionService(session)
