import re
from sqlmodel import SQLModel, Field, ARRAY, Float, JSON, Integer, Relationship, String
from sqlalchemy import Column
from sqlalchemy.dialects.postgresql import TEXT, JSONB
from pgvector.sqlalchemy import Vector
from typing import Optional, List, Dict
from datetime import datetime
from pydantic import BaseModel

"""
The SQLModel class is used to define the database schema (when table=True) or to define FastApi payload and response models (when table=False).    
"""
class Topic(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    user_id: str | None = Field(default=None)
    name: str = Field(nullable=False)
    description: str | None = Field(default=None)
    embedding: list[float] | None = Field(sa_column=Column(Vector(384)))
    subtopics: list["SubTopic"] = Relationship(back_populates="topic")


class SubTopic_Entity_Link(SQLModel, table=True):
    """
    Represents a link between a subtopic and an entity.
    """
    subtopic_id: Optional[int] = Field(default=None, foreign_key="subtopic.id", primary_key=True)
    entity_id: Optional[int] = Field(default=None, foreign_key="entity.id", primary_key=True)

class SubTopic(SQLModel, table=True):
    """
    Represents a subtopic with its ID, name, description, and parent topic ID.
    """
    id: int = Field(default=None, primary_key=True)
    user_id: str | None = Field(nullable=False)
    name: str = Field(nullable=False)
    embedding: List[float] | None = Field(sa_column=Column(Vector(384)))
    description: str | None = Field(default=None, nullable=True)
    key_words: str | None = Field(default=None)
    topic_id: int | None= Field(default=None, foreign_key="topic.id")
    topic: Topic = Relationship(back_populates="subtopics")
    entities: list["Entity"] = Relationship(back_populates="ent_subtopics", link_model=SubTopic_Entity_Link, sa_relationship_kwargs={"cascade": "delete"})

    def entities_agg_string(self):
        # Create string with each entity nanme, type and description
        results = ''
        for entity in self.entities:
            results += f'{entity.name} ({entity.type}): {entity.description}\n'
        return results
    
    def to_node(self):
        return TreeNode(
            key = self.id,
            label = self.name,
            data = self.description,
            children = [entity.to_node() for entity in self.entities]
        )



class Entity(SQLModel, table=True):
    """
    Represents an entity with its ID, document ID, name, description, source, type, Wikidata ID, and score.
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    document_id: Optional[int] = Field(default=None, foreign_key="document.id")
    document: Optional["Document"] = Relationship(back_populates="doc_entities")
    name: str = Field(default=None)
    description: str = Field(default=None, nullable=True)
    source: str = Field(default=None, nullable=True)
    type: str = Field(default=None, nullable=True)
    wikidata_id: str = Field(default=None, nullable=True)
    score: Optional[float] = Field(default=None, nullable=True)
    embedding: Optional[List[float]] = Field(sa_column=Column(Vector(384)))
    ent_subtopics: list[SubTopic] = Relationship(back_populates="entities", link_model=SubTopic_Entity_Link)

    def to_node(self):
        return TreeNode(
            key = self.id,
            label = self.name,
            data =  self.description,
            children = [])


class TreeNode(BaseModel):
    "Tree Node Model based on primevue Tree data filter"
    key: int
    label: str
    data: str
    children: list["TreeNode"] | None = None


class PagePayload(SQLModel, table=False):
    """
    Represents the payload for a page, including its URL and HTML content.
    """

    url: Optional[str] = Field(default=None)
    html: Optional[str] = Field(default=None)
    user_id: str = Field(default=None, nullable=True)


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


class Page(SQLModel, table=False):
    """
    Represents a web page with its clean URL, title, author, paragraphs, and full text.
    """

    clean_url: Optional[str] = Field(default=None)
    title: Optional[str] = Field(default=None)
    author: Optional[str] = Field(default=None)
    paragraphs: Optional[List[str]] = Field(default=None)
    full_text: Optional[str] = Field(default=None)


class Bookmark(SQLModel, table=True):
    """
    Represents a bookmark with its ID, URL, update timestamp, document ID, and user ID.
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    url: str = Field(nullable=False)
    update_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)
    document_id: Optional[int] = Field(default=None, nullable=True)
    user_id: Optional[str] = Field(nullable=False)
    cloned_documents: List[int] = Field(default=[], sa_column=Column(ARRAY(Integer)))


