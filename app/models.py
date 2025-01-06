from enum import Enum
import json, logging, sys
import uuid as uuid_pkg
from sqlmodel import SQLModel, Field, Float, JSON, Integer, Relationship, String
from sqlalchemy import Column, Index
from sqlalchemy.dialects.postgresql import JSONB, ARRAY, TSVECTOR
from pgvector.sqlalchemy import Vector
from typing import Optional, List, Dict
from datetime import datetime
from pydantic import BaseModel
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


"""
The SQLModel class is used to define the database schema (when table=True) or to define FastApi payload and response models (when table=False).    
"""


class Topic(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    user_id: str | None = Field(default=None)
    name: str = Field(nullable=False)
    description: str | None = Field(default=None)
    embedding: list[float] | None = Field(sa_column=Column(Vector(768)))
    subtopics: list["SubTopic"] = Relationship(back_populates="topic")


class SubTopic_Embedding_Link(SQLModel, table=True):
    """
    Represents a link between a subtopic and an embedding.
    """

    subtopic_id: Optional[int] = Field(
        default=None, foreign_key="subtopic.id", primary_key=True
    )
    embedding_id: Optional[int] = Field(
        default=None, foreign_key="embedding.id", primary_key=True
    )
    notes: Optional[str] = Field(default=None)


class SubTopic_Document_Link(SQLModel, table=True):
    """
    Represents a link between a subtopic and an document.
    """

    subtopic_id: Optional[int] = Field(
        default=None, foreign_key="subtopic.id", primary_key=True
    )
    document_id: Optional[uuid_pkg.UUID] = Field(
        default=None, foreign_key="document.id", primary_key=True
    )


class SubTopic_Entity_Link(SQLModel, table=True):
    """
    Represents a link between a subtopic and an document.
    """

    subtopic_id: Optional[int] = Field(
        default=None, foreign_key="subtopic.id", primary_key=True
    )
    entity_id: Optional[uuid_pkg.UUID] = Field(
        default=None, foreign_key="entity.id", primary_key=True
    )


class SubTopicDisplay(BaseModel):
    id: Optional[int]
    name: Optional[str]
    description: Optional[str]
    number_of_docs: Optional[int]
    docs_ids: Optional[List[int]]
    ents_ids: Optional[List[int]]
    key_words: Optional[str]


class SubTopic(SQLModel, table=True):
    """
    Represents a subtopic with its ID, name, description, and parent topic ID.
    """

    id: int = Field(default=None, primary_key=True)
    user_id: str | None = Field(nullable=False)
    name: str = Field(nullable=False)
    name_update_at: datetime = Field(default=datetime.now(), nullable=True)
    vector: List[float] | None = Field(sa_column=Column(Vector(768)))
    description: str | None = Field(default=None, nullable=True)
    key_words: str | None = Field(default=None)
    topic_id: int | None = Field(default=None, foreign_key="topic.id")
    topic: Topic = Relationship(back_populates="subtopics")
    update_at: datetime = Field(default_factory=datetime.now, nullable=True)
    embeddings: list["Embedding"] = Relationship(
        back_populates="subtopics",
        link_model=SubTopic_Embedding_Link,
        sa_relationship_kwargs={"cascade": "delete"},
    )
    documents: list["Document"] = Relationship(
        back_populates="subtopics",
        link_model=SubTopic_Document_Link,
        sa_relationship_kwargs={"cascade": "delete"},
    )
    entities: list["Entity"] = Relationship(
        back_populates="subtopics",
        link_model=SubTopic_Entity_Link,
        sa_relationship_kwargs={"cascade": "delete"},
    )

    def entities_agg_string(self):
        # Create string with each entity nanme, type and description
        results = ""
        for emb in self.embeddings:
            results += f"{emb.text}\n"
        return results

    def to_node(self):

        _docs_ids = [doc.id for doc in self.documents]
        for entity in self.entities:
            _docs_ids.extend([doc.id for doc in entity.documents])

        _docs_ids = list(set(_docs_ids))
        return TreeNode(
            key=self.id,
            doc_count=len(_docs_ids),
            label=f"{self.name.title()} ({len(_docs_ids)})",
            data=self.description,
            doc_ids=_docs_ids,
            children=[],
        )

    def to_display(self) -> "SubTopicDisplay":

        ## Get all the documents ids from the subtopic and its entities
        _docs_ids = [doc.id for doc in self.documents]
        for entity in self.entities:
            _docs_ids.extend([doc.id for doc in entity.documents])

        _docs_ids = list(set(_docs_ids))
        return SubTopicDisplay(
            id=self.id,
            name=self.name,
            description=self.description,
            number_of_docs=len(_docs_ids),
            docs_ids=_docs_ids,
            ents_ids=[ent.id for ent in self.entities],
            key_words=self.key_words,
        )


class Document_Entity_Link(SQLModel, table=True):
    """
    Represents a link between a document and an entity.
    """

    document_id: Optional[uuid_pkg.UUID] = Field(
        default=None, foreign_key="document.id", primary_key=True
    )
    entity_id: Optional[uuid_pkg.UUID] = Field(
        default=None, foreign_key="entity.id", primary_key=True
    )
    verbatim_text: Optional[str] = Field(default=None)
    description: Optional[str] = Field(default=None)


class Entity_User_Link(SQLModel, table=True):
    """
    Represents a link between a document and an entity.
    """

    entity_id: Optional[uuid_pkg.UUID] = Field(
        default=None, foreign_key="entity.id", primary_key=True
    )
    user_id: Optional[str] = Field(
        default=None, foreign_key="user.id", primary_key=True
    )


class EntityPublic(BaseModel):
    id: Optional[str]
    name: Optional[str]
    verbatim_text: Optional[str] = None
    description: Optional[str] = None
    source: Optional[str] = None
    type: Optional[str] = None


class Entity(SQLModel, table=True):
    """
    Represents an entity with its ID, document ID, name, description, source, type, Wikidata ID, and score.
    """

    id: uuid_pkg.UUID = Field(default_factory=uuid_pkg.uuid4, primary_key=True)
    version: int = Field(default=1, nullable=True)
    name: str = Field(default=None, nullable=True)
    normalized_label: str = Field(default=None, nullable=True)
    name_vector: List[float] | None = Field(sa_column=Column(Vector(768)))
    verbatim_text: str = Field(default=None, nullable=True)
    description: str = Field(default=None, nullable=True)
    description_vector: List[float] | None = Field(sa_column=Column(Vector(768)))
    descriptions_bank: Optional[str] = Field(default=None)
    source: str = Field(default=None, nullable=True)
    type: str = Field(default=None, nullable=True)
    wikidata_id: str = Field(default=None, nullable=True)
    score: Optional[float] = Field(default=None, nullable=True)
    update_at: datetime = Field(default=datetime.now(), nullable=True)
    aliases: List[dict] = Field(default=[], sa_column=Column(JSONB))
    instance_of: Optional[Dict] = Field(default={}, sa_column=Column(JSONB))

    ## Many to Many relationships between entities documents
    documents: list["Document"] = Relationship(
        back_populates="entities", link_model=Document_Entity_Link
    )
    subtopics: list["SubTopic"] = Relationship(
        back_populates="entities", link_model=SubTopic_Entity_Link
    )
    users: list["User"] = Relationship(
        back_populates="entities", link_model=Entity_User_Link
    )

    def to_node(self):
        return TreeNode(
            key=str(self.id),
            label=f"{self.name} ({len(self.documents)})",
            data=self.description,
            doc_count=len(self.documents),
            doc_ids=[str(doc.id) for doc in self.documents],
            children=[],
        )

    def to_public(self) -> "EntityPublic":
        return EntityPublic(
            id=str(self.id),
            name=self.name,
            description=self.description,
            source=self.source,
            type=self.type,
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
    Represents a document with its ID, title, URL, original text, authors, short summary, summary bullet points,
    raw answer, publication date, update timestamp, and status.
    """

    id: uuid_pkg.UUID = Field(default_factory=uuid_pkg.uuid4, primary_key=True)
    title: str = Field(default=None, nullable=True)
    url: str = Field(default=None, nullable=True)
    source_type: str = Field(default=None, nullable=True)
    original_text: str = Field(default=None, nullable=True)
    html_elements: List[Dict] = Field(default=[], sa_column=Column(JSON))
    authors: str = Field(default=None, nullable=True)
    metadata_keywords: str = Field(default=None, nullable=True)
    metadata_description: str = Field(default=None, nullable=True)
    locale: str = Field(default=None, nullable=True)
    image_url: str = Field(default=None, nullable=True)
    site_name: str = Field(default=None, nullable=True)
    ai_short_summary: str = Field(default=None, nullable=True)
    ai_is_about: str = Field(default=None, nullable=True)
    ai_bullet_points: List[str] = Field(default=[], sa_column=Column(JSON))
    ai_citations: List[Dict] = Field(default=[], sa_column=Column(JSON))
    raw_answer: str = Field(default=None, nullable=True)
    publication_date: datetime = Field(default=None, nullable=True)
    update_at: datetime = Field(default_factory=datetime.now, nullable=True)
    status: str = Field(default="Pending", nullable=True)
    llm_service_meta: Optional[Dict] = Field(default={}, sa_column=Column(JSONB))
    ai_summary_vector: List[float] = Field(sa_column=Column(Vector(768)))

    ## Many to Many relationships between documents and entities
    entities: list["Entity"] = Relationship(
        back_populates="documents", link_model=Document_Entity_Link
    )
    qans: list["Question_Answer"] = Relationship(back_populates="document")
    subtopics: list["SubTopic"] = Relationship(
        back_populates="documents", link_model=SubTopic_Document_Link
    )

    def to_public(self, cosine_similarity: float = None) -> "DocumentPublic":

        if type(self.html_elements) == str:
            html_elements = json.loads(self.html_elements)
        else:
            html_elements = self.html_elements

        return DocumentPublic(
            id=str(self.id),
            title=self.title,
            url=self.url,
            source_type="web" if self.source_type is None else self.source_type,
            authors=self.authors.split(",") if self.authors else None,
            tldr=self.ai_bullet_points,
            publicationDate=self.publication_date,
            llmServiceMeta=self.llm_service_meta,
            status=self.status,
            updateAt=self.update_at,
            oneSentenceSummary=self.ai_short_summary,
            summary_citations=[
                DocumentCitation(document_id=str(self.id), verbatims=self.ai_citations)
            ],
            is_about=self.ai_is_about,
            entities_and_concepts=[ent.to_public() for ent in self.entities],
            cosine_similarity=cosine_similarity,
            image_url=self.image_url,
            site_name=self.site_name,
            html_elements=remove_none_header_elements(html_elements),
        )

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


class User(SQLModel, table=True):
    """
    Represents a user with its ID, email, password, and role.
    """

    id: str = Field(primary_key=True)
    first_name: str = Field(nullable=True)
    last_name: str = Field(nullable=True)

    entities: list["Entity"] = Relationship(
        back_populates="users", link_model=Entity_User_Link
    )


class Source(SQLModel, table=True):
    """
    Represents a source with its ID, URL, update timestamp, document ID, and user ID.
    """

    id: uuid_pkg.UUID = Field(default_factory=uuid_pkg.uuid4, primary_key=True)
    url: str = Field(nullable=True)
    update_at: datetime = Field(default_factory=datetime.now, nullable=False)
    document_id: Optional[uuid_pkg.UUID] = Field(default=None, nullable=True)
    user_id: Optional[str] = Field(nullable=False)
    filepath: Optional[str] = Field(default=None, nullable=True)
    filename: Optional[str] = Field(default=None, nullable=True)
    cloned_documents: List[uuid_pkg.UUID] = Field(
        default=[], sa_column=Column(ARRAY(Integer))
    )


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
    subtopics: list["SubTopic"] = Relationship(
        back_populates="embeddings",
        link_model=SubTopic_Embedding_Link,
        sa_relationship_kwargs={"cascade": "delete"},
    )

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
    postgresql_ops={"vector": "vector_cosine_ops"},
)


""" 
The pydantic class is used to give JSON Schema to the AI. See how it's being used in togeher_api_client.py 
Why I used Pydantic instead of SQLModel? Good question, in my testing I was not able to get a complete JSON Schema from SQLModel.
"""


class DocumentPublic(BaseModel):
    id: Optional[str]
    title: Optional[str]
    source_type: Optional[str] = None
    url: Optional[str] = None
    authors: Optional[List[str]] = None
    publicationDate: Optional[datetime] = None
    llmServiceMeta: Optional[Dict] = None
    status: Optional[str] = None
    updateAt: Optional[datetime] = None
    oneSentenceSummary: Optional[str] = None
    summary_citations: Optional[List[DocumentCitation]] = None
    is_about: Optional[str] = None
    tldr: Optional[List[str]] = None
    entities_and_concepts: Optional[List[EntityPublic]] = None
    usage: Optional[str] = None
    cosine_similarity: Optional[float] = None
    image_url: Optional[str] = None
    site_name: Optional[str] = None
    html_elements: Optional[List[dict]] = None


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
    related_docs: Optional[List[DocumentPublic]] = Field(default=[])
    tasks: Optional[list[StudyTaskPublic]] = Field(default=[])
    created_at: Optional[datetime] = Field(default=None)


class Answer(BaseModel):
    question: str
    answer: str
    citations: Optional[List[str]] = None
    relevance_score: Optional[list[float]] = None


class SearchResults(BaseModel):
    documents_display: Optional[List[DocumentPublic]]
    rag_answer: Optional[RagAnswerPublic]
    failure: Optional[str] = None


class WikidataSearchResult(BaseModel):
    id: str
    label: str
    description: Optional[str] = "No description"
    aliases: List[str] = []
    sitelinks: List[str] = []
    instance_of: List[str] = []
