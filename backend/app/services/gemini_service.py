"""
Google Gemini AI Service for content analysis and entity extraction
"""

import asyncio
import json
import time
from typing import Optional, Dict, Any, List, Union
from datetime import datetime, timedelta
from dataclasses import dataclass
from enum import Enum

from google import genai
from google.genai import types
from google.api_core import exceptions as gcp_exceptions

from app.core.config import settings
from app.utils.logging import get_logger

logger = get_logger(__name__)


class GeminiModel(Enum):
    """Available Gemini models"""
    FLASH = settings.GEMINI_FLASH_MODEL
    FLASH_LITE = settings.GEMINI_FLASH_LITE_MODEL
    EMBEDDING = settings.GEMINI_EMBEDDING_MODEL


@dataclass
class GeminiConfig:
    """Configuration for Gemini API calls"""
    temperature: float = 0.2
    top_p: float = 0.8
    top_k: int = 40
    max_output_tokens: int = 8192
    response_mime_type: str = "application/json"
    response_schema: Optional[Any] = None  # Pydantic model or schema for structured output


@dataclass
class RateLimitInfo:
    """Rate limiting information"""
    requests_per_minute: int = 60
    requests_per_day: int = 1500
    tokens_per_minute: int = 32000
    tokens_per_day: int = 1000000


