"""
Content Analysis Service for AI-powered document analysis
"""

import asyncio
import json
from typing import Dict, Any, List, Optional, Union
from datetime import datetime
from dataclasses import dataclass

from app.services.gemini_service import GeminiService, GeminiModel, get_gemini_service
from app.services.prompt_utils import generate_prompt, PromptType, create_analysis_prompt
from app.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class ContentAnalysisResult:
    """Result of content analysis"""
    summary: Optional[str] = None
    key_points: Optional[List[str]] = None
    entities: Optional[List[Dict[str, Any]]] = None
    topics: Optional[List[str]] = None
    sentiment: Optional[Dict[str, Any]] = None
    language: Optional[str] = None
    quality_score: Optional[float] = None
    bullet_points: Optional[List[str]] = None
    metadata: Optional[Dict[str, Any]] = None
    analysis_timestamp: Optional[datetime] = None
    model_used: Optional[str] = None
    success: bool = False
    error: Optional[str] = None


@dataclass
class EntityExtractionResult:
    """Result of entity extraction"""
    entities: List[Dict[str, Any]]
    total_count: int
    categories: Dict[str, int]
    confidence_scores: List[float]
    analysis_timestamp: datetime
    model_used: str
    success: bool
    error: Optional[str] = None


class ContentAnalysisService:
    """
    Service for AI-powered content analysis using Gemini models
    """
    
    def __init__(self, gemini_service: Optional[GeminiService] = None):
        """
        Initialize the content analysis service
        
        Args:
            gemini_service: Gemini service instance. If None, uses global instance
        """
        self.gemini_service = gemini_service or get_gemini_service()
        logger.info("ContentAnalysisService initialized")
    
    async def analyze_document_content(
        self,
        content: str,
        analysis_types: Optional[List[str]] = None,
        model: GeminiModel = GeminiModel.FLASH,
        include_metadata: bool = True
    ) -> ContentAnalysisResult:
        """
        Perform comprehensive content analysis
        
        Args:
            content: Document content to analyze
            analysis_types: List of analysis types to perform
            model: Gemini model to use
            include_metadata: Whether to include metadata in results
            
        Returns:
            ContentAnalysisResult with analysis data
        """
        if not content or not content.strip():
            return ContentAnalysisResult(
                success=False,
                error="Content cannot be empty",
                analysis_timestamp=datetime.now()
            )
        
        try:
            # Default analysis types if not specified
            if analysis_types is None:
                analysis_types = [
                    "summary", "key_points", "entities", 
                    "topics", "sentiment", "language"
                ]
            
            logger.info(f"Starting content analysis with types: {analysis_types}")
            
            # Convert analysis types to PromptType enums
            prompt_types = []
            type_mapping = {
                'summary': PromptType.CONTENT_SUMMARY,
                'key_points': PromptType.KEY_POINTS,
                'entities': PromptType.ENTITY_EXTRACTION,
                'topics': PromptType.TOPIC_CATEGORIZATION,
                'sentiment': PromptType.SENTIMENT_ANALYSIS,
                'language': PromptType.LANGUAGE_DETECTION,
                'validation': PromptType.CONTENT_VALIDATION,
                'bullet_points': PromptType.BULLET_POINTS
            }
            
            for analysis_type in analysis_types:
                if analysis_type in type_mapping:
                    prompt_types.append(type_mapping[analysis_type])
                else:
                    logger.warning(f"Unknown analysis type: {analysis_type}")
            
            # Generate comprehensive analysis prompt
            prompt = create_analysis_prompt(
                content=content,
                analysis_types=prompt_types,
                include_metadata=include_metadata
            )
            
            # Generate analysis using Gemini
            result = await self.gemini_service.generate_content(
                prompt=prompt,
                model=model,
                use_cache=True
            )
            
            if not result['success']:
                return ContentAnalysisResult(
                    success=False,
                    error="Failed to generate analysis",
                    analysis_timestamp=datetime.now(),
                    model_used=result.get('model', 'unknown')
                )
            
            # Parse the response
            analysis_data = self._parse_analysis_response(result['content'])
            
            return ContentAnalysisResult(
                summary=analysis_data.get('summary'),
                key_points=analysis_data.get('key_points'),
                entities=analysis_data.get('entities'),
                topics=analysis_data.get('topics'),
                sentiment=analysis_data.get('sentiment'),
                language=analysis_data.get('language'),
                quality_score=analysis_data.get('quality_score'),
                bullet_points=analysis_data.get('bullet_points'),
                metadata=analysis_data.get('metadata'),
                analysis_timestamp=datetime.now(),
                model_used=result['model'],
                success=True
            )
            
        except Exception as e:
            logger.error(f"Error analyzing content: {str(e)}")
            return ContentAnalysisResult(
                success=False,
                error=str(e),
                analysis_timestamp=datetime.now()
            )
    
    async def extract_entities(
        self,
        content: str,
        model: GeminiModel = GeminiModel.FLASH
    ) -> EntityExtractionResult:
        """
        Extract named entities from content
        
        Args:
            content: Content to extract entities from
            model: Gemini model to use
            
        Returns:
            EntityExtractionResult with extracted entities
        """
        try:
            logger.info("Starting entity extraction")
            
            # Generate entity extraction prompt
            prompt = generate_prompt(
                PromptType.ENTITY_EXTRACTION,
                content
            )
            
            # Generate analysis using Gemini
            result = await self.gemini_service.generate_content(
                prompt=prompt,
                model=model,
                use_cache=True
            )
            
            if not result['success']:
                return EntityExtractionResult(
                    entities=[],
                    total_count=0,
                    categories={},
                    confidence_scores=[],
                    analysis_timestamp=datetime.now(),
                    model_used=result.get('model', 'unknown'),
                    success=False,
                    error="Failed to extract entities"
                )
            
            # Parse entity extraction response
            entities_data = self._parse_entity_response(result['content'])
            
            # Calculate statistics
            total_count = len(entities_data)
            categories = {}
            confidence_scores = []
            
            for entity in entities_data:
                category = entity.get('category', 'OTHER')
                categories[category] = categories.get(category, 0) + 1
                confidence_scores.append(entity.get('confidence', 0.0))
            
            return EntityExtractionResult(
                entities=entities_data,
                total_count=total_count,
                categories=categories,
                confidence_scores=confidence_scores,
                analysis_timestamp=datetime.now(),
                model_used=result['model'],
                success=True
            )
            
        except Exception as e:
            logger.error(f"Error extracting entities: {str(e)}")
            return EntityExtractionResult(
                entities=[],
                total_count=0,
                categories={},
                confidence_scores=[],
                analysis_timestamp=datetime.now(),
                model_used='unknown',
                success=False,
                error=str(e)
            )
    
    async def generate_summary(
        self,
        content: str,
        max_length: int = 200,
        model: GeminiModel = GeminiModel.FLASH
    ) -> str:
        """
        Generate a summary of the content
        
        Args:
            content: Content to summarize
            max_length: Maximum length of summary
            model: Gemini model to use
            
        Returns:
            Generated summary
        """
        try:
            prompt = generate_prompt(
                PromptType.CONTENT_SUMMARY,
                content,
                max_length=max_length
            )
            
            result = await self.gemini_service.generate_content(
                prompt=prompt,
                model=model,
                use_cache=True
            )
            
            if result['success']:
                return result['content'].strip()
            else:
                return "Failed to generate summary"
                
        except Exception as e:
            logger.error(f"Error generating summary: {str(e)}")
            return f"Error generating summary: {str(e)}"
    
    async def extract_key_points(
        self,
        content: str,
        max_points: int = 10,
        model: GeminiModel = GeminiModel.FLASH
    ) -> List[str]:
        """
        Extract key points from content
        
        Args:
            content: Content to extract key points from
            max_points: Maximum number of key points
            model: Gemini model to use
            
        Returns:
            List of key points
        """
        try:
            prompt = generate_prompt(
                PromptType.KEY_POINTS,
                content,
                max_points=max_points
            )
            
            result = await self.gemini_service.generate_content(
                prompt=prompt,
                model=model,
                use_cache=True
            )
            
            if result['success']:
                return self._parse_key_points(result['content'])
            else:
                return ["Failed to extract key points"]
                
        except Exception as e:
            logger.error(f"Error extracting key points: {str(e)}")
            return [f"Error extracting key points: {str(e)}"]
    
    async def analyze_sentiment(
        self,
        content: str,
        model: GeminiModel = GeminiModel.FLASH
    ) -> Dict[str, Any]:
        """
        Analyze sentiment of content
        
        Args:
            content: Content to analyze
            model: Gemini model to use
            
        Returns:
            Sentiment analysis results
        """
        try:
            prompt = generate_prompt(
                PromptType.SENTIMENT_ANALYSIS,
                content
            )
            
            result = await self.gemini_service.generate_content(
                prompt=prompt,
                model=model,
                use_cache=True
            )
            
            if result['success']:
                return self._parse_sentiment_response(result['content'])
            else:
                return {
                    "sentiment": "unknown",
                    "confidence": 0.0,
                    "error": "Failed to analyze sentiment"
                }
                
        except Exception as e:
            logger.error(f"Error analyzing sentiment: {str(e)}")
            return {
                "sentiment": "unknown",
                "confidence": 0.0,
                "error": str(e)
            }
    
    def _parse_analysis_response(self, response: str) -> Dict[str, Any]:
        """Parse comprehensive analysis response"""
        try:
            # Try to parse as JSON first
            if response.strip().startswith('{'):
                return json.loads(response)
            
            # If not JSON, try to extract structured data
            return self._extract_structured_data(response)
            
        except json.JSONDecodeError:
            logger.warning("Failed to parse analysis response as JSON")
            return self._extract_structured_data(response)
    
    def _parse_entity_response(self, response: str) -> List[Dict[str, Any]]:
        """Parse entity extraction response"""
        try:
            # Try to parse as JSON first
            if response.strip().startswith('{'):
                data = json.loads(response)
                return data.get('entities', [])
            
            # If not JSON, try to extract entities from text
            return self._extract_entities_from_text(response)
            
        except json.JSONDecodeError:
            logger.warning("Failed to parse entity response as JSON")
            return self._extract_entities_from_text(response)
    
    def _parse_key_points(self, response: str) -> List[str]:
        """Parse key points from response"""
        lines = response.split('\n')
        key_points = []
        
        for line in lines:
            line = line.strip()
            if line and (line.startswith('•') or line.startswith('-') or line.startswith('*')):
                # Remove bullet point markers
                point = line[1:].strip()
                if point:
                    key_points.append(point)
            elif line and line[0].isdigit() and '.' in line:
                # Handle numbered points
                point = line.split('.', 1)[1].strip()
                if point:
                    key_points.append(point)
        
        return key_points
    
    def _parse_sentiment_response(self, response: str) -> Dict[str, Any]:
        """Parse sentiment analysis response"""
        try:
            if response.strip().startswith('{'):
                return json.loads(response)
            
            # Extract sentiment from text
            response_lower = response.lower()
            if 'positive' in response_lower:
                sentiment = 'positive'
            elif 'negative' in response_lower:
                sentiment = 'negative'
            else:
                sentiment = 'neutral'
            
            return {
                "sentiment": sentiment,
                "confidence": 0.7,  # Default confidence
                "tone": "professional"
            }
            
        except Exception as e:
            logger.warning(f"Error parsing sentiment response: {str(e)}")
            return {
                "sentiment": "neutral",
                "confidence": 0.5,
                "tone": "unknown"
            }
    
    def _extract_structured_data(self, response: str) -> Dict[str, Any]:
        """Extract structured data from unstructured response"""
        data = {}
        
        # Extract summary
        if 'summary' in response.lower():
            summary_start = response.lower().find('summary')
            if summary_start != -1:
                summary_text = response[summary_start:summary_start+200]
                data['summary'] = summary_text.strip()
        
        # Extract language
        if 'language' in response.lower():
            lang_start = response.lower().find('language')
            if lang_start != -1:
                lang_text = response[lang_start:lang_start+50]
                data['language'] = lang_text.strip()
        
        return data
    
    def _extract_entities_from_text(self, response: str) -> List[Dict[str, Any]]:
        """Extract entities from unstructured text response"""
        entities = []
        lines = response.split('\n')
        
        for line in lines:
            line = line.strip()
            if line and ':' in line:
                parts = line.split(':', 1)
                if len(parts) == 2:
                    entity_text = parts[0].strip()
                    category = parts[1].strip()
                    
                    entities.append({
                        'text': entity_text,
                        'category': category.upper(),
                        'confidence': 0.8,
                        'context': ''
                    })
        
        return entities


# Global service instance
_content_analysis_service: Optional[ContentAnalysisService] = None


def get_content_analysis_service() -> ContentAnalysisService:
    """Get the global content analysis service instance"""
    global _content_analysis_service
    if _content_analysis_service is None:
        _content_analysis_service = ContentAnalysisService()
    return _content_analysis_service


def initialize_content_analysis_service(gemini_service: Optional[GeminiService] = None) -> ContentAnalysisService:
    """Initialize the global content analysis service instance"""
    global _content_analysis_service
    _content_analysis_service = ContentAnalysisService(gemini_service)
    return _content_analysis_service
