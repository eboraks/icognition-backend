import os
import google.generativeai as genai
from pydantic import BaseModel
from pydantic_core import ValidationError
from app.log import get_logger



logging = get_logger()

""" GEMINI_FLASH_MODEL": "models/gemini-1.5-flash-001",
"GEMINI_PRO_MODEL": "models/gemini-1.5-pro-001",
        "GEMINI_EMBEDDING_MODEL": "models/text-embedding-004"""


class GeminiClient:

    ## Set default model name, gcp key and configure the generative model
    def __init__(self, _flash_model_name: str = os.getenv("GEMINI_FLASH_MODEL"), _pro_model_name: str = os.getenv("GEMINI_PRO_MODEL")):
        self.flash_model_name = _flash_model_name
        self.pro_model_name = _pro_model_name
        genai.configure(api_key = os.getenv("GCP_AI_KEY"))
        

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


    async def generate_response(self, prompt: str, prompt_model: BaseModel, gemini_model = os.getenv("GEMINI_FLASH_MODEL"), attempts: int = 3):
        

        client = genai.GenerativeModel(gemini_model)
        logging.debug(f"Generating response for prompt_model: {prompt_model}")
        response = await client.generate_content_async(prompt, 
                generation_config={"response_mime_type": "application/json",  "response_schema": prompt_model})
        
        try:
            validated_response = prompt_model.model_validate_json(response.text, strict=False)
        except ValidationError as e:
            logging.error(f"Error validating the response: {e}")
            if (attempts > 0):
                logging.info(f"Retrying the response generation for prompt_model: {prompt_model}")
                return await self.generate_response(prompt=prompt, prompt_model=prompt_model, gemini_model=os.getenv("GEMINI_FLASH_MODEL"), attempts = attempts - 1)
            
        except Exception as e:
            logging.error(f"Error validating the response: {e}")
            return await self.generate_response(prompt=prompt, prompt_model=prompt_model, gemini_model=os.getenv("GEMINI_FLASH_MODEL"), attempts = attempts - 1)
    

        return validated_response
    
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
            logging.error(f"Error generating embeddings: {e}")
            result = None

        return result['embedding']
    
    @classmethod
    def pro_model_name(cls):
        return os.getenv("GEMINI_PRO_MODEL")
    



