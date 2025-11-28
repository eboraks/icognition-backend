"""
DSPy-based content extraction service for iCognition WITHOUT entity extraction
Uses DSPy with Google Gemini models for faster structured content extraction
"""

import os
from typing import Optional, Dict, Any
import dspy
from datetime import datetime

from app.core.config import settings
from app.utils.logging import get_logger
from app.services.dspy_models_no_entities import ContentExtractNoEntities
from app.models import Document
from app.utils.text_utils import extract_text_from_html

logger = get_logger(__name__)


# --- 1. Define the DSPy Signature WITHOUT entity extraction ---
class ExtractContentNoEntities(dspy.Signature):
    """
You are an expert content analysis engine. Your sole task is to analyze the 
provided text and return a valid JSON object that conforms to the 
ContentExtract Pydantic model WITHOUT extracting entities.

Do not provide any conversational text, apologies, or explanations outside 
of the JSON.

### JSON Generation Rules:

1.  **Skip Entity Extraction:** Do NOT extract entities. Focus only on:
    - Title extraction
    - Summary generation
    - Key takeaways
    - Analysis metadata (objectivity, tone, intent)

2.  **Paywalls:** If content is limited, fill `access_notes` with 
    'Full analysis is limited; content is behind a paywall.'
3.  **Opinion Pieces:** Set `objectivity` correctly (e.g., 'Subjective (Opinion)').
4.  **Social Media:** Set `source_type` to 'Social Media Post'.
5.  **Multi-Topic:** Ensure `key_takeaways` covers all topics.
"""
    
    content_text: str = dspy.InputField(
        desc="The full text of the article, blog post, or social media post."
    )
    
    extracted_data: ContentExtractNoEntities = dspy.OutputField(
        desc="The structured data extracted from the text."
    )


# --- 2. Define the DSPy Program ---
class ContentExtractorProgramNoEntities(dspy.Module):
    """DSPy program for content extraction WITHOUT entity extraction"""
    
    def __init__(self):
        super().__init__()
        # Use dspy.Predict with the signature
        self.predict = dspy.Predict(ExtractContentNoEntities)

    def forward(self, text):
        result = self.predict(content_text=text)
        return result.extracted_data


class DspyExtractionServiceNoEntities:
    """
    Service for extracting structured content using DSPy and Google Gemini models.
    This version excludes entity extraction for faster processing.
    """
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize the DSPy extraction service
        
        Args:
            api_key: Google API key. If None, uses settings.GOOGLE_API_KEY
        """
        self.api_key = api_key or settings.GOOGLE_API_KEY
        if not self.api_key:
            raise ValueError("Google API key is required for DSPy extraction")
        
        # Configure DSPy with Google Gemini
        # Use dspy.LM with gemini/ prefix as per DSPy documentation
        gemini_model_name = settings.GEMINI_FLASH_MODEL.replace("models/", "")
        self.lm = dspy.LM(
            f'gemini/{gemini_model_name}',
            api_key=self.api_key
        )
        
        dspy.configure(lm=self.lm)
        
        # Initialize the extractor program
        self.program = ContentExtractorProgramNoEntities()
        
        logger.info("DspyExtractionServiceNoEntities initialized successfully")
    
    def extract_content(
        self,
        text: str,
        model_name: str
    ) -> ContentExtractNoEntities:
        """
        Extract structured content from text
        
        Args:
            text: The content text to extract from
            model_name: The Gemini model to use (flash or flash_lite)
            
        Returns:
            ContentExtractNoEntities object with structured data
        """
        try:
            text = extract_text_from_html(text)
            if not text:
                raise ValueError("No readable content provided for extraction")
            
            logger.info(f"Starting content extraction (NO ENTITIES) with model: {model_name}")
            
            # Switch model if needed by creating a new LM instance
            if model_name == "flash_lite":
                gemini_model_name = settings.GEMINI_FLASH_LITE_MODEL.replace("models/", "")
            else:
                gemini_model_name = settings.GEMINI_FLASH_MODEL.replace("models/", "")
            
            self.lm = dspy.LM(
                f'gemini/{gemini_model_name}',
                api_key=self.api_key
            )
            dspy.configure(lm=self.lm)
            
            # Run extraction
            extracted_content = self.program(text=text)
            
            logger.info(f"Content extraction completed successfully (NO ENTITIES)")
            return extracted_content
            
        except Exception as e:
            logger.error(f"Error during content extraction: {str(e)}")
            raise
    
    def extract_from_document(
        self,
        document: Document,
        model_name: str
    ) -> ContentExtractNoEntities:
        """
        Extract structured content from a Document object
        
        Args:
            document: Document object from database
            model_name: The Gemini model to use (flash or flash_lite)
            
        Returns:
            ContentExtractNoEntities object with structured data
        """
        if not document.content:
            raise ValueError("Document has no content to extract")
        
        text = extract_text_from_html(document.content)
        if not text:
            raise ValueError("Document has no readable content to extract")
        return self.extract_content(text, model_name)


# Global service instance
_dspy_service_no_entities: Optional[DspyExtractionServiceNoEntities] = None


def get_dspy_service_no_entities() -> DspyExtractionServiceNoEntities:
    """Get the global DSPy extraction service instance (NO ENTITIES)"""
    global _dspy_service_no_entities
    if _dspy_service_no_entities is None:
        _dspy_service_no_entities = DspyExtractionServiceNoEntities()
    return _dspy_service_no_entities


def initialize_dspy_service_no_entities(api_key: Optional[str] = None) -> DspyExtractionServiceNoEntities:
    """Initialize the global DSPy service instance (NO ENTITIES)"""
    global _dspy_service_no_entities
    _dspy_service_no_entities = DspyExtractionServiceNoEntities(api_key)
    return _dspy_service_no_entities

