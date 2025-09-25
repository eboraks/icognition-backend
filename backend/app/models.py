from enum import Enum
import json, logging, sys
import uuid as uuid_pkg
from sqlmodel import SQLModel, Field, Float, JSON, Integer, Relationship, String
from sqlalchemy import Column, Index, DateTime, func, Text, FLOAT
from sqlalchemy.dialects.postgresql import JSONB, ARRAY, TSVECTOR
from pgvector.sqlalchemy import Vector
from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, ConfigDict
from app.icog_util import remove_none_header_elements

from app.gemini_client import GeminiClient


logging.basicConfig(
    stream=sys.stdout,
    format="%(asctime)s - %(message)s - %(filename)s:%(lineno)d",
    level=logging.INFO,
    datefmt="%Y-%m-%d %H:%M:%S",
)


class QuestionAnswerStatus(Enum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED_SAVE = "COMPLETED_SAVE"
    COMPLETED_NO_SAVE = "COMPLETED_NO_SAVE"
    FAILED = "FAILED"


class TreeNode(BaseModel):
    "Tree Node Model based on primevue Tree data filter"
    key: str
    label: str
    data: Optional[str] = None
    doc_count: Optional[int] = None
    doc_ids: Optional[list[str]] = None
    children: Optional[list["TreeNode"]] = None



class Document_Entity_Link(SQLModel, table=True):
    """
    Represents a link between a document and an entity.
    """
    __table_args__ = {'extend_existing': True}

    document_id: Optional[uuid_pkg.UUID] = Field(
        default=None, foreign_key="document.id", primary_key=True
    )
    entity_id: Optional[str] = Field(
        default=None, foreign_key="entities.id", primary_key=True
    )


class Entity_User_Link(SQLModel, table=True):
    """
    Represents a link between a document and an entity.
    """

    entity_id: Optional[str] = Field(
        default=None, foreign_key="entities.id", primary_key=True
    )
    user_id: Optional[str] = Field(
        default=None, foreign_key="users.id", primary_key=True
    )



# Removed old Entity model - using NewEntity as Entity instead

    def to_node(self):
        return TreeNode(
            key=(self.name + self.type).replace(" ", "").lower(),
            label=f"{self.name} ({len(self.documents)})",
            data=self.description,
            doc_count=len(self.documents),
            doc_ids=[str(doc.id) for doc in self.documents],
            children=[],
        )

    
    def to_embeddings(self) -> list["Embedding"]:
        """
        Converts the model instance to a list of Embeddings objects.

        Returns:
            A list of Embeddings objects representing the model instance.
        """
        results = []

        if self.description and self.name:

            _text = f"{self.name} - {self.description}"

            results.append(
                Embedding(
                    source_type="entity",
                    source_id=self.id,
                    version=self.version,
                    field="entity_name_description",
                    text=_text,
                )
            )

        return results


class Document(SQLModel, table=True):
    """
    Consolidated Document model with AI analysis capabilities and user isolation.
    Combines features from both legacy and new Document models.
    """

    id: uuid_pkg.UUID = Field(default_factory=uuid_pkg.uuid4, primary_key=True)
    
    # Timestamps
    created_at: Optional[datetime] = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime(timezone=True), server_default=func.now())
    )
    updated_at: Optional[datetime] = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    )
    
    # User association (from new model)
    user_id: Optional[str] = Field(default=None, foreign_key="users.id", index=True, nullable=True)
    
    # Document identification
    title: str = Field(default=None, nullable=True)
    url: str = Field(default=None, nullable=True)
    source_type: str = Field(default=None, nullable=True)
    content_type: str = Field(default=None, nullable=True)
    
    # Content source tracking (from new model)
    content_source: str = Field(default="url", max_length=20, nullable=True)  # "url", "html", "text"
    
    # Document metadata
    authors: str = Field(default=None, nullable=True)
    metadata_keywords: str = Field(default=None, nullable=True)
    metadata_description: str = Field(default=None, nullable=True)
    locale: str = Field(default=None, nullable=True)
    image_url: str = Field(default=None, nullable=True)
    site_name: str = Field(default=None, nullable=True)
    
    # Content storage (consolidated from both models)
    source_text_in_html: str = Field(default=None, nullable=True)  # Legacy field
    raw_html: Optional[str] = Field(default=None, sa_column=Column(Text))  # New field
    content: Optional[str] = Field(default=None, sa_column=Column(Text))  # New field
    content_vector: Optional[List[float]] = Field(default=None, sa_column=Column(Vector(1536)))  # New field
    
    # AI analysis fields (legacy model)
    ai_is_about: str = Field(default=None, nullable=True)
    ai_bullet_points: List[str] = Field(default=[], sa_column=Column(JSON))
    ai_citations: List[Dict] = Field(default=[], sa_column=Column(JSON))
    
    # Publication and processing
    publication_date: datetime = Field(default=None, nullable=True)
    update_at: datetime = Field(default_factory=datetime.now, nullable=True)  # Legacy field
    
    # Advanced metadata
    llm_service_meta: Optional[Dict] = Field(default={}, sa_column=Column(JSONB))
    types_and_concepts: Optional[List[Dict]] = Field(default=[], sa_column=Column(JSONB))
    cosine_similarity: float = Field(default=0.0, nullable=True)
    document_metadata: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(JSON))  # New field
    
    # Remove original_text, html_elements, and raw_answer as they're stored elsewhere
    # These fields will be migrated out later

    # Removed entities relationship to avoid conflicts with Entity model
    qans: list["Question_Answer"] = Relationship(back_populates="document")
    
    def to_display(self) -> dict:
        return {
            "id": str(self.id),
            "title": self.title,
            "url": self.url,
            "source_type": self.source_type,
            "content_type": self.content_type,
            "authors": self.authors,
            "publication_date": self.publication_date,
            "site_name": self.site_name,
            "cosine_similarity": self.cosine_similarity,
            "ai_is_about": self.ai_is_about,
            "ai_bullet_points": self.ai_bullet_points,
            
        }
    
    

    def to_embeddings(self) -> list["Embedding"]:
        """
        Converts the model instance to a list of Embeddings objects.

        Returns:
            A list of Embeddings objects representing the model instance.
        """
        results = []

        if self.ai_is_about:
            results.append(
                Embedding(
                    source_type="document",
                    source_id=self.id,
                    field="is_about",
                    text=self.ai_is_about,
                )
            )

        if self.metadata_keywords:
            results.append(
                Embedding(
                    source_type="document",
                    source_id=self.id,
                    field="ai_short_summary",
                    text=self.ai_short_summary,
                )
            )

        if self.ai_bullet_points:
            for bullet_point in self.ai_bullet_points:
                results.append(
                    Embedding(
                        source_type="document",
                        source_id=self.id,
                        field="summary_bullet_points",
                        text=bullet_point,
                    )
                )
        if self.title:
            results.append(
                Embedding(
                    source_type="document",
                    source_id=self.id,
                    field="title",
                    text=self.title,
                )
            )

        return results

    def get_source_text_as_string(self) -> str:
        """
        Converts the source_text_in_html dictionary into a formatted string.
        Each element is processed according to its type (h1-h6, p, etc.) and
        formatted appropriately.

        Returns:
            str: A formatted string representation of the HTML content
        """
        if not self.source_text_in_html:
            return ""
            
        try:
            # Parse the JSON string if it's a string
            elements = json.loads(self.source_text_in_html) if isinstance(self.source_text_in_html, str) else self.source_text_in_html
            
            result = []
            for element in elements:
                if not isinstance(element, dict) or 'element' not in element or 'text' not in element:
                    continue
                    
                element_type = element['element'].lower()
                text = element['text'].strip()
                
                if not text:
                    continue
                    
                # Format based on element type
                if element_type.startswith('h') and len(element_type) == 2 and element_type[1] in '123456':
                    # Headers get a newline before and after
                    result.append(f"\n{text}\n")
                elif element_type == 'p':
                    # Paragraphs get a newline after
                    result.append(f"{text}\n")
                else:
                    # Other elements just get added as is
                    result.append(text)
                    
            return ' '.join(result).strip()
            
        except (json.JSONDecodeError, TypeError) as e:
            logging.error(f"Error processing source_text_in_html for document {self.id}: {e}")
            return ""

    async def generate_vector(self, geminiClient: GeminiClient):

        try:
            if self.ai_is_about and self.ai_bullet_points:
                text = f"{self.ai_is_about} \n"
                for bullet_point in self.ai_bullet_points:
                    text += f"{bullet_point} \n"
                self.ai_summary_vector = await geminiClient.generate_embedding(
                    content=text, title=self.title
                )
                return self.ai_summary_vector

            else:
                return None
        except Exception as e:
            # Handle the exception here
            logging.error(
                f"An error occurred while generating summary vector for document_id: {self.id}. Error: {e}"
            )
            return None


