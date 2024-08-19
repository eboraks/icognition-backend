import os, logging, sys
import google.generativeai as genai
from pydantic import BaseModel
from pydantic_core import ValidationError



logging.basicConfig(
    stream=sys.stdout,
    format="%(asctime)s - %(message)s",
    level=logging.INFO,
    datefmt="%Y-%m-%d %H:%M:%S",
)


""" GEMINI_FLASH_MODEL": "models/gemini-1.5-flash-001",
"GEMINI_PRO_MODEL": "models/gemini-1.5-pro-001",
        "GEMINI_EMBEDDING_MODEL": "models/text-embedding-004"""


class GeminiClient:

    ## Set default model name, gcp key and configure the generative model
    def __init__(self, _model_name: str = os.getenv("GEMINI_FLASH_MODEL")):
        self.model_name = _model_name
        genai.configure(api_key = os.getenv("GCP_AI_KEY"))
        self.client = genai.GenerativeModel(_model_name)


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


    async def generate_response(self, prompt: str, prompt_model: BaseModel, attempts: int = 3):
        
        logging.debug(f"Generating response for prompt_model: {prompt_model}")
        response = await self.client.generate_content_async(prompt, 
                generation_config={"response_mime_type": "application/json",  "response_schema": prompt_model})
        
        try:
            answer = prompt_model.model_validate_json(response.text)
        except ValidationError as e:
            logging.error(f"Error validating the response: {e}")
            if (attempts > 0):
                logging.info(f"Retrying the response generation for prompt_model: {prompt_model}")
                return await self.generate_response(prompt, prompt_model, attempts - 1)
        except Exception as e:
            logging.error(f"Error validating the response: {e}")
            raise e

        return answer
    
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
    



