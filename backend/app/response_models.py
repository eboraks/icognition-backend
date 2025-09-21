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
class InitialSummary(BaseModel):
    answer_for_chat: str
    content_type: str
    key_concepts_and_arguments: list[str]
    citations_from_source: list[str]
    status: Status
    
    def __str__(self):
        return self.summary

@register_model
class ExtractedEntity(BaseModel):
    type: str
    name: str
    description: str
    status: Status
    def __str__(self):
        return f"{self.type} {self.name} {self.description}"

@register_model
class Entities(BaseModel):
    entities: list[ExtractedEntity]
    status: str
    def __str__(self):
        return str(self.entities)

@register_model
class ChatMessagePublic(BaseModel):
    id: str
    chat_id: str
    question: str
    answer: str
    created_at: str

@register_model
class MatchResult(BaseModel):
    best_match_index: int
    match_confidence: float
    reasoning: str
    def __str__(self):
        return f"Match index: {self.best_match_index}, confidence: {self.match_confidence}"

