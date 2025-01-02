import datetime
import os, pickle
import re
import app.getters as getter
from app import html_parser
from app.db_connector import get_engine
from app.source_doc_handler import SourceDocHandler
from app.models import (
    DocumentCitation,
    Entity_User_Link,
    Question_Answer,
    Source,
    Entity,
    Page,
    Document,
    PagePayload,
    Embedding,
    Document_Entity_Link,
)
from app.gemini_client import GeminiClient
from sqlalchemy import (
    select,
    and_,
    exc,
    text,
)
from sqlalchemy.orm import Session

from app.gemini_prompts_models import EntitiesPrompt, SummarizePrompt, TopicPrompt

from app.log import get_logger
import app.entity_handler as entity_handler

logging = get_logger(__name__)


env_vers = os.environ

engine = get_engine()
genimi_client = GeminiClient()

doc_counter_for_subtopics = 0


def test_db_connection():

    try:
        conn = engine.connect()
        conn.close()
        return True
    except exc.OperationalError as e:
        logging.error(f"Error connectiong to DB {e}")
        return None


def create_page(payload: PagePayload) -> Page:
    page = html_parser.create_page(payload)
    if page == None:
        logging.info(f"Page not found for url {payload.url}")
        return None

    return page


def clone_document(doc: Document):

    old_doc = getter.get_document_public_by_id(doc.id)

    ## Clone document. This is used when regenerasting a document, we keep the old document and it's related objects
    new_doc = Document()
    new_doc.title = old_doc.title
    new_doc.url = old_doc.url
    new_doc.original_text = old_doc.original_text

    with Session(engine) as session:
        session.add(new_doc)
        session.commit()
        session.refresh(new_doc)

        # Update the old document to show it was cloned
        old_doc.status = "Cloned"
        return new_doc


def update_document(doc: Document, related_objects: list[list] = None):
    with Session(engine) as session:
        session.add(doc)

        session.add_all(doc.entities)

        if related_objects:
            logging.info(f"Adding related objects to document {doc.id}")
            for related_object in related_objects:
                session.add_all(related_object)
        session.commit()
        session.refresh(doc)
        return doc


def reassociate_bookmark_with_document(old_document_id, new_document_id):
    """
    This function reassociate a bookmark with a new document
    """
    with Session(engine) as session:
        bookmark = session.scalar(
            select(Source).where(Source.document_id == old_document_id)
        )
        if bookmark is None:
            logging.error(f"Bookmark with document {old_document_id} not found")
            return None

        bookmark.document_id = new_document_id
        bookmark.cloned_documents.append(old_document_id)

        session.commit()
        session.refresh(bookmark)
        logging.info(
            f"Bookmark {bookmark.id} reassociated with document {new_document_id}"
        )
        return bookmark


async def generate_summary(doc: Document, testing: bool = False) -> Document:
    """
    Function that takes pages and return a document with the generated summary,
    bullet points and entities generate by LLM
    """

    doc.status = "Processing"
    update_document(doc)

    try:
        logging.info(f"Generating summary for document {doc.id}")

        ## For testing, if file exists, load it and return payload
        filename = f"response_one_{doc.id}.json"
        if os.path.exists(filename):
            with open(filename, "rb") as f:
                response = pickle.load(f)
                logging.info(f"Response loaded from file for document {doc.id}")
        else:

            response = await genimi_client.generate_response(
                SummarizePrompt.build_prompt(doc.original_text), SummarizePrompt
            )
            ## Save response in json file
            if testing:
                with open(filename, "wb") as f:
                    pickle.dump(response, f)

        logging.info(f"Response from LLM {response}")

    except Exception as e:
        logging.error(f"Error generating with LLM {e}")
        doc.status = "Failure"
        update_document(doc)
        return None

    try:
        ## raw_answer is the response from LLM with the support sentences.
        doc = response.populate_document(doc)
        doc.ai_summary_vector = await doc.generate_vector(geminiClient=genimi_client)
        doc.status = "Done"
        doc.update_at = datetime.datetime.now()
        update_document(doc)
        logging.info(f"Document {doc.id} was updated with summary and bullet points")
        return doc

    except Exception as e:
        doc.status = "Failure"
        logging.error(f"Error generating with LLM {e}")
        update_document(doc)
        return None


