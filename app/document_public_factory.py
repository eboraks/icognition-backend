## Add Logger
import logging
from uuid import UUID

from app.models import EntityPublic, Chat_Message, EventName
from app.response_models import Answer, Summary, ContentType, Types

# Set up logger
logger = logging.getLogger(__name__)

import json
from typing import List, Optional, Dict


def chat_messages_to_document_dict(chat_messages: List[Chat_Message], document: Dict) -> Dict:
    """
    Convert chat messages with different event types into a document dictionary
    
    Args:
        chat_messages: List of Chat_Message objects
        document: Initial document dictionary with basic information
        
    Returns:
        A document dictionary with data extracted from the chat messages
    """
    if not chat_messages:
        return document
    
    # Initialize document with chat_id as the unique ID if not already set
    chat_id = str(chat_messages[0].chat_id)
    if "id" not in document:
        document["id"] = chat_id
    
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
                document["is_about"] = summary.summary_for_chat
                document["tldr"] = summary.important_bullet_points
                
            elif message.event_name == EventName.CONTENT_TITLE.value:
                # Extract title data
                answer = Answer(**response_data)
                document["title"] = answer.short_answer_for_computer
                
            elif message.event_name == EventName.CONTENT_TYPE.value:
                # Extract content type
                content_type = ContentType(**response_data)
                document["source_type"] = content_type.content_type
                
            elif message.event_name == EventName.ENTITIES.value:
                # Extract entities
                types_data = Types(**response_data)
                entities = []
                
                for entity_type in types_data.types:
                    entity = {
                        "id": f"{chat_id}_{entity_type.name}",  # Create a unique ID
                        "name": entity_type.name,
                        "description": entity_type.description,
                        "type": entity_type.type
                    }
                    entities.append(entity)
                
                document["entities_and_concepts"] = entities
                
        except Exception as e:
            logger.error(f"Error processing message with event {message.event_name}: {str(e)}")
    
    return document