## Models to be used in the Gemini API responses
class Verbatim(BaseModel):
    verbatim_text: str


class DocumentCitation(BaseModel):
    document_id: str
    verbatims: list[Verbatim]

    def get_verbatims(self) -> list[dict]:
        """ "Return the citations as a list of dictionaries for stroing as JSON in DB"""
        return [c.__dict__ for c in self.verbatims]

    def to_dict(self) -> dict:
        return {"document_id": self.document_id, "verbatims": self.get_verbatims()}


class RagAnswerPublic(BaseModel):
    uuid: Optional[str] = None
    status: Optional[str] = None
    question: Optional[str] = None
    answer: Optional[str] = None
    answer_in_html: Optional[bool] = False
    documents_used: Optional[List[str]] = None
    citations: Optional[list[DocumentCitation]] = None
    llm_service_meta: Optional[dict] = None
    created_at: Optional[str] = None


class Question_Answer(SQLModel, table=True):
    """
    Represents a question answer with its ID, question, answer, and document ID.
    """

    uuid: uuid_pkg.UUID = Field(default_factory=uuid_pkg.uuid4, primary_key=True)
    question: str = Field(default=None, nullable=True)
    answer: str = Field(default=None, nullable=True)
    citations: List[dict] = Field(default=[], sa_column=Column(JSON))
    question_vector: List[float] = Field(sa_column=Column(Vector(768)))
    created_at: datetime = Field(default_factory=datetime.now, nullable=True)
    created_by: str = Field(default="AI", nullable=True)
    deleted: bool = Field(default=False, nullable=True)

    document_id: Optional[uuid_pkg.UUID] = Field(
        default=None, foreign_key="document.id"
    )
    document: Document = Relationship(back_populates="qans")

    def to_public(self) -> RagAnswerPublic:

        return RagAnswerPublic(
            uuid=str(self.uuid),
            status=QuestionAnswerStatus.COMPLETED_SAVE.value,
            question=self.question,
            answer=self.answer,
            citations=[DocumentCitation(**c) for c in self.citations],
            relevance_score=None,
            created_at=str(self.created_at),
        )



