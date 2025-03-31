from pydantic import BaseModel
from typing import List, Optional, Dict, Type
import json
import logging

# Set up logger
logger = logging.getLogger(__name__)

from enum import Enum

# Model registry to map model names to their classes
MODEL_REGISTRY: Dict[str, Type[BaseModel]] = {}

def register_model(model_class: Type[BaseModel]) -> Type[BaseModel]:
    """Register a model class in the registry"""
    MODEL_REGISTRY[model_class.__name__] = model_class
    return model_class

def get_model_class(model_name: str) -> Optional[Type[BaseModel]]:
    """Get a model class by its name"""
    return MODEL_REGISTRY.get(model_name)

class Status(Enum):
    ERROR = "Error"
    SUCCESS = "Success"

@register_model
class Answer(BaseModel):
    answer_for_chat: str
    short_answer_for_computer: str
    text_used_for_answer: list[str]
    status: Status
    
    def __str__(self):
        return self.short_answer_for_computer

@register_model
class SuggestedQuestions(BaseModel):
    questions: list[str]
    status: Status
    
    def __str__(self):
        return json.dumps(self.questions)

@register_model
class PageContent(BaseModel):
    detailed_summary: str
    author: str = None
    title: str = None
    url: str = None
    tags: list[str] = None
    published_date: str = None
    status: Status
    
    def __str__(self):
        return self.text

    
@register_model
class ContentType(BaseModel):
    content_type: str
    status: Status
    
    def __str__(self):
        return self.content_type

@register_model
class Summary(BaseModel):
    summary_for_chat: str
    important_bullet_points: list[str]
    text_used_for_answer: list[str]
    status: str
    def __str__(self):
        return self.summary_for_chat

@register_model
class Topic(BaseModel):
    topics: list[str]
    status: str
    def __str__(self):
        return str(self.topics)
    
@register_model
class Graph(BaseModel):
    subject: str
    predicate: str
    object: str
    status: Status
    
    def __str__(self):
        return f"{self.subject} {self.predicate} {self.object}"

@register_model
class Graphs(BaseModel):
    graphs: list[Graph]
    status: Status

@register_model
class Type(BaseModel):
    type: str
    name: str
    description: str
    status: Status
    def __str__(self):
        return f"{self.type} {self.name} {self.description}"

@register_model
class Types(BaseModel):
    types: list[Type]
    status: str
    def __str__(self):
        return str(self.types)

@register_model
class ChatMessagePublic(BaseModel):
    id: str
    chat_id: str
    question: str
    answer: str
    created_at: str

def chat_messages_to_document(chat_messages, document):
    """
    Convert chat messages with different event types into a Document object
    
    Args:
        chat_messages: List of Chat_Message objects
        document: Document object to update
        
    Returns:
        A Document object with data extracted from the chat messages
    """
    from app.models import EventName, Entity
    
    if not chat_messages:
        return None
    
    # Extract data from different event types
    for message in chat_messages:
        try:
            # Parse the response JSON
            response_data = message.response
            if isinstance(response_data, str):
                response_data = json.loads(response_data)
                
            # Process based on event type
            if message.event_name == EventName.SUMMARY.value:
                # Extract summary data
                summary = Summary(**response_data)
                document.is_about = summary.summary_for_chat
                document.tldr = summary.important_bullet_points
                
            elif message.event_name == EventName.CONTENT_TITLE.value:
                # Extract title data
                answer = Answer(**response_data)
                document.title = answer.short_answer_for_computer
                
            elif message.event_name == EventName.CONTENT_TYPE.value:
                # Extract content type
                content_type = ContentType(**response_data)
                document.source_type = content_type.content_type
                
            elif message.event_name == EventName.ENTITIES.value:
                # Extract entities
                types_data = Types(**response_data)
                entities = []
                
                for entity_type in types_data.types:
                    entity = Entity(
                        id=f"{chat_messages[0].chat_id}_{entity_type.name}",  # Create a unique ID
                        name=entity_type.name,
                        description=entity_type.description,
                        type=entity_type.type
                    )
                    entities.append(entity)
                
                document.entities_and_concepts = entities
                
        except Exception as e:
            logger.error(f"Error processing message with event {message.event_name}: {str(e)}")
    
    return document 
