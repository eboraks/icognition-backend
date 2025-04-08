from app.log import get_logger
logger = get_logger(__name__)

import os
from google import genai
from google.genai import types
from pydantic import BaseModel
import json
from app.response_models import Status

class GeminiClient:
    def __init__(self, _flash_model_name: str = os.getenv("GEMINI_FLASH_MODEL", "gemini-2.0-flash"), 
                 _pro_model_name: str = os.getenv("GEMINI_PRO_MODEL", "gemini-2.0-pro")):
        self.flash_model_name = _flash_model_name
        self.pro_model_name = _pro_model_name
        
        # Initialize the client with API key
        self.client = genai.Client(api_key=os.getenv("GCP_AI_KEY"))

    def get_models_names(self):
        """Get the list of models that support embedContent or generateContent methods"""
        return [model.name for model in self.client.list_models()]

    async def generate_response(self, prompt: str, response_model: BaseModel) -> BaseModel:
        """Generate a response using the Gemini model."""
        try:
            # Generate content with JSON response format
            response = self.client.models.generate_content(
                model=self.flash_model_name,
                contents=[prompt],
                config=types.GenerateContentConfig(
                    temperature=0.2,
                    top_p=0.8,
                    top_k=40,
                    response_mime_type="application/json",
                    response_schema=response_model.model_json_schema(),
                    citationMetadata=True
                )
            )
            
            # Process the response
            if response and response.text:
                try:
                    # Try to parse the response as JSON
                    response_data = json.loads(response.text)
                        
                    return response_model(**response_data)
                except json.JSONDecodeError:
                    # If not JSON, try to parse it as a string
                    return response_model(
                        answer_for_chat=response.text,
                        short_answer_for_computer=response.text,
                        citations=[],
                        status=Status.SUCCESS.value,
                        best_match_index=0,
                        match_confidence=1.0,
                        reasoning="Response was not in JSON format"
                    )
            else:
                return response_model(
                    answer_for_chat="No response generated",
                    short_answer_for_computer="No response generated",
                    citations=[],
                    status=Status.ERROR.value,
                    best_match_index=0,
                    match_confidence=0.0,
                    reasoning="No response was generated"
                )
                
        except Exception as e:
            logger.error(f"Error in Gemini response generation: {str(e)}")
            return response_model(
                answer_for_chat=f"Error: {str(e)}",
                short_answer_for_computer=f"Error: {str(e)}",
                citations=[],
                status=Status.ERROR.value,
                best_match_index=0,
                match_confidence=0.0,
                reasoning=f"Error occurred: {str(e)}"
            )

    async def generate_embedding(self, content: str, title: str = None, task_type: str = "SEMANTIC_SIMILARITY", 
                               model_name: str = os.getenv("GEMINI_EMBEDDING_MODEL")):
        """Generate embeddings for given content"""
        try:
            # Configure embedding request
            config = {
                "task_type": task_type,
                "output_dimensionality": 3072  # Ensure consistent output size
            }
            if title:
                config["title"] = title

            # Generate embedding
            response = self.client.models.embed_content(
                model=model_name,
                contents=content,
                config=config
            )

            if response and response.embeddings:
                return response.embeddings[0].values
            else:
                logger.error("No embedding returned from API")
                return []

        except Exception as e:
            logger.error(f"Error generating embeddings: {e}")
            return []

    @classmethod
    def pro_model_name(cls):
        return os.getenv("GEMINI_PRO_MODEL", "gemini-2.0-pro")
    