class Collection(SQLModel, table=False):
    id: str = Field(primary_key=True)
    name: Optional[str] = Field(default=None, nullable=True)
    description: Optional[str] = Field(default=None, nullable=True)
    user_id: str = Field(nullable=False)
    status: str = Field(default="PENDING", nullable=True)
    created_at: datetime = Field(default_factory=datetime.now, nullable=True)
    documents_ids: List[str] = Field(default=[], sa_column=Column(ARRAY(String)))


class Study_Collection(SQLModel, table=True):
    """
    Represents a study collection with its ID, name, description, and user ID.
    """

    id: uuid_pkg.UUID = Field(default_factory=uuid_pkg.uuid4, primary_key=True)
    name: str = Field(nullable=False)
    description: str = Field(default=None, nullable=True)
    ai_explanation: str = Field(default=None, nullable=True)
    user_id: str = Field(nullable=False)
    status: str = Field(default="PENDING", nullable=True)
    objective_tasks_vector: List[float] = Field(sa_column=Column(Vector(768)))
    # documents: list["Document"] = Relationship(back_populates="study_collection", link_model="Study_Collection_Document_Link", sa_relationship_kwargs={"cascade": "delete"})
    tasks: list["Study_Task"] = Relationship(back_populates="study_collection")
    created_at: datetime = Field(default_factory=datetime.now, nullable=True)

    async def generate_vector(self, geminiClient: GeminiClient):
        text = f"{self.description} \n"
        for task in self.tasks:
            text += f"{task.description} \n"

        self.objective_tasks_vector = await geminiClient.generate_embedding(
            content=text, title=self.name
        )

    def to_public(self) -> "StudyCollectionPublic":
        return StudyCollectionPublic(
            id=self.id,
            name=self.name,
            description=self.description,
            ai_explanation=self.ai_explanation,
            user_id=self.user_id,
            created_at=self.created_at,
            status=self.status,
            tasks=[task.to_public() for task in self.tasks],
        )


