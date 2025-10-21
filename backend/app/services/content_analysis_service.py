"""
Simple Content Analysis Service for document summarization and bullet point extraction
"""

import json
import re
from typing import Optional, Dict, Any, List
from datetime import datetime
from pydantic import BaseModel, Field

from app.services.gemini_service import get_gemini_service, GeminiModel, GeminiConfig
from app.log import get_logger

logger = get_logger(__name__)


class DocumentSummary(BaseModel):
    """Structured output for document summary"""
    summary: str = Field(description="A concise 2-3 sentence summary of the document content")


class DocumentBulletPoints(BaseModel):
    """Structured output for document bullet points"""
    bullet_points: List[str] = Field(
        description="A list of 4-6 key bullet points summarizing the main topics",
        min_items=4,
        max_items=6
    )


class ContentAnalysisService:
    """
    Simple service for content analysis using Gemini AI.
    Replaces the complex ChatHandler with direct API calls for summarization and bullet points.
    """
    
    def __init__(self):
        """Initialize the content analysis service"""
        self.gemini_service = get_gemini_service()
        logger.info("ContentAnalysisService initialized")
    
    async def analyze_document_content(
        self,
        content: str,
        title: Optional[str] = None,
        url: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Analyze document content to generate summary and bullet points
        
        Args:
            content: Document content (clean text or HTML)
            title: Optional document title
            url: Optional document URL
            
        Returns:
            Dictionary containing:
            - summary: Document summary (ai_is_about)
            - bullet_points: List of key bullet points (ai_bullet_points)
            - analysis_timestamp: When analysis was performed
        """
        if not content or not content.strip():
            raise ValueError("Content cannot be empty")
        
        logger.info(f"Starting content analysis for document: {title or 'Untitled'}")
        
        try:
            # Clean the content if it's HTML
            clean_content = self._clean_content(content)
            
            # Generate summary and bullet points in parallel
            summary_task = self._generate_summary(clean_content, title)
            bullet_points_task = self._generate_bullet_points(clean_content, title)
            
            summary_result = await summary_task
            bullet_points_result = await bullet_points_task
            
            result = {
                'summary': summary_result,
                'bullet_points': bullet_points_result,
                'analysis_timestamp': datetime.utcnow(),
                'content_length': len(clean_content),
                'title': title,
                'url': url
            }
            
            logger.info(f"Content analysis completed successfully for: {title or 'Untitled'}")
            return result
            
        except Exception as e:
            logger.error(f"Error analyzing document content: {str(e)}")
            raise
    
    async def _generate_summary(
        self,
        content: str,
        title: Optional[str] = None
    ) -> str:
        """
        Generate a concise summary of the document content
        
        Args:
            content: Clean document content
            title: Optional document title
            
        Returns:
            Summary string
        """
        # Create a focused prompt for summarization
        prompt_parts = [
            "Please provide a concise summary of the following content.",
            "The summary should be 2-3 sentences that capture the main points and key information.",
            "Focus on the most important ideas and avoid unnecessary details."
        ]
        
        if title:
            prompt_parts.append(f"Title: {title}")
        
        prompt_parts.extend([
            "",
            "Content:",
            content[:4000]  # Limit content length for API efficiency
        ])
        
        prompt = "\n".join(prompt_parts)
        
        try:
            # Use Gemini Flash for fast summarization with structured output
            config = GeminiConfig(
                temperature=0.3,
                max_output_tokens=200,
                response_mime_type="application/json",
                response_schema=DocumentSummary
            )
            
            result = await self.gemini_service.generate_content(
                prompt=prompt,
                model=GeminiModel.FLASH,
                config=config
            )
            
            # Parse structured response
            summary_data = json.loads(result['content'])
            summary = summary_data['summary'].strip()
            logger.debug(f"Generated summary: {summary[:100]}...")
            return summary
            
        except Exception as e:
            logger.error(f"Error generating summary: {str(e)}")
            # Fallback to a simple truncation if AI fails
            return content[:200] + "..." if len(content) > 200 else content
    
    async def _generate_bullet_points(
        self,
        content: str,
        title: Optional[str] = None
    ) -> List[str]:
        """
        Generate key bullet points from the document content
        
        Args:
            content: Clean document content
            title: Optional document title
            
        Returns:
            List of bullet point strings
        """
        # Create a focused prompt for bullet points
        prompt_parts = [
            "Please extract the key points from the following content.",
            "Return exactly 6 bullet points that capture the most important information.",
            "Each bullet point should be concise but informative.",
            "Format your response as a JSON array of strings."
        ]
        
        if title:
            prompt_parts.append(f"Title: {title}")
        
        prompt_parts.extend([
            "",
            "Content:",
            content[:4000]  # Limit content length for API efficiency
        ])
        
        prompt = "\n".join(prompt_parts)
        
        try:
            # Use Gemini Flash for bullet point extraction with structured output
            config = GeminiConfig(
                temperature=0.2,
                max_output_tokens=500,
                response_mime_type="application/json",
                response_schema=DocumentBulletPoints
            )
            
            result = await self.gemini_service.generate_content(
                prompt=prompt,
                model=GeminiModel.FLASH,
                config=config
            )
            
            # Parse structured response
            bullet_data = json.loads(result['content'])
            bullet_points = bullet_data['bullet_points']
            
            # Clean and validate bullet points
            cleaned_points = []
            for point in bullet_points:
                if isinstance(point, str) and point.strip():
                    cleaned_points.append(point.strip())
            
            # Ensure we have at least 4 points
            while len(cleaned_points) < 4:
                cleaned_points.append("Additional information available in the full document.")
            
            logger.debug(f"Generated {len(cleaned_points)} bullet points")
            return cleaned_points[:6]  # Return max 6 points
            
        except Exception as e:
            logger.error(f"Error generating bullet points: {str(e)}")
            # Fallback to simple content extraction
            return self._extract_fallback_bullet_points(content)
    
    def _clean_content(self, content: str) -> str:
        """
        Clean content by removing HTML tags and normalizing whitespace
        
        Args:
            content: Raw content (may be HTML or plain text)
            
        Returns:
            Cleaned text content
        """
        # Check if content looks like HTML
        if '<' in content and '>' in content:
            # Simple HTML tag removal
            # Remove HTML tags
            clean_text = re.sub(r'<[^>]+>', '', content)
            # Normalize whitespace
            clean_text = re.sub(r'\s+', ' ', clean_text)
            return clean_text.strip()
        else:
            # Already clean text, just normalize whitespace
            return re.sub(r'\s+', ' ', content).strip()
    
    def _extract_bullet_points_from_text(self, text: str) -> List[str]:
        """
        Extract bullet points from text response when JSON parsing fails
        
        Args:
            text: Text response from AI
            
        Returns:
            List of bullet points
        """
        # Look for bullet points in various formats
        bullet_patterns = [
            r'•\s*([^\n]+)',
            r'-\s*([^\n]+)',
            r'\*\s*([^\n]+)',
            r'\d+\.\s*([^\n]+)'
        ]
        
        bullet_points = []
        for pattern in bullet_patterns:
            matches = re.findall(pattern, text, re.MULTILINE)
            for match in matches:
                if match.strip() and len(match.strip()) > 10:  # Minimum length
                    bullet_points.append(match.strip())
        
        # If we found bullet points, return them
        if bullet_points:
            return bullet_points[:6]
        
        # Fallback: split by sentences and take first 6
        sentences = re.split(r'[.!?]+', text)
        return [s.strip() for s in sentences[:6] if s.strip() and len(s.strip()) > 10]
    
    def _extract_fallback_bullet_points(self, content: str) -> List[str]:
        """
        Extract fallback bullet points when AI generation fails
        
        Args:
            content: Document content
            
        Returns:
            List of fallback bullet points
        """
        # Split content into sentences
        sentences = re.split(r'[.!?]+', content)
        
        # Filter and clean sentences
        bullet_points = []
        for sentence in sentences:
            sentence = sentence.strip()
            if len(sentence) > 20 and len(sentence) < 200:  # Reasonable length
                bullet_points.append(sentence)
        
        # Return up to 6 points
        return bullet_points[:6] if bullet_points else ["Content analysis temporarily unavailable."]


# Global service instance
_content_analysis_service: Optional[ContentAnalysisService] = None


def get_content_analysis_service() -> ContentAnalysisService:
    """Get the global content analysis service instance"""
    global _content_analysis_service
    if _content_analysis_service is None:
        _content_analysis_service = ContentAnalysisService()
    return _content_analysis_service


def initialize_content_analysis_service() -> ContentAnalysisService:
    """Initialize the global content analysis service instance"""
    global _content_analysis_service
    _content_analysis_service = ContentAnalysisService()
    return _content_analysis_service