class Document(SQLModel, table=True):
    """
    Represents a document with its ID, title, URL, original text, authors, short summary, summary bullet points,
    raw answer, publication date, update timestamp, and status.
    """

    id: int = Field(default=None, primary_key=True)
    title: str = Field(default=None, nullable=True)
    url: str = Field(default=None, nullable=True)
    original_text: str = Field(default=None, nullable=True)
    authors: List[float] = Field(sa_column=Column(ARRAY(Float)), default=[])
    short_summary: str = Field(default=None, nullable=True)
    is_about: str = Field(default=None, nullable=True)
    summary_bullet_points: List[str] = Field(default=[], sa_column=Column(JSON))
    raw_answer: str = Field(default=None, nullable=True)
    publication_date: datetime = Field(default=None, nullable=True)
    update_at: datetime = Field(default_factory=datetime.utcnow, nullable=True)
    status: str = Field(default="Pending", nullable=True)
    llm_service_meta: Optional[Dict] = Field(default={}, sa_column=Column(JSONB))
    doc_entities: list[Entity] = Relationship(back_populates="document")


class Document_Embeddings(SQLModel, table=True):
    id: int = Field(default=None, primary_key=True)
    document_id: int = Field(nullable=False)
    field: str = Field(default=None, nullable=True)
    entity_id: int = Field(default=None, nullable=True)
    embeddings: List[float] = Field(sa_column=Column(Vector(384)))


class DocArtifact(SQLModel, table=False):
    """
    Represents a document artifact with its ID.
    """

    id: Optional[int] = Field(default=None, primary_key=True)




""" 
The pydantic class is used to give JSON Schema to the Together.AI API. See how it's being used in togeher_api_client.py 
Why I used Pydantic instead of SQLModel? Good question, in my testing I was not able to get a complete JSON Schema from SQLModel.
"""



class IdentifyEntity(BaseModel):
    name: Optional[str]
    type: Optional[str]
    description: Optional[str]


class EntityDisplay(BaseModel):
    id: Optional[int]
    document_id: Optional[int]
    name: Optional[str]
    description: Optional[str]
    source: Optional[str]
    type: Optional[str]
    wikidata_id: Optional[str]
    score: Optional[float]

    @classmethod
    def from_orm(cls, entity: Entity):
        return cls(
            id=entity.id,
            document_id=entity.document_id,
            name=entity.name,
            description=entity.description,
            source=entity.source,
            type=entity.type,
            wikidata_id=entity.wikidata_id,
            score=entity.score,
        )

class DocumentDisplay(BaseModel):
    id: Optional[int]
    title: Optional[str]
    url: Optional[str] = None
    authors: Optional[List[str]] = None
    publicationDate: Optional[str] = None
    llmServiceMeta: Optional[Dict] = None
    status: Optional[str] = None
    updateAt: Optional[datetime] = None
    oneSentenceSummary: Optional[str] = None
    is_about: Optional[str] = None
    tldr: Optional[List[str]] = None
    entities_and_concepts: Optional[List[EntityDisplay]] = None
    usage: Optional[str] = None
    cosine_similarity: Optional[float] = None

    @classmethod
    def from_orm(cls, document: Document, entities: List[Entity] = None, cosine_similarity: float = None):
        return cls(
            id=document.id,
            title=document.title,
            url=document.url,
            authors=document.authors,
            tldr=document.summary_bullet_points,
            publicationDate=document.publication_date,
            llmServiceMeta=document.llm_service_meta,
            status=document.status,
            updateAt=document.update_at,
            oneSentenceSummary=document.short_summary,
            is_about=document.is_about,
            entities_and_concepts= [EntityDisplay.from_orm(entity) for entity in entities] if entities else None,
            cosine_similarity=cosine_similarity,
        )

class RagAnswerDisplay(BaseModel):
    answer: Optional[str]
    documents_used: Optional[List[int]]
    llm_service_meta: Optional[Dict]


class SearchResults(BaseModel):
    documents_display: Optional[List[DocumentDisplay]]
    rag_answer: Optional[RagAnswerDisplay]
    failure: Optional[str] = None



class SubTopicDisplay(BaseModel):
    id: Optional[int]
    name: Optional[str]
    description: Optional[str]
    number_of_docs: Optional[int]
    docs_ids: Optional[List[int]]

    @classmethod
    def from_touple(cls, subtopic_touple):
        return cls(
            id=subtopic_touple[0],
            name=subtopic_touple[1],
            description=subtopic_touple[2],
            number_of_docs=subtopic_touple[3],
            docs_ids=subtopic_touple[4]
        )