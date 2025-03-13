import json
import asyncio
from typing import Callable, List, Optional
from pydantic import BaseModel
import logging

from app.gemini_chat_client import ChatClient
import app.getters as getters
from google.genai.types import GenerateContentConfig

from app.app_logic import insert_or_update_chat_history
from app.models import Chat_Message, DocumentPublic, EventName, BroadcastMessage, WebSocketMessageType, EntityPublic
from app.response_models import Answer, ContentType, Summary, Topic, Type, Types, ChatMessagePublic, Graph, Graphs

# Set up logger
logger = logging.getLogger(__name__)


class ChatHandler:
    def __init__(self, document_id: str = None, collection_id: str = None, user_id: str = None, temperature: float = 0.5, event_listener: Callable = None):
        self._user_id = user_id
        self._temperature = temperature
        self._event_listener = event_listener
        self._context_type = "document" if document_id else "collection"
        self._context_id = document_id if document_id else collection_id
        
        # Load context data
        if self._context_type == "document" and document_id:
            self._doc = getters.get_document_by_id(document_id)
            self._source = getters.get_source_by_document_id(document_id)
        elif self._context_type == "collection" and collection_id:
            self._doc = getters.get_study_collection_by_id(collection_id)
        
        # Initialize chat client
        system_instruction = None
        try:
            with open("app/chat_workflows/chat_system_instructions.txt", "r") as f:
                system_instruction = f.read()
        except Exception as e:
            logger.error(f"Error loading system instruction: {str(e)}")
            system_instruction = "You are a helpful assistant."
        
        self._client = ChatClient(
            response_model=Answer, 
            system_instruction=system_instruction
        )
        
        # Set chat history if available
        if self._context_id:
            chat_history = getters.get_chat_history(self._context_id)
            if chat_history:
                self._client.set_chat_history(chat_history)
    
    
    def _process_chat_step(self, _the_ask_prompt: str, 
                           _support_prompt: str, 
                           _response_model: BaseModel, 
                           _asked_by: str = "system", 
                           _chat_type: str = "document", 
                           _event_name: str = EventName.INIT_DOC_CHAT.value):
        try:
            response = self._client.send_message(prompt = _the_ask_prompt + " " + _support_prompt, response_model = _response_model)
            
            if type(response) == str:
                ## Try to parse the answer as a json
                try:
                    response = json.loads(response)
                    message = Chat_Message(
                        chat_id = self._doc.id,
                        chat_type = _chat_type,
                        user_id = self._user_id, 
                        prompt = _the_ask_prompt,
                        asked_by = _asked_by,
                        response = json.dumps(response),
                        event_name = _event_name
                    )
                    message = insert_or_update_chat_history(message)
                    
                    return response
                except Exception as e:  
                    logger.error(f"Error parsing answer: {str(e)}")
                    return None
            
            
            if response.status in ["good", "complete"]:
                message = Chat_Message(
                    chat_id = self._doc.id,
                    chat_type = _chat_type,
                    user_id = self._user_id, 
                    prompt = _the_ask_prompt,
                    asked_by = _asked_by,
                    response = response.model_dump_json(),
                    event_name = _event_name
                )
                message = insert_or_update_chat_history(message)
                
                return response
            else:
                logger.error(f"Error in _process_chat_step: {response.status}")
                return response
            
        except Exception as e:
            logger.error(f"Error in _process_chat_step: {str(e)}")
            return None
    
    
    def start_analyze(self):
        
        ## If the chat is already initiated, send event that the chat is already initiated
        if self.chat_status(self._doc.id):
            event_data = {
                "name": EventName.CHAT_ALREADY_INITIATED.value,
                "doc_id": str(self._doc.id),
                "ask": "The chat is already initiated",
                "response": "The chat is already initiated"
            }
            self._event_listener(event_data)
            return
        

        ## Get the chat history and if it exists, send event that the chat is already initiated
        chat_history = getters.get_chat_history(self._doc.id)
        event_names = [message.event_name for message in chat_history]

        ## Get the content types and entity types
        content_types = getters.get_content_types()
        entity_types = getters.get_entity_types()
        
        ## Identify the level of bias in the content
        try: 
            with open("app/data/bias_categorization.json", "r") as f:
                bias_categorization = json.load(f)
        except Exception as e:
            logger.error(f"Error loading bias categorization: {str(e)}")
            bias_categorization = []
        
        

        asyncio.run(self._event_listener(BroadcastMessage(
            user_id=self._user_id,
            message_type=WebSocketMessageType.PROGRESS_PERCENTAGE.value,
            data=10,
            document_id=self._doc.id
        )))
        
        ## Send the initial chat message
        if EventName.INIT_DOC_CHAT.value not in event_names:
            content_response = self._process_chat_step(
                _the_ask_prompt = "This is the content we are going to analyze: ",
                _support_prompt = self._source.html_root_element[:400000],
                _response_model = None,
                _asked_by = "system",
                _chat_type = "document",
                _event_name = EventName.INIT_DOC_CHAT.value
            )
        
            if content_response is None:
                logger.error("Error in content response")
                asyncio.run(self._event_listener(BroadcastMessage(
                    user_id=self._user_id,
                    message_type=WebSocketMessageType.ERROR.value,
                    data=f"Error in content response",
                    document_id=self._doc.id
                )))
                return
        


        asyncio.run(self._event_listener(BroadcastMessage(
            user_id=self._user_id,
            message_type=WebSocketMessageType.PROGRESS_PERCENTAGE.value,
            data=10,
            document_id=self._doc.id
        )))

        if EventName.CONTENT_TITLE.value not in event_names:
            content_title = self._process_chat_step(
                _the_ask_prompt = "Identify the title of the content",
                _support_prompt = "",
                _response_model = Answer,
                _asked_by = "system",
                _chat_type = "document",
            _event_name = EventName.CONTENT_TITLE.value
            )
        
            logger.info(f"Content title: {content_title.short_answer_for_computer}")
        
        content_title_str = content_title.short_answer_for_computer if content_title.short_answer_for_computer else None
        


        asyncio.run(self._event_listener(BroadcastMessage(
            user_id=self._user_id,
            message_type=WebSocketMessageType.PROGRESS_PERCENTAGE.value,
            data=20,
            document_id=self._doc.id
        )))

        if EventName.CONTENT_TYPE.value not in event_names:
            content_type_answer = self._process_chat_step(
                _the_ask_prompt = "Categorize the type of the content. ",
                _support_prompt = """Is it news article, blog post, product description, etc. 
                Use the following content types as a reference: """ + str(content_types),
            _response_model = ContentType,
            _asked_by = "system",
            _chat_type = "document",
            _event_name = EventName.CONTENT_TYPE.value
            )
        
        content_type_str = content_type_answer.content_type if content_type_answer.content_type else "content"
        
        content_name = content_title_str if content_title_str else content_type_str
        


        asyncio.run(self._event_listener(BroadcastMessage(
            user_id=self._user_id,
            message_type=WebSocketMessageType.PROGRESS_PERCENTAGE.value,
            data=20,
            document_id=self._doc.id
        )))

        if EventName.SUMMARY.value not in event_names:
            summary_response = self._process_chat_step(
                _the_ask_prompt = f"Summaries the main idea in the \"{content_name}\" and create a short overview in bullet points that is easy to understand",
                _support_prompt = "",
            _response_model = Summary,
            _asked_by = "system",
            _chat_type = "document",
            _event_name = EventName.SUMMARY.value
            )
            logger.info(f"Summary: {summary_response.summary_for_chat}")
            
        
        if len(bias_categorization) > 0:
            if EventName.BIAS_CATEGORIZATION.value not in event_names:
                self._process_chat_step(
                    _the_ask_prompt = f"Identify the level of bias in the {content_name}. ",
                    _support_prompt = """Use the following bias categorization to identify the level of bias: """ + json.dumps(bias_categorization),
                    _response_model = Answer,
                    _asked_by = "system",
                    _chat_type = "document",
                _event_name = EventName.BIAS_CATEGORIZATION.value
            )
            
        ## Check chat status and send event if chat is ready
        if self.chat_status(self._doc.id):
            chat_messages = self.generate_explain_message()

            chat_messages = [msg.to_dict() for msg in chat_messages]

            asyncio.run(self._event_listener(BroadcastMessage(
                user_id=self._user_id,
                message_type=WebSocketMessageType.CHAT_READY.value,
                data=chat_messages,
                document_id=self._doc.id
            )))
        else:
            asyncio.run(self._event_listener(BroadcastMessage(
                user_id=self._user_id,
                message_type=WebSocketMessageType.CHAT_NOT_READY.value,
                data="Chat is not ready",
                document_id=self._doc.id
            )))
        
        if EventName.ENTITIES.value not in event_names:
            self._process_chat_step(
                _the_ask_prompt = f"Identify the entities in the {content_name}",
                _support_prompt = """Use the following schema.org entities as a reference: """ + str(entity_types),
                _response_model = Types,
                _asked_by = "system",
                _chat_type = "document",
            _event_name = EventName.ENTITIES.value
            )
    
    def generate_explain_message(self) -> list[Chat_Message]:
        chat_history = getters.get_chat_history(self._doc.id)
        
        ## Get the summary
        system_messages = [{'role': 'system', 'prompt': message.prompt, 'response': message.response} for message in chat_history if message.event_name in [EventName.SUMMARY.value, EventName.CONTENT_TITLE.value, EventName.CONTENT_TYPE.value, EventName.BIAS_CATEGORIZATION.value]]


        ## prompt asking to write a message to the user that write a message to the user that explains the content using the chat history
        prompt  = f"""
        You are a helpful assistant that explains the content of a document to the user.
        I want you to take the following chat history and write a message to the user that explains the content.
        Your response should have two parts:
        - A short explanation of the content, that include what the content is about (max four sentences), and what is the bias / motivation of the author
        - Bullet points of the most important points in the content

        Format the answer_for_chat in the response using HTML tags: <b> for bold, <br> for new line and <ul> and </ul> for the bullet points.
        The chat history is: {system_messages}
        """
        response = self._client.send_message(prompt = prompt, response_model = Answer)
        
        chat_message = Chat_Message(
            chat_id = self._doc.id,
            chat_type = "document",
            user_id = self._user_id,
            prompt = "Explain the content of the document",
            response = response.model_dump_json(),
            asked_by = "system",
            event_name = EventName.EXPLAIN_CONTENT.value 
        )
        insert_or_update_chat_history(chat_message)

        return [chat_message]
        


    async def ask_question(self, question: str) -> Chat_Message:
        """
        Ask a question using the chat session manager
        
        Args:
            question: The question to ask
            
        Returns:
            A Chat_Message object containing the response
        """
        
        # Ask the question
        try:
            # Send the question to the chat client
            _prompt = f"{question}\n\nFormat the answer_for_chat in the response using HTML tags: <b> for bold, <br> for new line and <ul> and </ul> for the bullet points."
            response = self._client.send_message(prompt=_prompt, response_model=Answer)
            
            # Store the conversation in the database
            message = Chat_Message(
                chat_id=str(self._context_id),
                chat_type=self._context_type,
                user_id=self._user_id,
                prompt=_prompt,
                asked_by="user",
                response=response.model_dump_json() if hasattr(response, "model_dump_json") else json.dumps(response),
                event_name=EventName.MANUAL_MESSAGE.value
            )
            message = insert_or_update_chat_history(message)
            
            return message
            
        except Exception as e:
            logger.error(f"Error in ask_question: {str(e)}")
            # Create an error message
            error_response = {
                "answer_for_chat": f"I'm sorry, I encountered an error: {str(e)}",
                "short_answer_for_computer": f"Error: {str(e)}",
                "citations": [],
                "status": "error"
            }
            
            message = Chat_Message(
                chat_id=str(self._context_id),
                chat_type=self._context_type,
                user_id=self._user_id,
                prompt=_prompt,
                asked_by="user",
                response=json.dumps(error_response),
                event_name=EventName.ERROR.value
            )
            message = insert_or_update_chat_history(message)
            
            return message

    
    


    @classmethod    
    def chat_status(cls, document_id: str) -> bool:
        """
        Check if all required chat steps are completed for a document
        
        Args:
            document_id: The document ID to check
            
        Returns:
            True if all required steps are completed, False otherwise
        """
        event_names = [message.event_name for message in getters.get_chat_history(document_id)]

        if len(event_names) == 0:
            return False

        enum_values = ['init_doc_chat', 'content_type', 'content_title', 'summary']

        for enum_value in enum_values:
            if enum_value not in event_names:
                return False

        return True
    
    @classmethod
    def get_initial_chat_history(cls, document_id: str) -> list[Chat_Message]:
        """
        Get the initial chat history for a document, including summary and user messages
        
        Args:
            document_id: The document ID
            
        Returns:
            A list of Chat_Message objects
        """
        chat = getters.get_chat_history(document_id)

        ## Filter out message with event_name = SUMMARY, 
        initial_chat_history = [message for message in chat if message.event_name in [EventName.SUMMARY.value]]
        user_messages = [message for message in chat if message.asked_by == "user"]

        ## Add the user messages to the chat history
        initial_chat_history.extend(user_messages)
        initial_chat_history.sort(key=lambda x: x.created_at)

        return initial_chat_history
    






