import json
from typing import Callable
from pydantic import BaseModel
import logging

from app.gemini_chat_client import ChatClient
import app.getters as getters
from google.genai.types import GenerateContentConfig

from app.app_logic import insert_chat_history
from app.models import Chat_History, EventName

# Set up logger
logger = logging.getLogger(__name__)

class Answer(BaseModel):
    long_answer: str
    short_answer: str
    citations: list[str]
    
    def __str__(self):
        return self.short_answer
    
   
    
class ContentType(BaseModel):
    content_type: str
    
    def __str__(self):
        return self.content_type
    

class Topic(BaseModel):
    topics: list[str]
    
    def __str__(self):
        return str(self.topics)
    
class Graph(BaseModel):
    subject: str
    predicate: str
    object: str
    
    def __str__(self):
        return f"{self.subject} {self.predicate} {self.object}"

class Graphs(BaseModel):
    graphs: list[Graph]
    
class Type(BaseModel):
    type: str
    name: str
    description: str
    
    def __str__(self):
        return f"{self.type} {self.name} {self.description}"

class Types(BaseModel):
    types: list[Type]
    
    def __str__(self):
        return str(self.types)

class InitiateDocumentChat:
    def __init__(self, document_id: str, temperature: float = 0.5):
        self.doc = getters.get_document_by_id(document_id)
        self.source = getters.get_source_by_document_id(document_id)
        self.client = ChatClient(response_schema = Answer)
        self.temperature = temperature
        
    def init_doc_chat(self, listener: Callable):
        try:
            ## Get the chat history and if it exists, send event that the chat is already initiated
            chat_history = getters.get_chat_history(self.doc.id)
            if len(chat_history) > 2:
                event_data = {
                    "name": EventName.CHAT_ALREADY_INITIATED.value,
                    "doc_id": str(self.doc.id),
                    "ask": "The chat is already initiated",
                    "response": "The chat is already initiated"
                }
                listener(event_data)
                return
            
            content_types = getters.get_content_types()
            entity_types = getters.get_entity_types()
            _user_id = self.source.user_id
            
            try:
                _prompt = "This is the content we are going to analyze: {SUPPORT_INFO}"
                response = self.client.send_message(prompt = _prompt, prompt_support_info = self.source.html_root_element)
                
                chat_history = Chat_History(
                    chat_id = self.doc.id,
                    chat_type = "document",
                    user_id = _user_id,
                    prompt = _prompt,
                    asked_by = "system",
                    response = json.dumps({"response": response})
                )
                insert_chat_history(chat_history)
            except Exception as e:
                logger.error(f"Error analyzing content: {str(e)}")
                event_data = {
                    "name": EventName.ERROR.value,
                    "doc_id": str(self.doc.id),
                    "ask": _prompt,
                    "response": f"Error analyzing content: {str(e)}"
                }
                listener(event_data)
            
            try:
                content_type_prompt_1 = """Categorize the type of the content; """
                content_type_prompt_2 = """Is it news article, blog post, product description, etc. Use the following content types as a reference: {SUPPORT_INFO}"""
                
                content_type_answer = self.client.send_message(prompt=content_type_prompt_1 + content_type_prompt_2, 
                                                               prompt_support_info=content_types, response_model=ContentType)

                chat_history = Chat_History(
                    chat_id = self.doc.id,
                    chat_type = "document",
                    user_id = _user_id,
                    prompt = content_type_prompt_1,
                    asked_by = "system",
                    response = content_type_answer.model_dump_json()
                )
                chat_history = insert_chat_history(chat_history)
            except Exception as e:
                logger.error(f"Error categorizing content type: {str(e)}")
                content_type_answer = ContentType(content_type="")
                event_data = {
                    "name": EventName.ERROR.value,
                    "doc_id": str(self.doc.id),
                    "ask": content_type_prompt_1,
                    "response": f"Error categorizing content: {str(e)}"
                }
                listener(event_data)
            
            try:
                if content_type_answer.content_type:
                    main_idea_prompt = f"What is the main idea, message or topic of the {content_type_answer.content_type}?"
                else:
                    main_idea_prompt = "What is the main idea, message or topic of the content?"
                
                main_idea_answer = self.client.send_message(prompt=main_idea_prompt, response_model=Answer)
                if len(main_idea_answer.short_answer) > 0:
                    chat_history = Chat_History(
                        chat_id = self.doc.id,
                        chat_type = "document",
                        user_id = _user_id,
                        prompt = main_idea_prompt,
                        asked_by = "user",
                        response = main_idea_answer.model_dump_json()
                    )
                    chat_history = insert_chat_history(chat_history)

                    event_data = {
                        "name": EventName.INIT_DOC_CHAT.value,
                        "doc_id": str(self.doc.id),
                        "chat_id": chat_history.id,
                        "ask": main_idea_prompt,
                        "response": str(main_idea_answer)[:100]
                    }
                    listener(event_data)
                else:
                    event_data = {
                        "name": EventName.INIT_DOC_CHAT.value,
                        "doc_id": str(self.doc.id),
                        "ask": main_idea_prompt,
                        "response": "Problem"
                    }
                    listener(event_data)
            except Exception as e:
                logger.error(f"Error getting main idea: {str(e)}")
                event_data = {
                    "name": EventName.ERROR.value,
                    "doc_id": str(self.doc.id),
                    "ask": main_idea_prompt if 'main_idea_prompt' in locals() else "Getting main idea",
                    "response": f"Error getting main idea: {str(e)}"
                }
                listener(event_data)
            
            ## Identify the level of bias in the content
            try: 
                with open("app/data/bias_categorization.json", "r") as f:
                    bias_categorization = json.load(f)
            except Exception as e:
                logger.error(f"Error loading bias categorization: {str(e)}")
                bias_categorization = []
            
            if len(bias_categorization) > 0:
                try:
                    content_type = content_type_answer.content_type if content_type_answer.content_type else "content"
                    bias_categorization_prompt_1 = f"Identify the level of bias in the {content_type}. "
                    bias_categorization_prompt_2 = """Use the following bias categorization to identify the level of bias: {SUPPORT_INFO}""".format(SUPPORT_INFO=bias_categorization)
                    
                    bias_categorization_answer = self.client.send_message(prompt=bias_categorization_prompt_1 + bias_categorization_prompt_2, response_model=Answer)
                    
                    if len(bias_categorization_answer.short_answer) > 0:
                        chat_history = Chat_History(
                            chat_id = self.doc.id,
                            chat_type = "document",
                            user_id = _user_id,
                            prompt = bias_categorization_prompt_1,
                            asked_by = "user",
                            response = bias_categorization_answer.model_dump_json()
                        )
                        chat_history = insert_chat_history(chat_history)
                        
                        event_data = {
                            "name": EventName.BIAS_CATEGORIZATION.value,
                            "doc_id": str(self.doc.id),
                            "chat_id": chat_history.id,
                            "ask": bias_categorization_prompt_1,
                            "response": str(bias_categorization_answer)[:100]
                        }
                        listener(event_data)
                    else:
                        event_data = {
                            "name": EventName.BIAS_CATEGORIZATION.value,
                            "doc_id": str(self.doc.id),
                            "ask": bias_categorization_prompt_1,
                            "response": "Problem"
                        }
                        listener(event_data)
                except Exception as e:
                    logger.error(f"Error identifying bias: {str(e)}")
                    event_data = {
                        "name": EventName.ERROR.value,
                        "doc_id": str(self.doc.id),
                        "ask": bias_categorization_prompt_1 if 'bias_categorization_prompt_1' in locals() else "Identifying bias",
                        "response": f"Error identifying bias: {str(e)}"
                    }
                    listener(event_data)
            
            
            ## Identify the entities in the content
            try:
                if content_type_answer.content_type:
                    entities_prompt_1 = f"Identify the types of the entities mentioned in the {content_type_answer.content_type}"
                else:
                    entities_prompt_1 = "Identify the types of the entities mentioned in the content"
            
                entities_prompt_2 = """"using the schema.org RDF file. Describe the type in the context of the content. The schema.org RDF: {SUPPORT_INFO}"""
                
                entities_answer = self.client.send_message(prompt=entities_prompt_1 + entities_prompt_2, 
                                                          prompt_support_info=entity_types, response_model=Types)
                if len(entities_answer.types) > 0:
                    chat_history = Chat_History(
                        chat_id = self.doc.id,
                        chat_type = "document",
                        user_id = _user_id,
                        prompt = entities_prompt_1,
                        asked_by = "user",
                        response = entities_answer.model_dump_json()
                    )
                    chat_history = insert_chat_history(chat_history)
                    
                    event_data = {
                        "name": EventName.ENTITIES.value,
                        "doc_id": str(self.doc.id),
                        "chat_id": chat_history.id,
                        "ask": entities_prompt_1,
                        "response": str(entities_answer)[:100]
                    }
                    listener(event_data)
                else:
                    event_data = {
                        "name": EventName.ENTITIES.value,
                        "doc_id": str(self.doc.id),
                        "ask": entities_prompt_1,
                        "response": "Problem"
                    }
                    listener(event_data)
            except Exception as e:
                logger.error(f"Error identifying entities: {str(e)}")
                event_data = {
                    "name": EventName.ERROR.value,
                    "doc_id": str(self.doc.id),
                    "ask": entities_prompt_1 if 'entities_prompt_1' in locals() else "Identifying entities",
                    "response": f"Error identifying entities: {str(e)}"
                }
                listener(event_data)
        except Exception as e:
            logger.error(f"Error in init_doc_chat: {str(e)}")
            event_data = {
                "name": EventName.ERROR.value,
                "doc_id": str(self.doc.id) if hasattr(self, 'doc') and hasattr(self.doc, 'id') else "unknown",
                "ask": "Initializing document chat",
                "response": f"Error initializing document chat: {str(e)}"
            }
            try:
                listener(event_data)
            except Exception as listener_error:
                logger.error(f"Error sending error to listener: {str(listener_error)}")
        