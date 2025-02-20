from app.log import get_logger
logger = get_logger(__name__)


import os
import google.generativeai as genai
from pydantic import BaseModel
from pydantic_core import ValidationError
import asyncio
import json



class GeminiClient:

    ## Set default model name, gcp key and configure the generative model
    def __init__(self, _flash_model_name: str = os.getenv("GEMINI_FLASH_MODEL"), _pro_model_name: str = os.getenv("GEMINI_PRO_MODEL")):
        self.flash_model_name = _flash_model_name
        self.pro_model_name = _pro_model_name
        genai.configure(api_key = os.getenv("GCP_AI_KEY"))
        
        # Initialize clients once
        self.flash_client = genai.GenerativeModel(self.flash_model_name)
        self.pro_client = genai.GenerativeModel(self.pro_model_name)

    def get_models_names(self):
        """ 
            Get the list of models that support the embedContent or generateContent generation methods 
            return: list of models names
        """
        models_names = []
        for m in genai.list_models():
            if 'embedContent' in m.supported_generation_methods:
                models_names.append(m.name)

            if 'generateContent' in m.supported_generation_methods:
                models_names.append(m.name)

        return models_names 


    async def generate_response(self, prompt: str, prompt_model: BaseModel):
        logger.info(f"Gemini Client: Generating response for prompt_model: {prompt_model}")
        try:
            

            # Use the appropriate pre-initialized client
            client = self.flash_client
            
            # Make the API call
            response = await client.generate_content_async(prompt, 
                generation_config={"response_mime_type": "application/json",  "response_schema": prompt_model})
            
            # Parse and validate response
            try:
                json_response = json.loads(response.text)
                validated_response = prompt_model.model_validate(json_response)
                return validated_response
            except Exception as e:
                logger.error(f"Error validating the response: {str(e)}")
                raise e

        except Exception as e:
            logger.error(f"Error validating the response: {str(e)}")
            raise e
    

    async def generate_embedding(self, content: str, title: str = None, task_type: str = "retrieval_document", model_name: str = os.getenv("GEMINI_EMBEDDING_MODEL")):
        """
        Generate embeddings for a given string content
        content: string content to generate embeddings for
        task_type: the type of task for which the embeddings are generated
        title: title for the embeddings
        return: the embeddings
        """
    
        try:
            result = None
            if title:
                result = genai.embed_content(
                    model=model_name,
                    content=content,
                    task_type=task_type
                )
            else:
                result = genai.embed_content(
                    model=model_name,
                    content=content,
                    task_type=task_type,
                    title=title
                )
        except Exception as e:
            logger.error(f"Error generating embeddings: {e}")
            result = None

        try: 
            return result['embedding']
        except Exception as e:
            logger.error(f"Error extracting embeddings: {e}")
            return None
    
    
    @classmethod
    def pro_model_name(cls):
        return os.getenv("GEMINI_PRO_MODEL")
    



