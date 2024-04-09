import re
from sqlmodel import SQLModel, Field, ARRAY, Float, JSON, Integer, Relationship
from sqlalchemy import Column
from sqlalchemy.dialects.postgresql import TEXT, JSONB
from pgvector.sqlalchemy import Vector
from typing import Optional, List, Dict
from datetime import datetime
from pydantic import BaseModel


"""
The SQLModel class is used to define the database schema (when table=True) or to define FastApi payload and response models (when table=False).    
"""

class SubTopic(SQLModel, table=True):
    """
    Represents a subtopic with its ID, name, description, and parent topic ID.
    """
    name: str = Field(nullable=False, primary_key=True)
    name_embedding: List[float] | None = Field(sa_column=Column(Vector(384)))
    description: str | None = Field(default=None, nullable=True)

class SubTopic_Entity_Link(SQLModel, table=True):
    """
    Represents a link between a subtopic and an entity.
    """
    subtopic_name: Optional[str] = Field(default=None, foreign_key="subtopic.name", primary_key=True)
    entity_id: Optional[int] = Field(default=None, foreign_key="entity.id", primary_key=True)


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


class Document_Embeddings(SQLModel, table=True):
    id: int = Field(default=None, primary_key=True)
    document_id: int = Field(nullable=False)
    field: str = Field(default=None, nullable=True)
    embeddings: List[float] = Field(sa_column=Column(Vector(384)))


class DocArtifact(SQLModel, table=False):
    """
    Represents a document artifact with its ID.
    """

    id: Optional[int] = Field(default=None, primary_key=True)