class Study_Task(SQLModel, table=True):
    """
    Represents a study task with its ID, name, description, and user ID.
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    description: str = Field(default=None)
    ai_explanation: str = Field(default=None, nullable=True)
    status: str = Field(default="PENDING", nullable=True)
    description_vector: List[float] = Field(sa_column=Column(Vector(768)))
    collection_id: Optional[uuid_pkg.UUID] = Field(
        default=None, foreign_key="study_collection.id"
    )
    study_collection: Study_Collection = Relationship(back_populates="tasks")
    citations: list["Study_Task_Citation"] = Relationship(back_populates="task")
    created_at: datetime = Field(default_factory=datetime.now, nullable=True)
    updated_at: datetime = Field(default_factory=datetime.now, nullable=True)

    async def generate_vector(self, geminiClient: GeminiClient):
        self.description_vector = await geminiClient.generate_embedding(
            content=self.description
        )

    def to_public(self) -> "StudyTaskPublic":
        return StudyTaskPublic(
            id=self.id,
            description=self.description,
            ai_explanation=self.ai_explanation,
            status=self.status,
            collection_id=self.collection_id,
            created_at=self.created_at,
            citations=[citation.to_public() for citation in self.citations],
        )


class Study_Task_Citation(SQLModel, table=True):
    """
    Represents a study task citation with its ID, task ID, and citation.
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    text_reference: Optional[List[Dict]] = Field(default=[], sa_column=Column(JSON))
    ## Intentially I didn't created relationship with Document because that will require a many to many relationship table
    ## and code to manage creation, update and deletion of the relationship.
    document_id: Optional[uuid_pkg.UUID] = Field(default=None, nullable=True)
    task_id: Optional[int] = Field(default=None, foreign_key="study_task.id")
    task: Study_Task = Relationship(back_populates="citations")
    created_at: datetime = Field(default_factory=datetime.now, nullable=True)

    def to_public(self) -> "StudyTaskCitationPublic":
        return StudyTaskCitationPublic(
            id=self.id,
            text_reference=self.text_reference,
            document_id=self.document_id,
            task_id=self.task_id,
            created_at=self.created_at,
        )


class Study_Collection_Document_Link(SQLModel, table=True):
    """
    Represents a link between a study collection and a document.
    """

    collection_id: uuid_pkg.UUID = Field(
        default=None, foreign_key="study_collection.id", primary_key=True
    )
    document_id: uuid_pkg.UUID = Field(
        default=None, foreign_key="document.id", primary_key=True
    )


###
###  The following classes are used to define the FastAPI payload and response models
###


