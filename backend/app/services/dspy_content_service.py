"""
DSPy-based content analysis service for iCognition
Uses DSPy with Google Gemini Flash Lite for fast structured content extraction
Replaces the legacy ContentAnalysisService
"""

from typing import Optional, Dict, Any
import dspy
import anyio
from datetime import datetime

from app.core.config import settings
from app.utils.logging import get_logger
from app.services.dspy_models_no_entities import ContentExtractNoEntities
from app.models import Document

logger = get_logger(__name__)


# --- DSPy Signature for Content Extraction ---
class ExtractContent(dspy.Signature):
    """
You are an expert content analysis engine. Your sole task is to analyze the 
provided text and return a valid JSON object that conforms to the 
ContentExtract Pydantic model.

Do not provide any conversational text, apologies, or explanations outside 
of the JSON.

### JSON Generation Rules:

1.  **Focus on Quality:**
    - Extract accurate title
    - Generate a neutral, informative summary (one paragraph)
    - Identify 4-6 key takeaways (most important facts/arguments)
    - Analyze objectivity, tone, and intent

2.  **Links and URLs:**
    - **IMPORTANT**: When the content contains links or URLs (especially in social media posts), 
      explicitly include the full URL in both the summary and relevant bullet points.
    - If a link is the subject of a post (e.g., "Check out this article: [link]"), 
      include the complete URL in the summary and at least one bullet point.
    - For social media posts that reference external articles, always include the 
      article URL in the summary and key takeaways.
    - Extract URLs from anchor tags, plain text URLs, or shortened links mentioned in the content.
    - Include the full URL as plain text in the summary and key takeaways (the frontend will format them as links).

3.  **Paywalls:** If content is limited, fill `access_notes` with 
    'Full analysis is limited; content is behind a paywall.'
4.  **Opinion Pieces:** Set `objectivity` correctly (e.g., 'Subjective (Opinion)').
5.  **Social Media:** Set `source_type` to 'Social Media Post'.
6.  **Multi-Topic:** Ensure `key_takeaways` covers all topics.
"""
    
    content_text: str = dspy.InputField(
        desc="The full text of the article, blog post, or social media post."
    )
    
    extracted_data: ContentExtractNoEntities = dspy.OutputField(
        desc="The structured data extracted from the text."
    )


# --- DSPy Program ---
class ContentExtractorProgram(dspy.Module):
    """DSPy program for content extraction"""
    
    def __init__(self):
        super().__init__()
        self.predict = dspy.Predict(ExtractContent)

    def forward(self, text):
        result = self.predict(content_text=text)
        return result.extracted_data


class DspyContentService:
    """
    Service for extracting structured content using DSPy and Google Gemini Flash Lite.
    Replaces ContentAnalysisService with faster, more structured extraction.
    """
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize the DSPy content service
        
        Args:
            api_key: Google API key. If None, uses settings.GOOGLE_API_KEY
        """
        self.api_key = api_key or settings.GOOGLE_API_KEY
        if not self.api_key:
            raise ValueError("Google API key is required for DSPy content extraction")
        
        # Store LM configuration but don't configure globally yet
        gemini_model_name = settings.GEMINI_FLASH_LITE_MODEL.replace("models/", "")
        self.model_name = f'gemini/{gemini_model_name}'
        
        logger.info("DspyContentService initialized successfully with Flash Lite model")
    
    async def analyze_document_content(
        self,
        content: str,
        title: Optional[str] = None,
        url: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Analyze document content using DSPy extraction.
        
        This method maintains compatibility with the old ContentAnalysisService interface
        while using the new DSPy-based extraction.
        
        Args:
            content: Document content (clean text or HTML)
            title: Optional document title
            url: Optional document URL
            
        Returns:
            Dictionary containing:
            - summary: Document summary (maps to ai_is_about)
            - bullet_points: List of key takeaways (maps to ai_bullet_points)
            - extracted_content: Full DSPy extraction result (maps to extracted_content field)
            - analysis_timestamp: When analysis was performed
        """
        if not content or not content.strip():
            raise ValueError("Content cannot be empty")
        
        logger.info(f"Starting DSPy content analysis for: {title or 'Untitled'}")
        
        try:
            # Use anyio.to_thread.run_sync to offload synchronous DSPy calls
            # This prevents blocking the event loop during LLM processing
            lm = dspy.LM(self.model_name, api_key=self.api_key)
            
            def run_extraction():
                with dspy.context(lm=lm):
                    program = ContentExtractorProgram()
                    return program(text=content)
            
            extracted = await anyio.to_thread.run_sync(run_extraction)
            
            # Prepare result in compatible format with old service
            # Note: URLs are returned as plain text - frontend will handle link formatting
            result = {
                'summary': extracted.summary,
                'bullet_points': extracted.key_takeaways,
                'extracted_content': {
                    'title': extracted.title,
                    'source_type': extracted.source_type,
                    'summary': extracted.summary,
                    'key_takeaways': extracted.key_takeaways,
                    'analysis': {
                        'objectivity': extracted.analysis.objectivity,
                        'tone': extracted.analysis.tone,
                        'intent': extracted.analysis.intent
                    },
                    'access_notes': extracted.access_notes,
                    'extraction_timestamp': datetime.utcnow().isoformat(),
                    'model': settings.GEMINI_FLASH_LITE_MODEL
                },
                'analysis_timestamp': datetime.utcnow(),
                'content_length': len(content),
                'title': title,
                'url': url
            }
            
            logger.info(f"DSPy content analysis completed successfully for: {title or 'Untitled'}")
            return result
            
        except Exception as e:
            logger.error(f"Error analyzing document content with DSPy: {str(e)}")
            raise
    
    def extract_content(
        self,
        text: str
    ) -> ContentExtractNoEntities:
        """
        Extract structured content from text (direct DSPy interface)
        
        Args:
            text: The content text to extract from
            
        Returns:
            ContentExtractNoEntities object with structured data
        """
        try:
            logger.info(f"Starting DSPy content extraction")
            
            # Use dspy.context for async task execution
            lm = dspy.LM(self.model_name, api_key=self.api_key)
            
            with dspy.context(lm=lm):
                program = ContentExtractorProgram()
                extracted_content = program(text=text)
            
            logger.info(f"DSPy content extraction completed successfully")
            return extracted_content
            
        except Exception as e:
            logger.error(f"Error during DSPy content extraction: {str(e)}")
            raise


# Global service instance
_dspy_content_service: Optional[DspyContentService] = None


def get_dspy_content_service() -> DspyContentService:
    """Get the global DSPy content service instance"""
    global _dspy_content_service
    if _dspy_content_service is None:
        _dspy_content_service = DspyContentService()
    return _dspy_content_service


def initialize_dspy_content_service(api_key: Optional[str] = None) -> DspyContentService:
    """Initialize the global DSPy content service instance"""
    global _dspy_content_service
    _dspy_content_service = DspyContentService(api_key)
    return _dspy_content_service

