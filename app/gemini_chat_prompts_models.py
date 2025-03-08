import json
from typing import Callable
from pydantic import BaseModel
import logging

from app.gemini_chat_client import ChatClient
import app.getters as getters
from google.genai.types import GenerateContentConfig

from app.app_logic import insert_chat_history
from app.models import Chat_Message, EventName

# Set up logger
logger = logging.getLogger(__name__)


class ChatMessagePublic(BaseModel):
    id: str
    chat_id: str
    question: str
    answer: str
    created_at: str


    



class Answer(BaseModel):
    answer_for_chat: str
    short_answer_for_computer: str
    citations: list[str]
    status: str
    
    def __str__(self):
        return self.short_answer_for_computer
    
    
class ContentType(BaseModel):
    content_type: str
    status: str
    
    def __str__(self):
        return self.content_type
    
class Summary(BaseModel):
    summary_for_chat: str
    important_bullet_points: list[str]
    citations: list[str]
    status: str
    def __str__(self):
        return self.summary_for_chat


class Topic(BaseModel):
    topics: list[str]
    status: str
    def __str__(self):
        return str(self.topics)
    
class Graph(BaseModel):
    subject: str
    predicate: str
    object: str
    status: str
    
    def __str__(self):
        return f"{self.subject} {self.predicate} {self.object}"

class Graphs(BaseModel):
    graphs: list[Graph]
    status: str

class Type(BaseModel):
    type: str
    name: str
    description: str
    status: str
    def __str__(self):
        return f"{self.type} {self.name} {self.description}"

class Types(BaseModel):
    types: list[Type]
    status: str
    def __str__(self):
        return str(self.types)

class GeminiChatHandler:
    def __init__(self, document_id: str, user_id: str, temperature: float = 0.5, event_listener: Callable = None):
        self._doc = getters.get_document_by_id(document_id)
        self._source = getters.get_source_by_document_id(document_id)
        self._user_id = user_id
        
        with open("app/chat_workflows/chat_system_instructions.txt", "r") as f: 
            self._system_instruction = f.read()
        
        self._client = ChatClient(response_model = Answer, system_instruction = self._system_instruction)
        self._temperature = temperature
        self._event_listener = event_listener
    
    def _process_chat_step(self, _the_ask_prompt: str, 
                           _support_prompt: str, _response_model: BaseModel, 
                           _asked_by: str = "system", _chat_type: str = "document", _event_name: str = EventName.INIT_DOC_CHAT.value):
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
                    message = insert_chat_history(message)
                    event_data = {
                        "name": _event_name,
                        "doc_id": str(self._doc.id),
                        "chat_id": message.id,
                        "ask": _the_ask_prompt,
                        "response": str(response)[:100]
                    }
                    self._event_listener(event_data)
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
                message = insert_chat_history(message)
                event_data = {
                    "name": _event_name,
                    "doc_id": str(self._doc.id),
                    "chat_id": message.id,
                    "ask": _the_ask_prompt,
                    "response": str(response)[:100]
                }
                self._event_listener(event_data)
                
                return response
            else:
                logger.error(f"Error in _process_chat_step: {response}")
                event_data = {
                    "name": EventName.ERROR.value,
                    "doc_id": str(self._doc.id),
                    "ask": _the_ask_prompt,
                    "response": response
                }
                self._event_listener(event_data)
                return response
            
        except Exception as e:
            logger.error(f"Error in _process_chat_step: {str(e)}")
            event_data = {
                "name": EventName.ERROR.value,
                "doc_id": str(self._doc.id),
                "ask": _the_ask_prompt,
                "response": f"Error in _process_chat_step: {str(e)}"
            }
            self._event_listener(event_data)
            return None
    
        
    def start_analyze(self):
        

        ## If the chat is already initiated, send event that the chat is already initiated
        if ChatStorageHandler.chat_status(self._doc.id):
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
        
        
        if EventName.INIT_DOC_CHAT.value not in event_names:
            content_response = self._process_chat_step(
                _the_ask_prompt = "This is the content we are going to analyze: ",
                _support_prompt = self._source.html_root_element,
                _response_model = None,
                _asked_by = "system",
                _chat_type = "document",
                _event_name = EventName.INIT_DOC_CHAT.value
            )
        
        if content_response is None:
            logger.error("Error in content response")
            return
        
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
            
        if EventName.ENTITIES.value not in event_names:
            self._process_chat_step(
                _the_ask_prompt = f"Identify the entities in the {content_name}",
                _support_prompt = """Use the following schema.org entities as a reference: """ + str(entity_types),
                _response_model = Types,
                _asked_by = "system",
                _chat_type = "document",
            _event_name = EventName.ENTITIES.value
            )
            
    
class ChatStorageHandler:
    
    @classmethod    
    def chat_status(self, document_id: str) -> bool:

        event_names = [message.event_name for message in getters.get_chat_history(document_id)]

        if len(event_names) == 0:
            return False

        enum_values = ['init_doc_chat', 'content_type', 'content_title', 'summary']

        for enum_value in enum_values:
            if enum_value not in event_names:
                return False

        return True
    

    
    @classmethod
    def get_initial_chat_history(self, document_id: str) -> list[Chat_Message]:

        chat = getters.get_chat_history(document_id)

        ## Filter out message with event_name = SUMMARY, 
        initial_chat_history = [message for message in chat if message.event_name in [EventName.SUMMARY.value]]
        user_messages = [message for message in chat if message.asked_by == "user"]

        
        ## Add the user messages to the chat history
        initial_chat_history.extend(user_messages)
        initial_chat_history.sort(key=lambda x: x.created_at)


        return initial_chat_history
