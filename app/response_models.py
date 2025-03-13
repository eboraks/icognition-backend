from pydantic import BaseModel
from typing import List
import json
import logging

# Set up logger
logger = logging.getLogger(__name__)

class Answer(BaseModel):
    answer_for_chat: str
    short_answer_for_computer: str
    text_used_for_answer: list[str]
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
    text_used_for_answer: list[str]
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

class ChatMessagePublic(BaseModel):
    id: str
    chat_id: str
    question: str
    answer: str
    created_at: str

def chat_messages_to_document_public(chat_messages, document):
    """
    Convert chat messages with different event types into a DocumentPublic object
    
    Args:
        chat_messages: List of Chat_Message objects
        document: DocumentPublic object to update
        
    Returns:
        A DocumentPublic object with data extracted from the chat messages
    """
    from app.models import EventName, EntityPublic
    
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
                    entity = EntityPublic(
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