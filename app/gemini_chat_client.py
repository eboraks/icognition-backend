import asyncio
import json
import os
import functools
import time
import logging
from pydantic import BaseModel, ValidationError
from google import genai
from google.genai.types import (
    CreateBatchJobConfig,
    CreateCachedContentConfig,
    EmbedContentConfig,
    FunctionDeclaration,
    GenerateContentConfig,
    Part,
    SafetySetting,
    Tool,
)
from google.api_core import exceptions

# Set up logger
logger = logging.getLogger(__name__)

def retry_with_backoff(exceptions=(Exception,), max_retries=3, delay=1):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            retries = 0
            while retries < max_retries:
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    retries += 1
                    if retries == max_retries:
                        logger.error(f"Max retries ({max_retries}) reached for {func.__name__}. Error: {str(e)}")
                        raise e
                    wait_time = delay * (2 ** (retries - 1))  # Exponential backoff
                    logger.warning(f"Retrying {func.__name__} after {wait_time}s. Attempt {retries}/{max_retries}")
                    time.sleep(wait_time)
            return None
        return wrapper
    return decorator


class ChatClient:
    def __init__(self, response_schema: BaseModel, model_name: str = "models/gemini-2.0-flash", temperature: float = 0.5, system_instruction: str = """
  You are a research assistant that can help with analysis of the provided text.
  You will be provided with a text or HTML and you will need to extract information and analyze it and provide insights about the content."""):
        self.client = genai.Client(api_key=os.getenv("GCP_AI_KEY"))
        self.model_name = model_name
        self.system_instruction = system_instruction
        self.temperature = temperature 
    
        self.chat = self.client.chats.create(model = self.model_name, 
                            config = GenerateContentConfig(
                                    system_instruction = self.system_instruction,
                                    response_mime_type = "application/json",
                                    response_schema = response_schema,
                                    temperature = 0.5))
    
    def get_model_name(self):
        return self.model_name
    
    def get_client(self):
        return self.client
    
    def get_system_instruction(self):
        return self.system_instruction

    async def send_message_async(self, message: str):
        return self.chat.send_message(message)
    
    @retry_with_backoff(
        exceptions=(
            exceptions.InternalServerError,    # 500 errors
            exceptions.ResourceExhausted,      # Rate limits
            exceptions.ServiceUnavailable,     # 503 errors
            exceptions.DeadlineExceeded,       # Timeout errors
            ValidationError                    # Pydantic validation errors
        )
    )
    def send_message(self, prompt: str, prompt_support_info: str = None, response_model: BaseModel = None):
        
        _config = GenerateContentConfig(
            response_mime_type = "application/json",
            response_schema = response_model,
            temperature = self.temperature)
        
        if prompt_support_info is not None:
            prompt = prompt.format(SUPPORT_INFO = prompt_support_info)
            
        if "SUPPORT_INFO" in prompt:
            logger.error("SUPPORT_INFO placeholder found in prompt without support info provided")
            raise ValueError("SUPPORT_INFO is not allowed in the prompt")
        
        logger.debug(f"Sending message with prompt: {prompt[:100]}...")  # Log first 100 chars of prompt
        response = self.chat.send_message(prompt, config = _config)
        logger.debug("Message sent successfully")
        
        if response_model is not None:
            try:
                validated_response = response_model.model_validate_json(response.text)
                logger.debug("Response successfully validated against model")
                return validated_response
            except ValidationError as e:
                logger.error(f"Response validation failed: {str(e)}")
                raise
        else:
            return response.text









## main function    
async def main():
   return ChatClient()


if __name__ == "__main__":
    asyncio.run(main())