class CollectionDocumentlinkPayload(SQLModel, table=False):
    """
    Represents the payload for linking a collection and a document.
    """

    collection_id: Optional[uuid_pkg.UUID] = Field(default=None)
    document_id: Optional[uuid_pkg.UUID] = Field(default=None)


class StudyTaskCitationPublic(SQLModel, table=False):
    """
    Represents a study task citation with its ID, task ID, and citation.
    """

    id: Optional[int] = Field(default=None)
    text_reference: Optional[List[Dict]] = Field(default=[])
    document_id: Optional[uuid_pkg.UUID] = Field(default=None)
    document_title: Optional[str] = Field(default=None)
    task_id: Optional[int] = Field(default=None)
    created_at: Optional[datetime] = Field(default=None)


class StudyTaskPublic(SQLModel, table=False):
    """
    Represents a study task with its ID, name, description, and user ID.
    """

    id: Optional[int] = Field(default=None)
    description: Optional[str] = Field(default=None)
    ai_explanation: Optional[str] = Field(default=None)
    status: Optional[str] = Field(default=None)
    collection_id: Optional[uuid_pkg.UUID] = Field(default=None)
    citations: Optional[list[StudyTaskCitationPublic]] = Field(default=[])
    created_at: Optional[datetime] = Field(default=None)


class PagePayload(SQLModel, table=False):
    """
    Represents the payload for a page, including its URL and HTML content.
    """

    url: Optional[str] = Field(default=None)
    html: Optional[str] = Field(default=None)
    user_id: str = Field(default=None, nullable=True)
    source: Optional[str] = Field(default="web", nullable=True)


class QuestionPlayload(SQLModel, table=False):
    """
    Represents the payload for a question, including the question and user ID.
    """

    question: Optional[str] = Field(default=None)
    document_id: Optional[uuid_pkg.UUID] = Field(default=None)
    collection_id: Optional[uuid_pkg.UUID] = Field(default=None)
    documents_ids: Optional[List[uuid_pkg.UUID]] = Field(default=None)
    user_id: Optional[str] = Field(default=None)


class HTTPError(SQLModel, table=False):
    """
    Represents an HTTP error with a detail message.
    """

    detail: Optional[str] = Field(default=None)


class SearchPayload(SQLModel, table=False):
    """
    Represents the payload for a search, including the query and user ID.
    """

    query: Optional[str] = Field(default=None)
    user_id: Optional[str] = Field(default=None)
    collection_id: Optional[uuid_pkg.UUID] = Field(default=None)


class Page(SQLModel, table=False):
    """
    Represents a web page with its clean URL, title, author, paragraphs, and full text.
    """

    clean_url: Optional[str] = Field(default=None)
    title: Optional[str] = Field(default=None)
    authors: Optional[List[str]] = Field(default=None)
    paragraphs: Optional[List[str]] = Field(default=None)
    full_text: Optional[str] = Field(default=None)
    html_elements: Optional[str] = Field(default=None)
    keywords: Optional[List[str]] = Field(default=None)
    locale: Optional[str] = Field(default=None)
    publish_date: Optional[datetime] = Field(default=None)
    image_url: Optional[str] = Field(default=None)
    site_name: Optional[str] = Field(default=None)
    metadata_description: Optional[str] = Field(default=None)
    html_root_element: Optional[str] = Field(default=None)




class Embedding(SQLModel, table=True):
    id: int = Field(default=None, primary_key=True)
    version: int = Field(default=1, nullable=True)
    user_id: str = Field(default=None, nullable=True)
    field: str = Field(default=None, nullable=True)
    text: str = Field(default=None, nullable=True)
    search_vector: List[int] = Field(sa_column=Column(TSVECTOR))
    source_type: str = Field(default=None, nullable=False)
    source_id: uuid_pkg.UUID = Field(default=None, nullable=False)
    vector: List[float] = Field(sa_column=Column(Vector(768)))
    update_at: datetime = Field(default_factory=datetime.now, nullable=True)
    

    def get_documnet_id(self):
        if self.source_type == "document":
            return self.source_id
        else:
            return None

    def get_entity_id(self):
        if self.source_type == "entity":
            return self.source_id
        else:
            return None


