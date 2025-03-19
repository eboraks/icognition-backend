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
from google.genai.errors import ServerError
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

def async_retry_with_backoff(exceptions=(Exception,), max_retries=3, delay=1):
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            retries = 0
            while retries < max_retries:
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    retries += 1
                    if retries == max_retries:
                        logger.error(f"Max retries ({max_retries}) reached for {func.__name__}. Error: {str(e)}")
                        raise e
                    wait_time = delay * (2 ** (retries - 1))  # Exponential backoff
                    logger.warning(f"Retrying {func.__name__} after {wait_time}s. Attempt {retries}/{max_retries}")
                    await asyncio.sleep(wait_time)
            return None
        return wrapper
    return decorator

class ChatClient:
    def __init__(self, response_model: BaseModel, 
                 model_name: str = "models/gemini-2.0-flash", 
                 temperature: float = 0.5, 
                 system_instruction: str = "",
                 chat_history: list = None):
        
        self.client = genai.Client(api_key=os.getenv("GCP_AI_KEY"))
        self.model_name = model_name
        self.system_instruction = system_instruction
        self.temperature = temperature
        self.response_model = response_model
    
        # Create the chat session
        self.chat = self.client.chats.create(
            model=self.model_name, 
            config=GenerateContentConfig(
                system_instruction=self.system_instruction,
                response_mime_type="application/json",
                response_schema=response_model,
                temperature=self.temperature
            )
        )
        
        # If chat history is provided, add it to the chat
        if chat_history:
            self.set_chat_history(chat_history)
    
    def get_model_name(self):
        return self.model_name
    
    def get_client(self):
        return self.client
    
    def get_system_instruction(self):
        return self.system_instruction

    def set_chat_history(self, chat_history: list):
        """
        Set the chat history for the Gemini chat session.
        
        Args:
            chat_history: A list of Chat_Message objects representing the conversation history
        """
        try:
            # Add each message from the history to the chat
            prompt = f"Here is the conversation history:\n"
            for message in chat_history:
                    # Add the prompt to the chat
                prompt += f"Time: {message.created_at} User: {message.asked_by} Message: {message.user_prompt}. Response: {message.response}\n\n"
                     
            try:
                self.chat.send_message(prompt)
            except Exception as e:
                logger.error(f"Error sending message to chat history: {str(e)}")
                return False
            logger.info(f"Successfully set chat history with {len(chat_history)} messages")
            return True
            
        except Exception as e:
            logger.error(f"Error setting chat history: {str(e)}")
            return False

    @async_retry_with_backoff(
        exceptions=(
            exceptions.InternalServerError,    # 500 errors
            exceptions.ResourceExhausted,      # Rate limits
            exceptions.ServiceUnavailable,     # 503 errors
            exceptions.DeadlineExceeded,       # Timeout errors
            ValidationError,                   # Pydantic validation errors
            ServerError                        # Google Generative AI server errors
        )
    )
    async def send_message_async(self, message: str):
        # Run the synchronous method in an executor to avoid blocking
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, lambda: self.chat.send_message(message))
    
    @retry_with_backoff(
        exceptions=(
            exceptions.InternalServerError,    # 500 errors
            exceptions.ResourceExhausted,      # Rate limits
            exceptions.ServiceUnavailable,     # 503 errors
            exceptions.DeadlineExceeded,       # Timeout errors
            ValidationError,                   # Pydantic validation errors
            ServerError                        # Google Generative AI server errors
        )
    )
    def send_message(self, prompt: str, response_model: BaseModel = None):
        
        if response_model:
            
            _config = GenerateContentConfig(
                response_mime_type = "application/json",
                response_schema = response_model,
                temperature = self.temperature)
        
        else:
            _config = GenerateContentConfig(
                response_mime_type= "application/json",
                temperature = self.temperature)
        
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
def main():
   client = ChatClient(system_instruction = "You are a helpful assistant.", response_model = None)
   print("Got client")
   response = client.send_message(prompt = "What is the capital of France?", response_model = None)
   print(response)


if __name__ == "__main__":
    main()