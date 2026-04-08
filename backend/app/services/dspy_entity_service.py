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
from app.services.dspy_models_entities_only import EntityExtractionResult, Entity, EntityRelationshipResult
from app.models import Document
from app.utils.text_utils import extract_text_from_html
from app.services.prompt_service import get_prompt
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
    - IGNORE: photographers, photo credits, dates, publication mastheads
    - INCLUDE: Main people, organizations, locations, events, concepts, products, technologies
    - INCLUDE article authors:
      - Individual authors (e.g. "Jane Smith") → type: person
      - Editorial boards, newsroom groups, collective bylines (e.g. "The Editorial Board", "WSJ Staff") → type: organization

2.  **Entity Types:**
    - person: Key individuals mentioned, including individual article authors
    - organization: Companies, institutions, government bodies, editorial boards, collective author groups
    - institution: Academic or governmental institutions
    - location: Important places
    - event: Specific events or happenings
    - technology: Technologies, frameworks, or technical concepts
    - product: Products or services
    - science: Scientific disciplines, theories, research fields (e.g. "Quantum Physics", "Machine Learning")
    - medical_condition: Diseases, disorders, symptoms, health conditions (e.g. "Breast Cancer", "Diabetes")
    - organism: Biological species, animals, plants, microorganisms (e.g. "Macaca Mulatta", "E. Coli", "Redwood")
    - regulation: Laws, policies, standards, treaties (e.g. "GDPR", "Paris Agreement")
    - financial: Financial instruments, markets, economic concepts (e.g. "S&P 500", "Inflation")
    - creative_work: Books, films, artworks, publications (e.g. "The Great Gatsby")
    - concept: Abstract ideas, principles, or themes that don't fit above types (e.g. "Democracy", "Supply Chain")

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


# --- DSPy Signature for Relationship Extraction ---
class ExtractEntityRelationships(dspy.Signature):
    """
You are an expert knowledge graph builder. Given a list of entities already extracted from a document
and the original document text, identify meaningful directed relationships between those entities.

### Rules:
1. Only use entity names from the provided list — do not invent new entities.
2. **Factual accuracy is critical.** Each relationship must be EXPLICITLY stated or directly implied
   in the document text. Do NOT infer, assume, or hallucinate relationships. If the text says
   "Elon Musk made a deal with Samsung for chips", the relationship is "made_deal_with" — NOT "acquired".
3. Use short, NEUTRAL snake_case labels. Avoid editorialized or sensational language.
   - GOOD: advocates_military_action, seeks_to_undermine, competes_with, trades_with
   - BAD: wants_to_bomb, goal_to_destroy, opposes_helping
4. **Direction matters.** The from_entity is the SUBJECT performing the action; the to_entity is the OBJECT.
   - "Pete Hegseth briefed President Trump" → from: Pete Hegseth, to: President Trump, type: briefed
   - NOT the reverse.
5. Use general, reusable relationship types that could apply across documents:
   - GOOD: leads, member_of, headquartered_in, author_of, competes_with, allied_with, trades_with
   - BAD: commented_on, mentioned, part_of (when meaning "citizen of" or "works for government of")
6. If the article has an identifiable author or editorial board among the entities, create an
   "author_of" relationship from the author entity to the main subject/topic entity.
7. Do NOT create redundant bidirectional edges. If A trades_with B, do not also add B trades_with A.
   Pick the more natural direction.
8. Extract up to 20 relationships. Prefer high-confidence, clearly-stated relationships.
   Skip weak or trivial connections — quality over quantity.
"""

    entity_names: str = dspy.InputField(
        desc="Comma-separated list of entity names extracted from the document."
    )
    content_text: str = dspy.InputField(
        desc="The document text from which relationships should be extracted."
    )
    extracted_relationships: EntityRelationshipResult = dspy.OutputField(
        desc="Directed relationships between the provided entities."
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

        gemini_model_name = settings.GEMINI_FLASH_LITE_MODEL.replace("models/", "")
        self.model_name = f'gemini/{gemini_model_name}'

        # Create the LM client once at init — reused across all extraction calls.
        # max_tokens=8192: DSPy defaults to 4000 which truncates large entity lists.
        self.lm = dspy.LM(self.model_name, api_key=self.api_key, max_tokens=8192)

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
        
        # Load prompt from YAML
        custom_instructions = None
        try:
            db_prompt = get_prompt("entity_extraction")
            if db_prompt and db_prompt.user_prompt:
                logger.info("Using custom entity extraction prompt from YAML")
                custom_instructions = db_prompt.user_prompt
        except Exception as e:
            logger.warning(f"Error loading prompt from YAML, falling back to hardcoded: {e}")

        logger.info(f"Starting DSPy entity extraction for document {document_id or 'unknown'}")
        
        try:
            # Use anyio.to_thread.run_sync to offload synchronous DSPy calls.
            # self.lm is created once at init — no repeated instantiation cost.
            def run_extraction():
                with dspy.context(lm=self.lm):
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


    async def extract_relationships_from_entities(
        self,
        entity_names: List[str],
        content: str,
        document_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Extract relationships between already-extracted entities using DSPy.

        Args:
            entity_names: List of entity names extracted from the document.
            content: The original document text.
            document_id: Optional document ID for logging.

        Returns:
            List of dicts with keys: from_entity, to_entity, relationship_type
        """
        if len(entity_names) < 2:
            logger.info(f"Not enough entities ({len(entity_names)}) to extract relationships for doc {document_id}")
            return []

        text = extract_text_from_html(content)
        if not text:
            return []

        names_str = ", ".join(entity_names)
        logger.info(f"Extracting relationships for {len(entity_names)} entities in doc {document_id}")

        try:
            def run_extraction():
                with dspy.context(lm=self.lm):
                    predictor = dspy.Predict(ExtractEntityRelationships)
                    result = predictor(entity_names=names_str, content_text=text)
                    return result.extracted_relationships

            extracted = await anyio.to_thread.run_sync(run_extraction)

            relationships = [
                {
                    "from_entity": r.from_entity,
                    "to_entity": r.to_entity,
                    "relationship_type": r.relationship_type,
                }
                for r in extracted.relationships
            ]
            logger.info(f"Extracted {len(relationships)} relationships for doc {document_id}")
            return relationships

        except Exception as e:
            logger.error(f"Error extracting relationships for doc {document_id}: {e}")
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