Index(
    "index_embedding_search_vector_gin", Embedding.search_vector, postgresql_using="gin"
)

index = Index(
    "index_embedding_search_vector_hnsw",
    Embedding.vector,
    postgresql_using="hnsw",
    postgresql_with={"m": 16, "ef_construction": 64},
    postgresql_ops={"vector": "vector_cosine_ops"}
)


""" 
The pydantic class is used to give JSON Schema to the AI. See how it's being used in togeher_api_client.py 
Why I used Pydantic instead of SQLModel? Good question, in my testing I was not able to get a complete JSON Schema from SQLModel.
"""


class StudyCollectionPublic(SQLModel, table=False):
    """
    Represents a study collection with its ID, name, description, and user ID.
    """

    id: Optional[uuid_pkg.UUID] = Field(default=None)
    name: str = Field(nullable=False)
    description: Optional[str] = Field(default=None)
    ai_explanation: Optional[str] = Field(default=None)
    user_id: str = Field(nullable=False)
    documents_ids: Optional[List[str]] = Field(default=[])
    status: Optional[str] = Field(default=None)
    related_docs: Optional[List[dict]] = Field(default=[])
    tasks: Optional[list[StudyTaskPublic]] = Field(default=[])
    created_at: Optional[datetime] = Field(default=None)


class Answer(BaseModel):
    question: str
    answer: str
    citations: Optional[List[str]] = None
    relevance_score: Optional[list[float]] = None


class SearchResults(BaseModel):
    documents_display: Optional[List[dict]]
    rag_answer: Optional[RagAnswerPublic]
    failure: Optional[str] = None


class Content_Type(SQLModel, table=True):
    id: int = Field(default=None, primary_key=True)
    name: str = Field(nullable=False)
    description: str = Field(nullable=False)
    category: str = Field(nullable=False)
    follow_up_questions: List[str] = Field(default=[], sa_column=Column(JSON))


class Entity_Type(SQLModel, table=True):
    id: int = Field(default=None, primary_key=True)
    name: str = Field(nullable=False)
    description: str = Field(nullable=False)
    follow_up_questions: List[str] = Field(default=[], sa_column=Column(JSON))
    
    
class Chat_Message(SQLModel, table=True):
    """Stores chat history for document interactions"""
    
    id: int = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=datetime.now, nullable=False)
    asked_by: str = Field(nullable=False)  # system, user, initial_summary
    chat_id: uuid_pkg.UUID = Field(nullable=False)
    chat_type: str = Field(nullable=False)
    user_id: str = Field(nullable=False)
    user_prompt: str = Field(nullable=False)
    ai_prompt: str = Field(nullable=False)
    event_name: str = Field(nullable=False)
    response: str = Field(sa_column=Column(JSON), default="{}")  # Store as JSON string
    response_model: str = Field(nullable=True)  # Store the model name as a string
    
    def to_dict(self) -> dict:
        """Convert Chat_Message to a JSON-serializable dictionary"""
        try:
            # Parse the response JSON string if it's a string
            response_data = json.loads(self.response) if isinstance(self.response, str) else self.response
        except json.JSONDecodeError:
            response_data = {}
            
        return {
            "id": str(self.id),
            "created_at": self.created_at.isoformat(),
            "asked_by": self.asked_by,
            "chat_id": str(self.chat_id),
            "chat_type": self.chat_type,
            "user_id": self.user_id,
            "user_prompt": self.user_prompt,
            "ai_prompt": self.ai_prompt,
            "event_name": self.event_name,
            "response": response_data
        }


