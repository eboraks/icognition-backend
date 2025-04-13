## Initialize logging
from sqlmodel import SQLModel
from app.log import get_logger
logging = get_logger(__name__)

import datetime
import os, pickle
import re
import app.getters as getter
from app import html_parser
from app.db_connector import get_engine
from app.source_doc_handler import SourceDocHandler
from app.models import (
    Chat_Message,
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
import app.entity_handler as entity_handler



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


def insert_or_update_chat_history(chat_history: Chat_Message):
    with Session(engine) as session:

        ## Check if the chat history already exists using chat_id, user_id and event_name
        existing_chat_history = session.scalar(
            select(Chat_Message).where(
                Chat_Message.chat_id == chat_history.chat_id,
                Chat_Message.user_id == chat_history.user_id,
                Chat_Message.event_name == chat_history.event_name, 
                Chat_Message.asked_by == "system"
            )
        )

        if existing_chat_history:
            existing_chat_history.response = chat_history.response
            existing_chat_history.user_prompt = chat_history.user_prompt
            existing_chat_history.ai_prompt = chat_history.ai_prompt
            existing_chat_history.asked_by = chat_history.asked_by
            existing_chat_history.created_at = chat_history.created_at
            session.commit()
            session.refresh(existing_chat_history)
            return existing_chat_history
        else:
            session.add(chat_history)
            session.commit()
            session.refresh(chat_history)
            return chat_history



def merge_record(record):
    """
    Merge a record into the database
    
    Args:
        record: SQLAlchemy model instance to merge
        
    Returns:
        The merged record or None if input was None
        
    Raises:
        ValueError: If record is None
    """
    if record is None:
        logging.error("Cannot merge None record")
        raise ValueError("Record cannot be None")
        
    try:
        with Session(engine) as session:
            session.merge(record)
            session.commit()
    except Exception as e:
        logging.error(f"Error merging record: {str(e)}")
        raise e

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

        if doc.ai_is_about and doc.ai_bullet_points:
            doc.ai_summary_vector = await doc.generate_vector(
                geminiClient=genimi_client
            )
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
    
    ## Update the document with the source text in HTML
    doc.source_text_in_html = page.html_elements 
    if page.publish_date:
        doc.publication_date = page.publish_date
    if page.title:
        doc.title = page.title
    if page.authors:
        doc.authors = page.authors
    if page.metadata_description:
        doc.metadata_description = page.metadata_description
    if page.locale:
        doc.locale = page.locale
    if page.image_url:
        doc.image_url = page.image_url
    if page.site_name:
        doc.site_name = page.site_name

    bookmark = Source()
    bookmark.url = page.clean_url
    bookmark.update_at = datetime.datetime.now()
    bookmark.document_id = doc.id
    bookmark.user_id = user_id

    session.add(bookmark)
    session.add(doc)
    session.commit()
    session.refresh(bookmark)
    logging.info(f"Bookmark was created with id {bookmark.id}")

    session.close()

    return bookmark






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
