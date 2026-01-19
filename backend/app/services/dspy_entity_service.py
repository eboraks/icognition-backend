"""
DSPy-based entity extraction service for iCognition
Uses DSPy with Google Gemini Flash Lite for fast entity extraction
"""

from typing import Optional, List, Dict, Any
import dspy
import anyio
from datetime import datetime

from app.core.config import settings
from app.utils.logging import get_logger
from app.services.dspy_models_entities_only import EntityExtractionResult, Entity
from app.models import Document
from app.utils.text_utils import extract_text_from_html
from app.services.prompt_service import PromptService
from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger(__name__)


# --- DSPy Signature for Entity Extraction ---
class ExtractEntities(dspy.Signature):
    """
You are an expert entity extraction engine. Your task is to extract the MOST IMPORTANT entities from the provided text.

Return a valid JSON object with a list of entities.

### Entity Extraction Rules:

1.  **Focus on Main Entities:**
    - Extract only entities CENTRAL to understanding the content
    - IGNORE: photographers, bylines, publication details, photo credits, dates
    - INCLUDE: Main people, organizations, locations, events, concepts, products, technologies

2.  **Entity Types:**
    - organization: Companies, institutions, government bodies
    - person: Key individuals mentioned (not authors/photographers)
    - topic: Main subjects or themes
    - location: Important places
    - event: Specific events or happenings
    - technology: Technologies or technical concepts
    - product: Products or services
    - institution: Academic or governmental institutions

3.  **Quality over Quantity:**
    - Extract up to 15 entities maximum.
    - Each entity must be clearly relevant to the main content.
    - Provide a brief 1-sentence description for each

4.  **Description Format:**
    - Keep descriptions under 15 words
    - Focus on the entity's role in THIS content
    - Example: "The company announcing the product recall"
"""
    
    content_text: str = dspy.InputField(
        desc="The full text to extract entities from."
    )
    
    extracted_entities: EntityExtractionResult = dspy.OutputField(
        desc="The list of extracted entities with names, types, and descriptions."
    )


# --- DSPy Program ---
class EntityExtractorProgram(dspy.Module):
    """DSPy program for entity extraction"""
    
    def __init__(self):
        super().__init__()
        self.predict = dspy.Predict(ExtractEntities)

    def forward(self, text):
        result = self.predict(content_text=text)
        return result.extracted_entities


class DspyEntityService:
    """
    Service for extracting entities using DSPy and Google Gemini Flash Lite.
    """
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize the DSPy entity service
        
        Args:
            api_key: Google API key. If None, uses settings.GOOGLE_API_KEY
        """
        self.api_key = api_key or settings.GOOGLE_API_KEY
        if not self.api_key:
            raise ValueError("Google API key is required for DSPy entity extraction")
        
        # Store LM configuration but don't configure globally yet
        gemini_model_name = settings.GEMINI_FLASH_LITE_MODEL.replace("models/", "")
        self.model_name = f'gemini/{gemini_model_name}'
        
        logger.info("DspyEntityService initialized successfully with Flash Lite model")
    
    async def extract_entities_from_content(
        self,
        content: str,
        document_id: Optional[int] = None,
        session: Optional[AsyncSession] = None
    ) -> List[Dict[str, Any]]:
        """
        Extract entities from document content using DSPy.
        
        Args:
            content: Document content text
            document_id: Optional document ID for logging
            session: Optional database session to load prompt from DB
            
        Returns:
            List of entity dictionaries with name, type, description
        """
        text = extract_text_from_html(content)
        if not text:
            logger.warning(f"Empty content for document {document_id}, skipping entity extraction")
            return []
        
        # New Rule: Only process if there are 50 words or more
        word_count = len(text.split())
        if word_count < 50:
            logger.info(f"Content for document {document_id} is too short ({word_count} words), skipping entity extraction (min 50 words required)")
            return []
        
        # Load prompt from database if session is provided
        custom_instructions = None
        if session:
            try:
                prompt_service = PromptService(session)
                db_prompt = await prompt_service.get_latest_prompt("entity_extraction")
                if db_prompt and db_prompt.user_prompt:
                    logger.info(f"Using custom entity extraction prompt from database (version {db_prompt.version})")
                    custom_instructions = db_prompt.user_prompt
            except Exception as e:
                logger.warning(f"Error loading prompt from database, falling back to hardcoded: {e}")

        logger.info(f"Starting DSPy entity extraction for document {document_id or 'unknown'}")
        
        try:
            # Use anyio.to_thread.run_sync to offload synchronous DSPy calls
            # This prevents blocking the event loop during LLM processing
            lm = dspy.LM(self.model_name, api_key=self.api_key)
            
            def run_extraction():
                with dspy.context(lm=lm):
                    # Use custom instructions if available, otherwise use hardcoded ones in the signature
                    signature = ExtractEntities
                    if custom_instructions:
                        signature = ExtractEntities.with_instructions(custom_instructions)
                    
                    # Create one-off program with the chosen signature
                    class DynamicEntityExtractor(dspy.Module):
                        def __init__(self, sig):
                            super().__init__()
                            self.predict = dspy.Predict(sig)
                        def forward(self, text):
                            return self.predict(content_text=text).extracted_entities

                    program = DynamicEntityExtractor(signature)
                    return program(text=text)
            
            extracted = await anyio.to_thread.run_sync(run_extraction)
            
            # Convert to dictionary format
            entities = []
            for entity in extracted.entities:
                entities.append({
                    'name': entity.name,
                    'type': entity.type,
                    'description': entity.description
                })
            
            logger.info(f"Extracted {len(entities)} entities from document {document_id or 'unknown'}")
            return entities
            
        except Exception as e:
            logger.error(f"Error extracting entities from document {document_id}: {str(e)}")
            return []


# Global service instance
_dspy_entity_service: Optional[DspyEntityService] = None


def get_dspy_entity_service() -> DspyEntityService:
    """Get the global DSPy entity service instance"""
    global _dspy_entity_service
    if _dspy_entity_service is None:
        _dspy_entity_service = DspyEntityService()
    return _dspy_entity_service


def initialize_dspy_entity_service(api_key: Optional[str] = None) -> DspyEntityService:
    """Initialize the global DSPy entity service instance"""
    global _dspy_entity_service
    _dspy_entity_service = DspyEntityService(api_key)
    return _dspy_entity_service

