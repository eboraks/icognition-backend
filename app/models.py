import json, logging, sys
from types import SimpleNamespace
from sqlmodel import SQLModel, Field, Float, JSON, Integer, Relationship, String
from sqlalchemy import Column
from sqlalchemy.dialects.postgresql import TEXT, JSONB, ARRAY
from pgvector.sqlalchemy import Vector
from typing import Optional, List, Dict
from datetime import datetime
from pydantic import BaseModel, model_serializer

from app.icog_util import original_text_to_sentences, sentences_to_text
from app.gemini_client import GeminiClient


logging.basicConfig(
    stream=sys.stdout,
    format="%(asctime)s - %(message)s",
    level=logging.INFO,
    datefmt="%Y-%m-%d %H:%M:%S",
)

class TreeNode(BaseModel):
    "Tree Node Model based on primevue Tree data filter"
    key: int
    label: str
    data: Optional[str] = None
    doc_count: Optional[int] = None
    doc_ids: Optional[list[int]] = None
    children: Optional[list["TreeNode"]] = None


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


class SubTopic_Embedding_Link(SQLModel, table=True):
    """
    Represents a link between a subtopic and an embedding.
    """
    subtopic_id: Optional[int] = Field(default=None, foreign_key="subtopic.id", primary_key=True)
    embedding_id: Optional[int] = Field(default=None, foreign_key="embedding.id", primary_key=True)
    notes: Optional[str] = Field(default=None)

class SubTopic_Document_Link(SQLModel, table=True):
    """
    Represents a link between a subtopic and an document.
    """
    subtopic_id: Optional[int] = Field(default=None, foreign_key="subtopic.id", primary_key=True)
    document_id: Optional[int] = Field(default=None, foreign_key="document.id", primary_key=True)

class SubTopic_Entity_Link(SQLModel, table=True):
    """
    Represents a link between a subtopic and an document.
    """
    subtopic_id: Optional[int] = Field(default=None, foreign_key="subtopic.id", primary_key=True)
    entity_id: Optional[int] = Field(default=None, foreign_key="entity.id", primary_key=True)


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
    name_update_at: datetime = Field(default = datetime.now(), nullable=True)
    vector: List[float] | None = Field(sa_column=Column(Vector(384)))
    description: str | None = Field(default=None, nullable=True)
    key_words: str | None = Field(default=None)
    topic_id: int | None= Field(default=None, foreign_key="topic.id")
    topic: Topic = Relationship(back_populates="subtopics")
    update_at: datetime = Field(default_factory = datetime.now, nullable=True)
    embeddings: list["Embedding"] = Relationship(back_populates="subtopics", link_model=SubTopic_Embedding_Link, sa_relationship_kwargs={"cascade": "delete"})
    documents: list["Document"] = Relationship(back_populates="subtopics", link_model=SubTopic_Document_Link, sa_relationship_kwargs={"cascade": "delete"})
    entities: list["Entity"] = Relationship(back_populates="subtopics", link_model=SubTopic_Entity_Link, sa_relationship_kwargs={"cascade": "delete"})

    def entities_agg_string(self):
        # Create string with each entity nanme, type and description
        results = ''
        for emb in self.embeddings:
            results += f'{emb.text}\n'
        return results
    
    def to_node(self):

        _docs_ids = [doc.id for doc in self.documents]
        for entity in self.entities:
            _docs_ids.extend([doc.id for doc in entity.documents])

        _docs_ids = list(set(_docs_ids))  
        return TreeNode(
            key = self.id,
            doc_count = len(_docs_ids),
            label = f"{self.name.title()} ({len(_docs_ids)})",
            data = self.description,
            doc_ids = _docs_ids,
            children = []
        )
    
    def to_display(self) -> "SubTopicDisplay":

        ## Get all the documents ids from the subtopic and its entities
        _docs_ids = [doc.id for doc in self.documents]
        for entity in self.entities:
            _docs_ids.extend([doc.id for doc in entity.documents])

        _docs_ids = list(set(_docs_ids))    
        return SubTopicDisplay(
            id = self.id,
            name = self.name,
            description = self.description,
            number_of_docs = len(_docs_ids),
            docs_ids = _docs_ids,
            ents_ids = [ent.id for ent in self.entities],
            key_words = self.key_words)


class Document_Entity_Link(SQLModel, table=True):
    """
    Represents a link between a document and an entity.
    """

    document_id: Optional[int] = Field(default=None, foreign_key="document.id", primary_key=True)
    entity_id: Optional[int] = Field(default=None, foreign_key="entity.id", primary_key=True)