class Entity(SQLModel, table=True):
    """
    Represents an entity with its ID, document ID, name, description, source, type, Wikidata ID, and score.
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    document_id: Optional[int] = Field(default=None)
    name: str = Field(default=None)
    description: str = Field(default=None, nullable=True)
    source: str = Field(default=None, nullable=True)
    type: str = Field(default=None, nullable=True)
    wikidata_id: str = Field(default=None, nullable=True)
    score: Optional[float] = Field(default=None, nullable=True)


""" 
The pydantic class is used to give JSON Schema to the Together.AI API. See how it's being used in togeher_api_client.py 
Why I used Pydantic instead of SQLModel? Good question, in my testing I was not able to get a complete JSON Schema from SQLModel.
"""



class IdentifyEntity(BaseModel):
    name: Optional[str]
    type: Optional[str]
    description: Optional[str]


class DocumentPrompt(BaseModel):
    
    
    @classmethod
    def get_messages(cls, body: str) -> list[dict]:
        raise NotImplementedError("Subclass must implement this method")
    
    def populate_document(cls, document: Document) -> Document:
        raise NotImplementedError("Subclass must implement this method")
    
    def generate_entities(cls) -> list[Entity]:
        raise NotImplementedError("Subclass must implement this method")




class DocumentPromptTwo(DocumentPrompt):
     
    entities_and_topics: Optional[List[IdentifyEntity]]
    usage: Optional[str]

    def populate_document(cls, document: Document) -> Document:
        
        document.short_summary=cls.oneSentenceSummary
        document.llm_service_meta=cls.usage

        return document

    def generate_entities(self) -> list[Entity]:
        return [Entity(**entity.model_dump()) for entity in self.entities_and_topics]
        
    
    @classmethod
    def get_messages(cls, body: str):

        _system_content = """You are a researcher task with answering questions about an article.  
            Please ensure that your responses are socially unbiased and positive in nature.
            If a question does not make any sense, or is not factually coherent, explain why instead of answering something not correct. 
            If you don't know the answer, please don't share false information."""

        _user_content_1_examples = """Answers output must confirm to the this JSON format. Insure the JSON is valid. Shorten the answer to make sure the JSON is valid. [/INST] 
            JSON Output: {{
            "entities_and_topics" : [
            {{"name": "semiconductor", "type": "industry", "description": "Companies engaged in the design and fabrication of semiconductors and semiconductor devices"}},
            {{"name": "NBA", "type": "sport league", "description": "NBA is the national basketball league"}},
            {{"name": "Ford F150", "type": "vehicle", "description": "Article talks about the Ford F150 truck"}},
            {{"name": "mobile game soft launch", "type": "topic","description": "Mobile game soft launch is a process of releasing a game to a limited audience for testing."}},
            {{"name": "US Civil War", "type": "topic", "description": "The American Civil War was a civil war in the United States between the Union and the Confederacy, which had been formed by states that had seceded from the Union. The central cause of the war was the dispute over whether slavery would be permitted to expand into the western territories, leading to more slave states, or be prevented from doing so, which many believed would place slavery on a course of ultimate extinction."}},
            {{"name": "Capitalism", "type": "thoery", "description": Capitalism is an economic system based on the private ownership of the means of production and their operation for profit. Central characteristics of capitalism include capital accumulation, competitive markets, price system, private property, property rights recognition, voluntary exchange, and wage labor."}}
            ]}"""

        _user_content_2_task = """Use the examples above to identify no more then ten entities (companies, people, location, products....), 
            topic (marketing, politics, business strategy) and theories (free markets capatalism, gender dynamics...) 
            mentioned in the article. Include short description of each.

        Use the JSON format above to output your answer. Only output valid JSON format. Reduce the length of the answer to make sure the JSON is valid."""

        _user_content_3_article = """Article: {BODY}""".format(BODY=body)

        return [
            {"role": "system", "content": _system_content},
            {"role": "user", "content": _user_content_1_examples},
            {"role": "user", "content": _user_content_2_task},
            {"role": "user", "content": _user_content_3_article}
        ]



class DocumentPromptOne(DocumentPrompt):
    whatThisArticleIsAbout: Optional[str]
    oneSentenceSummary: Optional[str] 
    summaryInNumericBulletPoints: Optional[List[str]]
    usage: Optional[str]

    def populate_document(self, document: Document) -> Document:
            
            document.is_about=self.whatThisArticleIsAbout
            document.short_summary=self.oneSentenceSummary
            bullet_points = [re.sub(r"[1-9]{,2}\.", "", bullet_point).strip() for bullet_point in self.summaryInNumericBulletPoints]
            document.summary_bullet_points=bullet_points
            document.llm_service_meta=self.usage
    
            return document


    @classmethod
    def get_messages(cls, body: str):

        _system_content = """You are a researcher task with answering questions about an article.  
            Please ensure that your responses are socially unbiased and positive in nature.
            If a question does not make any sense, or is not factually coherent, explain why instead of answering something not correct. 
            If you don't know the answer, please don't share false information."""

        _user_content_1_examples = """Answers output must confirm to the this JSON format. Insure the JSON is valid. Shorten the answer to make sure the JSON is valid. [/INST] 
            JSON Output: {{
                "whatThisArticleIsAbout" : "Mobile game soft launch",
                "oneSentenceSummary" : "Mobile game soft launch is a process of releasing a game to a limited audience for testing.",
                "summaryInNumericBulletPoints" : [
                "1. Mobile game soft launch is a process of releasing a game to a limited audience for testing.",
                "2. Getting soft launch require planning, strategy and expirements.",
                ],
            }}"""

        _user_content_2_task = """Use the examples above to answer the following questions.
        1. Three to fours words explaining what the article is about.
        2. Summarize the article in one sentence. Limit the answer to twenty words.
        3. Summarize the article up to six bullet-points. Each bullet-point need to have betweeen ten to tweenty words. Limit the number of bullet points must below six.
        
        Use the JSON format above to output your answer. Only output valid JSON format. Reduce the length of the answer to make sure the JSON is valid."""

        _user_content_3_article = """Article: {BODY}""".format(BODY=body)

        return [
            {"role": "system", "content": _system_content},
            {"role": "user", "content": _user_content_1_examples},
            {"role": "user", "content": _user_content_2_task},
            {"role": "user", "content": _user_content_3_article}
        ]
 

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
    entities_and_concepts: Optional[List[Entity]] = None
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
            entities_and_concepts=entities,
            cosine_similarity=cosine_similarity,
        )
