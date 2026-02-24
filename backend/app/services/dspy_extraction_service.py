"""
DSPy-based content extraction service for iCognition
Uses DSPy with Google Gemini models for structured content extraction
"""

import os
from typing import Optional, Dict, Any
import dspy
from datetime import datetime

from app.core.config import settings
from app.utils.logging import get_logger
from app.services.dspy_models import ContentExtract
from app.models import Document
from app.utils.text_utils import extract_text_from_html
from app.utils.langfuse_worker import setup_dspy_instrumentation

logger = get_logger(__name__)


# --- 1. Define the DSPy Signature ---
class ExtractContent(dspy.Signature):
    """
You are an expert content analysis engine. Your sole task is to analyze the 
provided text and return a valid JSON object that conforms to the 
ContentExtract Pydantic model.

Do not provide any conversational text, apologies, or explanations outside 
of the JSON.

### JSON Generation Rules:

1.  **key_entities:** Up to TEN MOST IMPORTANT entities to the text. This MUST be a list of objects. For each
    important organization, person, topic... create an object with:
    - "name": The name of the entity (e.g., "Tesla", "Jake W. Simons").
    - "type": One of "organization", "person", "topic", "location"....
    - "description": A brief, 1-sentence description of the entity's 
      role or relevance in the text (e.g., "The company recalling Cybertrucks" 
      or "The user who posted the social media message").

2.  **Paywalls:** If content is limited, fill `access_notes` with 
    'Full analysis is limited; content is behind a paywall.'
3.  **Opinion Pieces:** Set `objectivity` correctly (e.g., 'Subjective (Opinion)').
4.  **Social Media:** Set `source_type` to 'Social Media Post'.
5.  **Multi-Topic:** Ensure `key_takeaways` covers all topics.
"""
    
    content_text: str = dspy.InputField(
        desc="The full text of the article, blog post, or social media post."
    )
    
    extracted_data: ContentExtract = dspy.OutputField(
        desc="The structured data extracted from the text."
    )


# --- 2. Define the DSPy Program ---
class ContentExtractorProgram(dspy.Module):
    """DSPy program for content extraction"""
    
    def __init__(self):
        super().__init__()
        # Use dspy.Predict with the signature
        self.predict = dspy.Predict(ExtractContent)

    def forward(self, text):
        result = self.predict(content_text=text)
        return result.extracted_data


class DspyExtractionService:
    """
    Service for extracting structured content using DSPy and Google Gemini models
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
        
        # Setup instrumentation (Langfuse/OpenInference)
        setup_dspy_instrumentation()

        dspy.configure(lm=self.lm)
        
        # Initialize the extractor program
        self.program = ContentExtractorProgram()
        
        logger.info("DspyExtractionService initialized successfully")
    
    def extract_content(
        self,
        text: str,
        model_name: str
    ) -> ContentExtract:
        """
        Extract structured content from text
        
        Args:
            text: The content text to extract from
            model_name: The Gemini model to use (flash or flash_lite)
            
        Returns:
            ContentExtract object with structured data
        """
        try:
            text = extract_text_from_html(text)
            if not text:
                raise ValueError("No readable content provided for extraction")
            
            logger.info(f"Starting content extraction with model: {model_name}")
            
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
            
            logger.info(f"Content extraction completed successfully")
            return extracted_content
            
        except Exception as e:
            logger.error(f"Error during content extraction: {str(e)}")
            raise
    
    def extract_from_document(
        self,
        document: Document,
        model_name: str
    ) -> ContentExtract:
        """
        Extract structured content from a Document object
        
        Args:
            document: Document object from database
            model_name: The Gemini model to use (flash or flash_lite)
            
        Returns:
            ContentExtract object with structured data
        """
        if not document.content:
            raise ValueError("Document has no content to extract")
        
        text = extract_text_from_html(document.content)
        if not text:
            raise ValueError("Document has no readable content to extract")
        return self.extract_content(text, model_name)


# Global service instance
_dspy_service: Optional[DspyExtractionService] = None


def get_dspy_service() -> DspyExtractionService:
    """Get the global DSPy extraction service instance"""
    global _dspy_service
    if _dspy_service is None:
        _dspy_service = DspyExtractionService()
    return _dspy_service


def initialize_dspy_service(api_key: Optional[str] = None) -> DspyExtractionService:
    """Initialize the global DSPy service instance"""
    global _dspy_service
    _dspy_service = DspyExtractionService(api_key)
    return _dspy_service

