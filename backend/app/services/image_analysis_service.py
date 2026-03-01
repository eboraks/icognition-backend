import os
import base64
import httpx
import asyncio
from typing import List, Dict, Any, Optional
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage
from dotenv import load_dotenv

from app.utils.logging import get_logger
from app.utils.langfuse_worker import get_langfuse_handler

load_dotenv()
logger = get_logger(__name__)

class ImageAnalysisService:
    """
    Service for downloading images and generating semantic descriptions
    using Google Gemini Vision capabilities.
    """
    def __init__(self):
        self.api_key = os.getenv("GOOGLE_API_KEY")
        self.llm_model_name = os.getenv("GEMINI_FLASH_MODEL", "gemini-1.5-flash")
        
        if not self.api_key:
            logger.error("GOOGLE_API_KEY not found! Image analysis will fail.")
            
        self.llm = ChatGoogleGenerativeAI(model=self.llm_model_name, google_api_key=self.api_key)
        logger.info(f"ImageAnalysisService initialized with model {self.llm_model_name}")

    async def analyze_images(self, image_urls: List[str]) -> Dict[str, str]:
        """
        Download multiple images parallelly and analyze them with Gemini multimodal.
        Returns a dictionary mapping image URLs to their descriptions.
        """
        if not image_urls:
            return {}
            
        # De-duplicate URLs
        unique_urls = list(dict.fromkeys(image_urls))
        logger.info(f"Analyzing {len(unique_urls)} images...")
        
        results = {}
        
        # We process them concurrently to save time
        async def process_single_image(url: str):
            try:
                # Download the image
                async with httpx.AsyncClient(timeout=15.0) as client:
                    response = await client.get(url, headers={"User-Agent": "iCognition-ImageAnalyzer/1.0"})
                    response.raise_for_status()
                    image_data = response.content
                    content_type = response.headers.get("content-type", "image/jpeg")
                
                # Check if it's actually an image
                if not content_type.startswith("image/"):
                    logger.warning(f"URL {url} returned non-image content type: {content_type}")
                    return url, ""
                    
                # Encode to base64
                image_b64 = base64.b64encode(image_data).decode("utf-8")
                
                # Send to Gemini for multimodal analysis
                message = HumanMessage(
                    content=[
                        {
                            "type": "text",
                            "text": "Describe this image in detail. Focus on: what is depicted, any text visible in the image, the apparent message or meaning, and the artistic style or context. Be concise but thorough. If it is just a generic logo, say 'Logo'. If it's a person's avatar, say 'Avatar of a person'."
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{content_type};base64,{image_b64}"
                            }
                        }
                    ]
                )
                
                lf_handler = get_langfuse_handler()
                callbacks = [lf_handler] if lf_handler else []
                
                result = await self.llm.ainvoke(
                    [message],
                    config={"callbacks": callbacks}
                )
                
                description = result.content if hasattr(result, 'content') else str(result)
                
                # Filter out obvious noise descriptions if the prompt instruction wasn't enough
                lower_desc = description.lower()
                if "logo" in lower_desc and len(description) < 20:
                    description = "[Logo]"
                elif "avatar" in lower_desc and len(description) < 30:
                    description = "[Avatar]"
                    
                logger.debug(f"Successfully analyzed image: {url[:80]}...")
                return url, description
                
            except Exception as e:
                logger.error(f"Error analyzing image {url}: {str(e)}")
                return url, f"[Image analysis failed: {str(e)[:50]}]"

        # Create tasks for all unique URLs
        tasks = [process_single_image(url) for url in unique_urls]
        completed = await asyncio.gather(*tasks)
        
        for url, desc in completed:
            if desc:  # Only keep non-empty descriptions
                results[url] = desc
                
        return results

# Singleton instance
_image_analysis_service: Optional[ImageAnalysisService] = None

def get_image_analysis_service() -> ImageAnalysisService:
    global _image_analysis_service
    if _image_analysis_service is None:
        _image_analysis_service = ImageAnalysisService()
    return _image_analysis_service