class EventName(Enum):
    """Enum for event names used in event listeners"""
    ERROR = "error"
    INIT_DOC_CHAT = "init_doc_chat"
    ENTITIES = "entities"
    CONTENT_TYPE = "content_type"
    BIAS_CATEGORIZATION = "bias_categorization"
    CHAT_ALREADY_INITIATED = "chat_already_initiated"
    CONTENT_TITLE = "content_title"
    BULLETS_POINTS = "bullets_points"
    SUMMARY = "summary"
    MANUAL_MESSAGE = "manual_message"
    EXPLAIN_CONTENT = "explain_content"
    SUGGESTED_QUESTIONS = "suggested_questions"
    SOURCE_TEXT = "source_text"
    OPENING_MESSAGE = "opening_message"
    
class WebSocketMessageType(Enum):
    """Enum for WebSocket message types used in broadcasts"""
    DOCUMENT = "document"
    DOCUMENT_READY = "document_ready"
    CHAT_READY = "chat-ready"
    CHAT_NOT_READY = "chat-not-ready"
    CHAT_MESSAGE = "chat-message"
    PROGRESS_PERCENTAGE = "progress_percentage"
    DOC_QANDA = "doc_qanda"
    ERROR = "error"
    SUGGESTED_QUESTIONS = "suggested-questions"
    
class BroadcastMessage:
    """
    Simple message format for WebSocket broadcasts
    """
    
    def __init__(
        self, 
        user_id: str, 
        message_type: str, 
        data: any, 
        document_id: str = None, 
        collection_id: str = None
    ):
        """
        Initialize a broadcast message
        
        Args:
            user_id: The ID of the user to receive the message
            message_type: The type of message (string value)
            data: The message payload
            document_id: Optional document ID related to the message
            collection_id: Optional collection ID related to the message
        """
        self.user_id = user_id
        self.message_type = message_type
        self.data = data
        self.document_id = document_id
        self.collection_id = collection_id
    
    def to_json(self) -> str:
        """
        Convert the message to a JSON string
        
        Returns:
            A JSON string representation of the message
        """
        message = {
            "user_id": str(self.user_id),
            "type": self.message_type
        }
        
        # Add document_id if provided
        if self.document_id:
            message["document_id"] = str(self.document_id)
            
        # Add collection_id if provided
        if self.collection_id:
            message["collection_id"] = str(self.collection_id)
        
        # Handle data that might already be a JSON string
        data = self.data
        if isinstance(data, str):
            try:
                # Check if it's already a valid JSON string
                json.loads(data)
                # If it is, parse it to avoid double serialization
                message["data"] = json.loads(data)
            except json.JSONDecodeError:
                # Not a JSON string, use it as is
                message["data"] = data
        else:
            # Not a string, use as is
            message["data"] = data
        
        return json.dumps(message)


# =============================================================================
# NEW MODELS FROM app.db.models.py (Consolidated)
# =============================================================================

class BaseModel(SQLModel):
    """Base model with common fields"""
    
    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: Optional[datetime] = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime(timezone=True), server_default=func.now())
    )
    updated_at: Optional[datetime] = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    )
    
    model_config = ConfigDict(table=False)  # Make this an abstract base class


class VectorField:
    """Helper class for vector fields"""
    
    @staticmethod
    def create_vector_field(dimensions: int = 1536):
        """Create a vector field with specified dimensions"""
        return Field(
            sa_column=Column(ARRAY(FLOAT(precision=32)), nullable=True),
            description=f"Vector embedding with {dimensions} dimensions"
        )


# Example models for testing SQLModel integration
class TestDocument(SQLModel, table=True):
    """Test document model with vector embedding"""
    
    __tablename__ = "test_documents"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: Optional[datetime] = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime(timezone=True), server_default=func.now())
    )
    updated_at: Optional[datetime] = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    )
    
    title: str = Field(max_length=255)
    content: str
    embedding: Optional[List[float]] = VectorField.create_vector_field(1536)
    doc_metadata: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(JSON))