class GeminiService:
    """
    Service for Google Gemini AI integration with robust error handling,
    rate limiting, and caching capabilities.
    """
    
    def __init__(self, api_key: Optional[str] = None, mock_mode: bool = False):
        """
        Initialize the Gemini service
        
        Args:
            api_key: Google API key. If None, uses settings.GOOGLE_API_KEY
            mock_mode: If True, runs in mock mode without requiring API key
        """
        self.mock_mode = mock_mode
        self.client: Optional[genai.Client] = None
        
        if mock_mode:
            logger.info("GeminiService initialized in mock mode")
        else:
            self.api_key = api_key or settings.GOOGLE_API_KEY
            if not self.api_key:
                raise ValueError("Google API key is required")
            
            # Use the new centralized client from google-genai SDK
            self.client = genai.Client(api_key=self.api_key)
        
        # Rate limiting
        self.rate_limit_info = RateLimitInfo()
        self.request_times: List[datetime] = []
        self.token_usage: List[int] = []
        
        # Cache for responses
        self.response_cache: Dict[str, Any] = {}
        self.cache_ttl = timedelta(hours=1)
        
        logger.info("GeminiService initialized successfully")
    
    async def generate_content(
        self,
        prompt: str,
        model: GeminiModel = GeminiModel.FLASH,
        config: Optional[GeminiConfig] = None,
        retry_count: int = 3,
        use_cache: bool = True
    ) -> Dict[str, Any]:
        """
        Generate content using Gemini models with retry logic and caching
        
        Args:
            prompt: Input prompt for content generation
            model: Gemini model to use
            config: Configuration for the generation
            retry_count: Number of retry attempts
            use_cache: Whether to use cached responses
            
        Returns:
            Dictionary containing the generated content and metadata
        """
        if not prompt.strip():
            raise ValueError("Prompt cannot be empty")
        
        # Check cache first
        cache_key = f"{model.value}:{hash(prompt)}"
        if use_cache and cache_key in self.response_cache:
            cached_data = self.response_cache[cache_key]
            if datetime.now() - cached_data['timestamp'] < self.cache_ttl:
                logger.debug(f"Returning cached response for prompt hash: {hash(prompt)}")
                return cached_data['response']
        
        # Mock mode handling
        if self.mock_mode:
            return await self._generate_mock_content(prompt, model, config, use_cache, cache_key)
        
        if not self.client:
            raise RuntimeError("Gemini client not initialized. Did you forget to provide an API key?")

        # Check rate limits
        await self._check_rate_limits()
        
        config = config or GeminiConfig()
        
        backoff = 1
        last_error = None
        
        for attempt in range(retry_count):
            try:
                logger.debug(f"Generating content with {model.value} (attempt {attempt + 1})")
                
                # Prepare generation config for the new SDK
                generation_config = types.GenerationConfig(
                    temperature=config.temperature,
                    top_p=config.top_p,
                    top_k=config.top_k,
                    max_output_tokens=config.max_output_tokens,
                )
                # TODO: Migrated from old SDK. `response_mime_type` and `response_schema` are not
                # directly supported in the new `GenerateContentConfig`.
                # Structured output might require a different approach.
                
                # Generate content using the new client, wrapped for async execution
                response = await asyncio.to_thread(
                    self.client.models.generate_content,
                    model=model.value,
                    contents=prompt,
                    generation_config=generation_config
                )
                
                # Simplified check for successful response
                if not hasattr(response, 'text') or not response.text:
                    finish_reason = getattr(response, 'finish_reason', 'UNKNOWN')
                    logger.warning(f"Response blocked or empty. Finish reason: {finish_reason}")
                    if attempt < retry_count - 1:
                        logger.info(f"Retrying (attempt {attempt + 2}/{retry_count})...")
                        await asyncio.sleep(2 ** attempt)
                        continue
                    else:
                        raise Exception(f"Response blocked after all retries. Finish reason: {finish_reason}")
                
                # Process successful response
                result = {
                    'content': response.text,
                    'model': model.value,
                    'timestamp': datetime.now(),
                    'attempt': attempt + 1,
                    'success': True
                }
                
                # Cache the response
                if use_cache:
                    self.response_cache[cache_key] = {
                        'response': result,
                        'timestamp': datetime.now()
                    }
                
                # Update rate limiting
                self._update_rate_limits(len(prompt), len(response.text))
                
                logger.info(f"Successfully generated content with {model.value}")
                return result
                
            except gcp_exceptions.ResourceExhausted as e:
                last_error = e
                logger.warning(f"Rate limit exceeded (attempt {attempt + 1}): {str(e)}")
                if attempt < retry_count - 1:
                    await asyncio.sleep(backoff)
                    backoff *= 2
                else:
                    raise
                    
            except gcp_exceptions.ServiceUnavailable as e:
                last_error = e
                logger.warning(f"Service unavailable (attempt {attempt + 1}): {str(e)}")
                if attempt < retry_count - 1:
                    await asyncio.sleep(backoff)
                    backoff *= 2
                else:
                    raise
                    
            except Exception as e:
                last_error = e
                logger.error(f"Unexpected error generating content (attempt {attempt + 1}): {str(e)}")
                if attempt < retry_count - 1:
                    await asyncio.sleep(backoff)
                    backoff *= 2
                else:
                    raise
        
        # If we get here, all retries failed
        raise Exception(f"Failed to generate content after {retry_count} attempts. Last error: {str(last_error)}")
    
    async def generate_embedding(
        self,
        text: str,
        title: Optional[str] = None,
        task_type: str = "SEMANTIC_SIMILARITY",
        output_dimensionality: int = 1536,
        retry_count: int = 3
    ) -> List[float]:
        """
        Generate embeddings using Gemini embedding models
        
        Args:
            text: Text to embed
            title: Optional title for the text
            task_type: Type of embedding task
            output_dimensionality: Dimension of the embedding vector
            retry_count: Number of retry attempts
            
        Returns:
            List of float values representing the embedding
        """
        if not text.strip():
            raise ValueError("Text cannot be empty")
        
        # Mock mode handling
        if self.mock_mode:
            return await self._generate_mock_embedding(text, title, task_type, output_dimensionality)
        
        if not self.client:
            raise RuntimeError("Gemini client not initialized. Did you forget to provide an API key?")

        # Check rate limits
        await self._check_rate_limits()
        
        backoff = 1
        last_error = None
        
        for attempt in range(retry_count):
            try:
                logger.debug(f"Generating embedding (attempt {attempt + 1})")
                
                # Generate embedding using the new client, wrapped for async
                # Build the request payload
                embed_params = {
                    "model": GeminiModel.EMBEDDING.value,
                    "contents": text,
                }
                
                # Build config for optional parameters
                config_params = {}
                
                # Only include optional parameters if they're provided
                if title:
                    config_params["title"] = title
                
                # Add output_dimensionality to config if supported
                if output_dimensionality:
                    config_params["outputDimensionality"] = output_dimensionality
                
                # Note: task_type parameter may not be supported in current SDK version
                # If needed, check SDK documentation for correct parameter name
                # config_params["task_type"] = task_type
                
                # Include config if we have any config parameters
                if config_params:
                    embed_params["config"] = config_params
                
                response = await asyncio.to_thread(
                    self.client.models.embed_content,
                    **embed_params
                )
                
                # Extract embedding from response - the API returns 'embeddings' (plural)
                if not response or not hasattr(response, 'embeddings'):
                    raise Exception("Invalid response structure from embed_content API")
                
                embeddings_obj = response.embeddings
                
                # Get the embedding values - embeddings is typically a list, get first one
                if isinstance(embeddings_obj, list) and len(embeddings_obj) > 0:
                    embedding_obj = embeddings_obj[0]
                else:
                    embedding_obj = embeddings_obj
                
                # Extract the actual vector values
                if hasattr(embedding_obj, 'values'):
                    embedding = list(embedding_obj.values)
                elif isinstance(embedding_obj, list):
                    embedding = embedding_obj
                elif isinstance(embedding_obj, dict) and 'values' in embedding_obj:
                    embedding = embedding_obj['values']
                else:
                    raise Exception(f"Unexpected embedding structure: {type(embedding_obj)}")
                
                # Ensure it's a list of floats
                embedding = [float(v) for v in embedding]
                
                # Normalize embedding to requested dimensions
                # Truncate if too long, pad with zeros if too short (though padding is unusual)
                actual_dims = len(embedding)
                if actual_dims != output_dimensionality:
                    if actual_dims > output_dimensionality:
                        # Truncate to requested dimension
                        logger.warning(f"Embedding has {actual_dims} dimensions, truncating to {output_dimensionality}")
                        embedding = embedding[:output_dimensionality]
                    elif actual_dims < output_dimensionality:
                        # Pad with zeros (unusual but handle gracefully)
                        logger.warning(f"Embedding has {actual_dims} dimensions, padding to {output_dimensionality}")
                        embedding.extend([0.0] * (output_dimensionality - actual_dims))
                
                # Update rate limiting
                self._update_rate_limits(len(text), 0)
                
                logger.info(f"Successfully generated embedding with {len(embedding)} dimensions (requested: {output_dimensionality})")
                return embedding
                    
            except gcp_exceptions.ResourceExhausted as e:
                last_error = e
                logger.warning(f"Rate limit exceeded for embedding (attempt {attempt + 1}): {str(e)}")
                if attempt < retry_count - 1:
                    await asyncio.sleep(backoff)
                    backoff *= 2
                else:
                    raise
                    
            except Exception as e:
                last_error = e
                logger.error(f"Error generating embedding (attempt {attempt + 1}): {str(e)}")
                if attempt < retry_count - 1:
                    await asyncio.sleep(backoff)
                    backoff *= 2
                else:
                    raise
        
        # If we get here, all retries failed
        raise Exception(f"Failed to generate embedding after {retry_count} attempts. Last error: {str(last_error)}")
    
    async def analyze_content(
        self,
        content: str,
        analysis_type: str = "summary",
        model: GeminiModel = GeminiModel.FLASH
    ) -> Dict[str, Any]:
        """
        Analyze content for various purposes (summary, key points, entities, etc.)
        
        Args:
            content: Content to analyze
            analysis_type: Type of analysis to perform
            model: Gemini model to use
            
        Returns:
            Dictionary containing analysis results
        """
        prompts = {
            "summary": "Provide a concise summary of the following content:",
            "bullet_points": "Extract the key points from the following content:",
            "entities": "Extract named entities (people, places, organizations, etc.) from the following content:",
            "topics": "Identify the main topics discussed in the following content:",
            "sentiment": "Analyze the sentiment of the following content:",
            "language": "Identify the language of the following content:"
        }
        
        if analysis_type not in prompts:
            raise ValueError(f"Unsupported analysis type: {analysis_type}")
        
        prompt = f"{prompts[analysis_type]}\n\n{content}"
        
        try:
            result = await self.generate_content(prompt, model)
            
            # Parse JSON response if possible
            try:
                parsed_content = json.loads(result['content'])
                result['parsed_content'] = parsed_content
            except json.JSONDecodeError:
                result['parsed_content'] = result['content']
            
            result['analysis_type'] = analysis_type
            return result
            
        except Exception as e:
            logger.error(f"Error analyzing content: {str(e)}")
            raise
    
    async def _check_rate_limits(self):
        """Check and enforce rate limits - simplified version"""
        # Let Gemini API handle its own rate limiting
        # We'll only add minimal delays if we get ResourceExhausted errors
        pass
    
    def _update_rate_limits(self, input_tokens: int, output_tokens: int):
        """Update rate limiting information"""
        now = datetime.now()
        self.request_times.append(now)
        self.token_usage.append(input_tokens + output_tokens)
    
    def clear_cache(self):
        """Clear the response cache"""
        self.response_cache.clear()
        logger.info("Response cache cleared")
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        now = datetime.now()
        valid_entries = sum(
            1 for data in self.response_cache.values()
            if now - data['timestamp'] < self.cache_ttl
        )
        
        return {
            'total_entries': len(self.response_cache),
            'valid_entries': valid_entries,
            'cache_ttl_hours': self.cache_ttl.total_seconds() / 3600
        }
    
    async def _generate_mock_content(
        self,
        prompt: str,
        model: GeminiModel,
        config: Optional[GeminiConfig],
        use_cache: bool,
        cache_key: str
    ) -> Dict[str, Any]:
        """Generate mock content for testing purposes"""
        await asyncio.sleep(0.1)  # Simulate API delay
        
        # Generate mock response based on prompt content
        mock_responses = {
            "summary": "This is a mock summary of the provided content. It covers the main points and key information discussed in the original text.",
            "bullet_points": "• Mock key point 1\n• Mock key point 2\n• Mock key point 3",
            "entities": '{"entities": [{"text": "Mock Entity", "category": "ORGANIZATION", "confidence": 0.95}]}',
            "sentiment": '{"sentiment": "positive", "confidence": 0.85, "tone": "professional"}',
            "default": "This is a mock response generated for testing purposes. The actual Gemini API would provide more sophisticated analysis."
        }
        
        # Determine response type based on prompt
        response_text = mock_responses["default"]
        if "summary" in prompt.lower():
            response_text = mock_responses["summary"]
        elif "key points" in prompt.lower() or "bullet" in prompt.lower():
            response_text = mock_responses["bullet_points"]
        elif "entities" in prompt.lower():
            response_text = mock_responses["entities"]
        elif "sentiment" in prompt.lower():
            response_text = mock_responses["sentiment"]
        
        result = {
            'content': response_text,
            'model': f"{model.value}-mock",
            'timestamp': datetime.now(),
            'attempt': 1,
            'success': True,
            'mock_mode': True
        }
        
        # Cache the response
        if use_cache:
            self.response_cache[cache_key] = {
                'response': result,
                'timestamp': datetime.now()
            }
        
        logger.info(f"Generated mock content with {model.value}")
        return result
    
    async def _generate_mock_embedding(
        self,
        text: str,
        title: Optional[str],
        task_type: str,
        output_dimensionality: int
    ) -> List[float]:
        """Generate mock embedding for testing purposes"""
        await asyncio.sleep(0.1)  # Simulate API delay
        
        # Generate mock embedding with specified dimensions
        import random
        random.seed(hash(text))  # Deterministic based on text content
        
        embedding = [random.uniform(-1, 1) for _ in range(output_dimensionality)]
        
        # Normalize the embedding
        norm = sum(x**2 for x in embedding) ** 0.5
        embedding = [x / norm for x in embedding]
        
        logger.info(f"Generated mock embedding with {len(embedding)} dimensions")
        return embedding


# Global service instance
_gemini_service: Optional[GeminiService] = None


def get_gemini_service() -> GeminiService:
    """Get the global Gemini service instance"""
    global _gemini_service
    if _gemini_service is None:
        # Try to initialize with API key, fall back to mock mode if not available
        try:
            _gemini_service = GeminiService()
        except ValueError:
            logger.warning("No Google API key found, initializing in mock mode")
            _gemini_service = GeminiService(mock_mode=True)
    return _gemini_service


def initialize_gemini_service(api_key: Optional[str] = None, mock_mode: bool = False) -> GeminiService:
    """Initialize the global Gemini service instance"""
    global _gemini_service
    _gemini_service = GeminiService(api_key, mock_mode)
    return _gemini_service
