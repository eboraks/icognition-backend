import json, os, logging, sys
from datetime import datetime
from datetime import timedelta
import google.generativeai as genai
from google.generativeai import caching, chat_async
from pydantic import BaseModel
from pydantic_core import ValidationError
import app.getters as getter
import asyncio


logging.basicConfig(
    stream=sys.stdout,
    format="%(asctime)s - %(message)s",
    level=logging.INFO,
    datefmt="%Y-%m-%d %H:%M:%S",
)


GCP_KEY = os.getenv("GCP_AI_KEY")

_model_name = "gemini-1.5-flash-001"

genai.configure(api_key=GCP_KEY)
client = genai.GenerativeModel(_model_name)

async def generate_response(prompt: str, prompt_model: BaseModel, attempts: int = 3):
    
    logging.debug(f"Generating response for prompt_model: {prompt_model}")
    response = await client.generate_content_async(prompt, 
            generation_config={"response_mime_type": "application/json",  "response_schema": prompt_model})
    
    try:
        answer = prompt_model.model_validate_json(response.text)
    except ValidationError as e:
        logging.error(f"Error validating the response: {e}")
        if (attempts > 0):
            logging.info(f"Retrying the response generation for prompt_model: {prompt_model}")
            return await generate_response(prompt, prompt_model, attempts - 1)
    except Exception as e:
        logging.error(f"Error validating the response: {e}")
        return None

    return answer