class TestEntity(SQLModel, table=True):
    """Test entity model"""
    
    __tablename__ = "test_entities"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: Optional[datetime] = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime(timezone=True), server_default=func.now())
    )
    updated_at: Optional[datetime] = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    )
    
    name: str = Field(max_length=255, index=True)
    description: Optional[str] = None
    entity_type: str = Field(max_length=100)
    embedding: Optional[List[float]] = VectorField.create_vector_field(1536)
    entity_metadata: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(JSON))


# User model (Firebase-based)
class User(SQLModel, table=True):
    """User model for Firebase authentication and user management"""
    
    __tablename__ = "users"
    
    id: Optional[str] = Field(default=None, primary_key=True)
    created_at: Optional[datetime] = Field(
        default_factory=datetime.now,
        sa_column=Column(DateTime(timezone=True), server_default=func.now())
    )
    updated_at: Optional[datetime] = Field(
        default_factory=datetime.now,
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    )
    
    # User profile information
    email: Optional[str] = Field(max_length=255, index=True)
    display_name: Optional[str] = Field(max_length=255)
    photo_url: Optional[str] = Field(max_length=500)
    
    # User activity tracking
    last_active: Optional[datetime] = Field(
        default_factory=datetime.now,
        sa_column=Column(DateTime(timezone=True), server_default=func.now())
    )
    
    # User preferences and settings
    preferences: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(JSON))
    
    # Account status
    is_active: bool = Field(default=True)
    is_verified: bool = Field(default=False)
    
    # Timestamps for account lifecycle
    first_login: Optional[datetime] = Field(default_factory=datetime.utcnow)
    last_login: Optional[datetime] = Field(default_factory=datetime.utcnow)


# Bookmark Management Models
class Bookmark(SQLModel, table=True):
    """Bookmark model for web page bookmarks"""

    __tablename__ = "bookmarks"

    id: uuid_pkg.UUID = Field(default_factory=uuid_pkg.uuid4, primary_key=True)
    created_at: Optional[datetime] = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime(timezone=True), server_default=func.now())
    )
    updated_at: Optional[datetime] = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    )

    # User association
    user_id: str = Field(foreign_key="users.id", index=True)

    # Document association
    document_id: Optional[uuid_pkg.UUID] = Field(foreign_key="document.id", index=True)

    # Bookmark content
    url: str = Field(max_length=2048, index=True)
    title: str = Field(max_length=500)
    description: Optional[str] = None
    content: Optional[str] = None  # Full page content for analysis

    # Metadata
    bookmark_metadata: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(JSON))

    # Status
    is_processed: bool = Field(default=False)
    processing_status: Optional[str] = Field(max_length=50, default="pending")


# New Entity model (from app.db.models)
class Entity(SQLModel, table=True):
    """Entity model for extracted entities from documents"""
    
    __tablename__ = "entities"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True, max_length=255)
    type: str = Field(index=True, max_length=50)  # Person, Product, Company, Location, Event, Technology, Topic
    description: Optional[str] = Field(default=None, sa_column=Column(Text))
    wikidata_id: Optional[str] = Field(default=None, index=True, max_length=50)
    wikidata_label: Optional[str] = Field(default=None, max_length=255)
    wikidata_description: Optional[str] = Field(default=None, sa_column=Column(Text))
    aliases: Optional[List[str]] = Field(default=None, sa_column=Column(ARRAY(Text)))
    vector: Optional[List[float]] = Field(default=None, sa_column=Column(Vector(768)))
    user_id: str = Field(foreign_key="users.id", index=True)
    created_at: Optional[datetime] = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime(timezone=True), server_default=func.now())
    )
    updated_at: Optional[datetime] = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    )


class EntityDocument(SQLModel, table=True):
    """Many-to-many relationship between entities and documents"""
    
    __tablename__ = "entity_documents"
    
    entity_id: str = Field(foreign_key="entities.id", primary_key=True)
    document_id: uuid_pkg.UUID = Field(foreign_key="document.id", primary_key=True)  # Changed to reference document table
    relevance: float = Field(default=0.0)
    created_at: Optional[datetime] = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime(timezone=True), server_default=func.now())
    )