def create_source_bookmark(page: Page, user_id: str) -> Source:
    source_doc_handler = SourceDocHandler()
    session = Session(engine)

    # Check if document exists, retrieve the bookmark and return
    # if exists. Else, create the document, bookmark.

    bookmark = session.scalar(
        select(Source).where(
            and_(Source.url == page.clean_url, Source.user_id == user_id)
        )
    )

    if bookmark:
        logging.info(f"Bookmark from url {page.clean_url} already exists")
        session.close()
        return bookmark

    doc = source_doc_handler.create_document_from_page(page)

    bookmark = Source()
    bookmark.url = page.clean_url
    bookmark.update_at = datetime.datetime.now()
    bookmark.document_id = doc.id
    bookmark.user_id = user_id

    session.add(bookmark)
    session.commit()
    session.refresh(bookmark)
    logging.info(f"Bookmark was created with id {bookmark.id}")

    session.close()

    return bookmark


async def generate_embeddings(user_id: str):
    """
    This function generates embeddings for a list of documents
    The reason this is not being done in the extract_info_from_doc function is because we don't want
    to delay returning the response to the user
    """

    ## Generate embeddings for documents that don't have embeddings
    with Session(engine) as session:

        ## Find Documents taht don't have embeddings
        docs_embedding = (
            select(Embedding.source_id)
            .filter(
                and_(Embedding.source_type == "document", Embedding.user_id == user_id)
            )
            .group_by(Embedding.source_id)
        )

        docs = (
            session.scalars(
                select(Document)
                .join(Source, Source.document_id == Document.id)
                .where(
                    and_(
                        Document.id.not_in(docs_embedding),
                        Document.ai_is_about != None,
                        Document.status == "Done",
                        Source.user_id == user_id,
                    )
                )
            )
            .unique()
            .all()
        )

        ## Find entities that don't have embeddings
        entity_embedding = (
            select(Embedding.source_id)
            .filter(
                and_(Embedding.source_type == "entity", Embedding.user_id == user_id)
            )
            .group_by(Embedding.source_id)
        )

        entities = (
            session.scalars(
                select(Entity)
                .join(Document_Entity_Link, Document_Entity_Link.entity_id == Entity.id)
                .join(Source, Source.document_id == Document_Entity_Link.document_id)
                .where(
                    and_(Entity.id.not_in(entity_embedding), Source.user_id == user_id)
                )
            )
            .unique()
            .all()
        )

    try:
        await generate_embeddings_for_docs(documents=docs, user_id=user_id)
    except Exception as e:
        logging.error(f"Error generating embeddings for documents {e}")

    try:
        await entity_handler.generate_embeddings_for_entities(
            entities=entities, user_id=user_id
        )
    except Exception as e:
        logging.error(f"Error generating embeddings for entities {e}")

    ## Update search_vector for embeddings that don't have it
    with Session(engine) as session:
        text = """UPDATE public.embedding
                SET search_vector = to_tsvector('english', text)
                WHERE search_vector IS NULL;"""
        session.execute(text)

    ## Generate embeddings for entities that don't have embeddings
    ## May, 22. Remove Embedding.version < Entity.version) from where clause, becuase embedding have old versions (versions add additive)
    ## results in always generating embeddings for entities with version above 1. That mean that updated entities will not generate new embeddings
    ## for now. In the future this can be improved, but for now it's ok.


async def generate_embeddings_for_docs(documents: list[Document], user_id: str):

    logging.info(f"Generating embeddings for {len(documents)} documents")
    embeddings = []
    for doc in documents:
        for emb in doc.to_embeddings():
            if emb.text:
                emb.vector = await genimi_client.generate_embedding(emb.text)
                emb.user_id = user_id
                embeddings.append(emb)

    with Session(engine) as session:
        session.add_all(embeddings)
        session.commit()


async def update_entity_embedding(entity: Entity):
    with Session(engine) as session:
        embedding = session.scalar(
            select(Embedding).where(Embedding.source_id == entity.id)
        )
        embedding.vector = await genimi_client.generate_embedding(entity.name)
        session.add(embedding)
        session.commit()
        logging.info(f"Embedding for entity {entity.id} was updated")


async def update_question_answer_citation_format():
    with Session(engine) as session:
        qas = session.scalars(
            select(Question_Answer).where(Question_Answer.citations != None)
        ).all()

        for qa in qas:
            dc = DocumentCitation(
                document_id=str(qa.document_id), verbatims=qa.citations
            )
            qa.citations = dc.to_dict()

        session.add_all(qas)
        session.commit()
        logging.info(f"Question and Answer citations format was updated")