class Entity(SQLModel, table=True):
    """
    Represents an entity with its ID, document ID, name, description, source, type, Wikidata ID, and score.
    """
    id: Optional[int] = Field(default=None, primary_key=True)
    version: int = Field(default=1, nullable=True)
    name: str = Field(default=None, nullable=True)
    name_vector: List[float] | None = Field(sa_column=Column(Vector(384)))
    description: str = Field(default=None, nullable=True)
    descriptions_bank: Optional[str] = Field(default=None)
    source: str = Field(default=None, nullable=True)
    type: str = Field(default=None, nullable=True)
    wikidata_id: str = Field(default=None, nullable=True)
    score: Optional[float] = Field(default=None, nullable=True)
    update_at: datetime = Field(default=datetime.now(), nullable=True)
    synonyms: List[dict]  = Field(default=[], sa_column=Column(JSON))

    ## Many to Many relationships between entities documents
    documents: list["Document"] = Relationship(back_populates="entities", link_model=Document_Entity_Link)
    subtopics: list["SubTopic"] = Relationship(back_populates="entities", link_model=SubTopic_Entity_Link)

    def to_node(self):
        return TreeNode(
            key = self.id,
            label = f"{self.name.title()} ({len(self.documents)})",
            data =  self.description,
            doc_count=len(self.documents),
            doc_ids = [doc.id for doc in self.documents],
            children = [])
    

    def to_display(self) -> "EntityDisplay":
        return EntityDisplay(
            id=self.id,
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

    id: int = Field(default=None, primary_key=True)
    title: str = Field(default=None, nullable=True)
    url: str = Field(default=None, nullable=True)
    original_text: str = Field(default=None, nullable=True)
    html_elements: List[Dict] = Field(default=[], sa_column=Column(JSON))
    authors: str = Field(default=None, nullable=True)
    metadata_keywords: str = Field(default=None, nullable=True)
    metadata_description: str = Field(default=None, nullable=True)
    locale: str = Field(default=None, nullable=True)
    image_url: str = Field(default=None, nullable=True)
    site_name: str = Field(default=None, nullable=True)
    short_summary: str = Field(default=None, nullable=True)
    is_about: str = Field(default=None, nullable=True)
    learning_from_document: str = Field(default=None, nullable=True)
    summary_bullet_points: List[str] = Field(default=[], sa_column=Column(JSON))
    summary_citations: List[Dict] = Field(default=[], sa_column=Column(JSON))
    raw_answer: str = Field(default=None, nullable=True)
    publication_date: datetime = Field(default=None, nullable=True)
    update_at: datetime = Field(default_factory=datetime.now, nullable=True)
    status: str = Field(default="Pending", nullable=True)
    llm_service_meta: Optional[Dict] = Field(default={}, sa_column=Column(JSONB))
    summary_vector: List[float] = Field(sa_column=Column(Vector(768)))

    ## Many to Many relationships between documents and entities
    entities: list["Entity"] = Relationship(back_populates="documents", link_model=Document_Entity_Link)
    qans: list["Question_Answer"] = Relationship(back_populates="document")
    subtopics: list["SubTopic"] = Relationship(back_populates="documents", link_model=SubTopic_Document_Link)

    def to_display(self, cosine_similarity: float = None) -> "DocumentDisplay": 

        if type(self.html_elements) == str:
            html_elements = json.loads(self.html_elements)
        else:
            html_elements=self.html_elements

        return DocumentDisplay(
            id = self.id,
            title = self.title,
            url = self.url,
            authors = self.authors.split(",") if self.authors else None,
            tldr = self.summary_bullet_points,
            publicationDate = self.publication_date,
            llmServiceMeta = self.llm_service_meta,
            status = self.status,
            updateAt = self.update_at,
            oneSentenceSummary = self.short_summary,
            is_about = self.is_about,
            entities_and_concepts= [ent.to_display() for ent in self.entities] ,
            cosine_similarity=cosine_similarity,
            image_url=self.image_url,
            site_name=self.site_name,
            html_elements= html_elements
        )



    def to_embeddings(self) -> list["Embedding"]:
        """
        Converts the model instance to a list of Embeddings objects.

        Returns:
            A list of Embeddings objects representing the model instance.
        """
        results = []

        if self.title:
            results.append(
                Embedding(
                    source_type="document",
                    source_id=self.id,
                    field="title",
                    text=self.title,
                )
            )

        if self.is_about:
            results.append(
                Embedding(
                    source_type="document",
                    source_id=self.id,
                    field="is_about",
                    text=self.is_about,
                )
            ) 

        if self.metadata_keywords:
            results.append(
                Embedding(
                    source_type="document",
                    source_id=self.id,
                    field="metadata_keywords",
                    text=self.metadata_keywords,
                )
            )
        
        if self.metadata_description:
            results.append(
                Embedding(
                    source_type="document",
                    source_id=self.id,
                    field="metadata_description",
                    text=self.metadata_description,
                )
            )

        if self.summary_bullet_points:
            for bullet_point in self.summary_bullet_points:
                results.append(
                    Embedding(
                        source_type="document",
                        source_id=self.id,
                        field="summary_bullet_points",
                        text=bullet_point,
                    )
                )

        return results
    
    async def generate_vector(self, geminiClient: GeminiClient):

        try:
            if self.is_about and self.summary_bullet_points:
                text = f"{self.is_about} \n"
                for bullet_point in self.summary_bullet_points:
                    text += f"{bullet_point} \n"
                self.summary_vector = await geminiClient.generate_embedding(content= text, title= self.title)
                return self.summary_vector

            else:
                return None
        except Exception as e:
            # Handle the exception here
            logging.error(f"An error occurred while generating summary vector for document_id: {self.id}. Error: {e}")
            return None

    def get_sentences_can_be_delete(self): 
        sentences = []
        for element in json.loads(self.html_elements, object_hook=lambda d: SimpleNamespace(**d)):

            if (element.element == 'p'):
                temp = original_text_to_sentences(element.text)
                sentences.extend(temp)
            else:
                sentences.append(element.text)

        return sentences

    def get_text_with_sentences_index_can_be_delete(self, sentences: list[str] = None):

        if sentences is None:
            sentences = self.get_sentences()

        return sentences_to_text(sentences)



class Question_Answer_Display(BaseModel):
    question: str
    answer: str
    citations: list[dict]


class Question_Answer(SQLModel, table=True):
    """
    Represents a question answer with its ID, question, answer, and document ID.
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    question: str = Field(default=None, nullable=True)
    answer: str = Field(default=None, nullable=True)
    citations: List[dict] = Field(default=[], sa_column=Column(JSON))
    question_vector: List[float] = Field(sa_column=Column(Vector(384)))

    document_id: Optional[int] = Field(default=None, foreign_key="document.id")
    document: Document = Relationship(back_populates="qans")


    def to_display(self) -> Question_Answer_Display:
        return Question_Answer_Display(
            question=self.question,
            answer=self.answer,
            citations=self.citations,
            relevance_score=None
        )

class Study_Task(SQLModel, table=True):
    """
    Represents a study task with its ID, name, description, and user ID.
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    description: str = Field(default=None)
    explanation: str = Field(default=None, nullable=True)
    status: str = Field(default="Pending", nullable=True)
    description_vector: List[float] = Field(sa_column=Column(Vector(768)))
    project_id: Optional[int] = Field(default=None, foreign_key="study_project.id")
    study_project: "Study_Project" = Relationship(back_populates="tasks")
    citations: list["Study_Task_Citation"] = Relationship(back_populates="task")

    async def generate_vector(self, geminiClient: GeminiClient):
        self.description_vector = await geminiClient.generate_embedding(content= self.description)


    
class Study_Project(SQLModel, table=True):
    """
    Represents a study project with its ID, name, description, and user ID.
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(nullable=False)
    objective: str = Field(default=None, nullable=True)
    explanation: str = Field(default=None, nullable=True)
    user_id: str = Field(nullable=False)
    objective_tasks_vector: List[float] = Field(sa_column=Column(Vector(768)))
    # documents: list["Document"] = Relationship(back_populates="study_project", link_model="Study_Project_Document_Link", sa_relationship_kwargs={"cascade": "delete"})
    tasks: list["Study_Task"] = Relationship(back_populates="study_project")
    

    async def generate_vector(self, geminiClient: GeminiClient):
        text = f"{self.objective} \n"
        for task in self.tasks:
            text += f"{task.description} \n"
        
        self.objective_tasks_vector = await geminiClient.generate_embedding(content= text, title= self.name)
        

class Study_Task_Citation(SQLModel, table=True):
    """
    Represents a study task citation with its ID, task ID, and citation.
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    citations: Optional[List[Dict]] = Field(default=[], sa_column=Column(JSON))
    ## Intentially I didn't created relationship with Document because that will require a many to many relationship table
    ## and code to manage creation, update and deletion of the relationship.
    document_id: Optional[int] = Field(default=None, nullable=True)
    task_id: Optional[int] = Field(default=None, foreign_key="study_task.id")
    task: Study_Task = Relationship(back_populates="citations")    



### 
###  The following classes are used to define the FastAPI payload and response models
###

class PagePayload(SQLModel, table=False):
    """
    Represents the payload for a page, including its URL and HTML content.
    """

    url: Optional[str] = Field(default=None)
    html: Optional[str] = Field(default=None)
    user_id: str = Field(default=None, nullable=True)

class QuestionPlayload(SQLModel, table=False):
    """
    Represents the payload for a question, including the question and user ID.
    """

    question: Optional[str] = Field(default=None)
    document_id: Optional[int] = Field(default=None)


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



class Bookmark(SQLModel, table=True):
    """
    Represents a bookmark with its ID, URL, update timestamp, document ID, and user ID.
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    url: str = Field(nullable=False)
    update_at: datetime = Field(default_factory=datetime.now, nullable=False)
    document_id: Optional[int] = Field(default=None, nullable=True)
    user_id: Optional[str] = Field(nullable=False)
    cloned_documents: List[int] = Field(default=[], sa_column=Column(ARRAY(Integer)))




class Embedding(SQLModel, table=True):
    id: int = Field(default=None, primary_key=True)
    version: int = Field(default=1, nullable=True)
    user_id: str = Field(default=None, nullable=True)
    field: str = Field(default=None, nullable=True)
    text: str = Field(default=None, nullable=True)
    source_type: str = Field(default=None, nullable=False)
    source_id: int = Field(default=None, nullable=False)
    vector: List[float] = Field(sa_column=Column(Vector(384)))
    update_at: datetime = Field(default_factory=datetime.now, nullable=True)
    subtopics: list["SubTopic"] = Relationship(back_populates="embeddings", link_model=SubTopic_Embedding_Link, sa_relationship_kwargs={"cascade": "delete"})

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



class DocArtifact(SQLModel, table=False):
    """
    Represents a document artifact with its ID.
    """

    id: Optional[int] = Field(default=None, primary_key=True)



""" 
The pydantic class is used to give JSON Schema to the Together.AI API. See how it's being used in togeher_api_client.py 
Why I used Pydantic instead of SQLModel? Good question, in my testing I was not able to get a complete JSON Schema from SQLModel.
"""



class EntityDisplay(BaseModel):
    id: Optional[int]
    name: Optional[str]
    description: Optional[str] | None
    source: Optional[str] | None
    type: Optional[str] | None
    
 

class DocumentDisplay(BaseModel):
    id: Optional[int]
    title: Optional[str]
    url: Optional[str] = None
    authors: Optional[List[str]] = None
    publicationDate: Optional[datetime] = None
    llmServiceMeta: Optional[Dict] = None
    status: Optional[str] = None
    updateAt: Optional[datetime] = None
    oneSentenceSummary: Optional[str] = None
    is_about: Optional[str] = None
    tldr: Optional[List[str]] = None
    entities_and_concepts: Optional[List[EntityDisplay]] = None
    tags: Optional[List[str]] = None
    usage: Optional[str] = None
    cosine_similarity: Optional[float] = None
    image_url: Optional[str] = None
    site_name: Optional[str] = None
    html_elements: Optional[List[dict]] = None


class RagAnswerDisplay(BaseModel):
    answer: Optional[str]
    documents_used: Optional[List[int]]
    llm_service_meta: Optional[Dict]


class Answer(BaseModel):
    question: str
    answer: str
    citations: Optional[List[str]] = None
    relevance_score: Optional[list[float]] = None


class SearchResults(BaseModel):
    documents_display: Optional[List[DocumentDisplay]]
    rag_answer: Optional[RagAnswerDisplay]
    failure: Optional[str] = None



class TestList(SQLModel, table=True):
    id: int = Field(default=None, primary_key=True)
    texts: Optional[List[str]] = Field(default=None, sa_column=Column(ARRAY(String)))
    texts2: List[str] = Field(default=[], sa_column=Column(ARRAY(String)))
    json1: Optional[List[str]] = Field(default=[], sa_column=Column(JSON))

    # Needed for Column(JSON)
    class Config:
        arbitrary_types_allowed = True
