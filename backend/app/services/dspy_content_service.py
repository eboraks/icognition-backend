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
from bs4 import BeautifulSoup
from app.services.image_analysis_service import get_image_analysis_service

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
    - Create a concise, structured summary in markdown (`markdown_content`) that captures the key points, arguments, and conclusions. Aim for 20-30% of the original length. Use headings, bullet points, or short paragraphs as appropriate — do NOT reproduce the full article text verbatim.
    - Analyze objectivity, tone, and intent
    - Identify URLs of content-relevant images (exclude ads, icons, tracking pixels)

2.  **Links and URLs:**
    - **IMPORTANT**: When the content contains links or URLs (especially in social media posts), 
      explicitly include the full URL in both the summary and relevant sections of the markdown content.
    - If a link is the subject of a post (e.g., "Check out this article: [link]"), 
      include the complete URL in the summary and in the markdown content.
    - For social media posts that reference external articles, always include the 
      article URL in the summary and markdown content.
    - Extract URLs from anchor tags, plain text URLs, or shortened links mentioned in the content.
    - Include the full URL as plain text in the summary and in the markdown content (the frontend will format them as links).

3.  **Images:**
    - If the content contains `[Image Description: ...]`, seamlessly incorporate this visual context into the markdown summary or explanation where relevant. Do not simply list the images; weave their meaning into the narrative to provide a complete understanding of the content.

4.  **Paywalls:** If content is limited, fill `access_notes` with 
    'Full analysis is limited; content is behind a paywall.'
5.  **Opinion Pieces:** Set `objectivity` correctly (e.g., 'Subjective (Opinion)').
6.  **Social Media:** Set `source_type` to 'Social Media Post'.
7.  **Multi-Topic:** Ensure `markdown_content` covers all topics accurately.
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
    
    def __init__(self, instructions: Optional[str] = None):
        super().__init__()
        if instructions:
            # Dynamically update signature instructions from DB
            self.predict = dspy.Predict(ExtractContent.with_instructions(instructions))
        else:
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

        gemini_model_name = settings.GEMINI_FLASH_LITE_MODEL.replace("models/", "")
        self.model_name = f'gemini/{gemini_model_name}'

        # Create the LM client once at init — reused across all extraction calls.
        # max_tokens=8192: Gemini Flash Lite supports 8192 output tokens; DSPy defaults to 4000
        # which causes truncation on long articles, breaking the JSON output.
        self.lm = dspy.LM(self.model_name, api_key=self.api_key, max_tokens=8192)

        logger.info("DspyContentService initialized successfully with Flash Lite model")
    
    async def _get_db_instructions(self) -> Optional[str]:
        """Fetch DSPy instructions from YAML"""
        from app.services.prompt_service import get_prompt

        try:
            db_prompt = get_prompt("DSPy: Content Extraction")
            if db_prompt:
                instructions = ""
                if db_prompt.system_prompt:
                    instructions += db_prompt.system_prompt + "\n\n"
                instructions += db_prompt.user_prompt
                return instructions
        except Exception as e:
            logger.warning(f"Failed to fetch DSPy instructions from YAML: {e}")
        return None

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
        
        # Fetch instructions from DB if available
        instructions = await self._get_db_instructions()
        
        try:
            # --- Inline Image Processing ---
            # Try to parse HTML to extract and describe images
            image_descriptions_map = {}
            filtered_html = content
            valid_urls = []

            if "<img" in content.lower():
                try:
                    soup = BeautifulSoup(content, 'html.parser')
                    img_tags = soup.find_all('img')
                    
                    # Filter images by heuristics
                    for img in img_tags:
                        src = img.get('src')
                        if not src or src.startswith('data:'):
                            continue
                            
                        # Basic filtering heuristics
                        alt = (img.get('alt') or '').lower()
                        src_lower = src.lower()
                        width = img.get('width')
                        height = img.get('height')
                        
                        # Skip tiny images or typical icons/avatars
                        if width and str(width).isdigit() and int(width) < 100:
                            continue
                        if height and str(height).isdigit() and int(height) < 100:
                            continue
                        if any(kw in src_lower or kw in alt for kw in ['icon', 'avatar', 'logo', 'spinner', 'tracker', 'pixel']):
                            continue
                            
                        valid_urls.append(src)
                        
                    # Limit to top 5 images to save LLM tokens/time
                    valid_urls = valid_urls[:5]
                    
                    if valid_urls:
                        logger.info(f"Extracting meanings for {len(valid_urls)} inline images in document")
                        image_service = get_image_analysis_service()
                        image_descriptions_map = await image_service.analyze_images(valid_urls)
                        
                        # Replace img tags with semantic text markers
                        for img in img_tags:
                            src = img.get('src')
                            if src in image_descriptions_map:
                                desc = image_descriptions_map[src]
                                # Create a text node to replace the image
                                new_tag = soup.new_tag("p")
                                new_tag.string = f"[Image Description: {desc}]"
                                img.replace_with(new_tag)
                        
                        filtered_html = str(soup)
                except Exception as img_err:
                    logger.warning(f"Failed to extract inline images: {img_err}")
                    # Fallback to original content
                    filtered_html = content

            # Use anyio.to_thread.run_sync to offload synchronous DSPy calls
            # self.lm is created once at init — no repeated instantiation cost.
            def run_extraction():
                with dspy.context(lm=self.lm):
                    program = ContentExtractorProgram(instructions=instructions)
                    return program(text=filtered_html)
            
            extracted = await anyio.to_thread.run_sync(run_extraction)
            
            # Prepare result in compatible format with old service
            # Note: URLs are returned as plain text - frontend will handle link formatting
            result = {
                'summary': None,
                'markdown_content': extracted.markdown_content,
                'image_urls': valid_urls,
                'extracted_content': {
                    'title': extracted.title,
                    'source_type': extracted.source_type,
                    'summary': None,
                    'markdown_content': extracted.markdown_content,
                    'image_urls': valid_urls,
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
            
            # self.lm is created once at init — no repeated instantiation cost.
            with dspy.context(lm=self.lm):
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

