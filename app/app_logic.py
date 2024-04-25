import datetime
import sys
import logging
import os
import app.transformers_util
import app.subtopics_util as subtopics_util
from app import html_parser
from app.db_connector import get_engine
from app.icog_util import DocSummarizer
from app.models import (
    Bookmark,
    Entity,
    Page,
    Document,
    PagePayload,
    DocumentDisplay,
    Document_Embeddings,
    SubTopic_Entity_Link,
    SubTopicDisplay,
)
from app.prompt_models import DocumentPromptOne, DocumentPromptTwo, RAGPrompt
from app.together_api_client import (
    TogetherMixtralClient,
    ApiCallException,
)
from sqlalchemy import (
    select,
    delete,
    and_,
    or_,
    text,
    exc,
)
from sqlalchemy.orm import Session

logging.basicConfig(
    stream=sys.stdout,
    format="%(asctime)s - %(message)s",
    level=logging.INFO,
    datefmt="%Y-%m-%d %H:%M:%S",
)

env_vers = os.environ

engine = get_engine()

mixtralClient = TogetherMixtralClient()
summarizer = DocSummarizer()


def test_db_connection():

    try:
        conn = engine.connect()
        conn.close()
        return True
    except exc.OperationalError as e:
        logging.error(f"Error connectiong to DB {e}")
        return None


def delete_bookmark_and_associate_records(bookmark_id) -> None:
    """
    This function deletes a bookmark and all associated records from the database.
    This function was create for testing purposes.
    """
    doc = get_document_by_bookmark_id(bookmark_id)
    delete_document_and_associate_records(doc.id)

    logging.info(f"Deleting bookmark {bookmark_id} and associated records")
    with Session(engine) as session:
        session.execute(delete(Bookmark).where(Bookmark.id == bookmark_id))
        session.commit()
        logging.info(f"Bookmark {bookmark_id} and associated records deleted")


def delete_document_and_associate_records(document_id) -> None:
    """
    This function deletes a document and all associated records from the database.
    This function was create for testing purposes.
    """
    logging.info(f"Deleting document {document_id} and associated records")
    with Session(engine) as session:
        delete_links = session.scalars(select(SubTopic_Entity_Link).join(Entity).where(Entity.document_id == document_id)).all()
        for link in delete_links:
            session.delete(link)
        session.execute(delete(Entity).where(Entity.document_id == document_id))
        session.execute(delete(Document).where(Document.id == document_id))

        session.commit()
        logging.info(f"Document {document_id} and associated records deleted")


def delete_all_of_users_records(user_id: str) -> None:
    """Delete all of the records for a user. This function was create for testing

    Args:
        user_id int
    """
    bookmarks = get_bookmarks_by_user_id(user_id)
    for bookmark in bookmarks:
        delete_bookmark_and_associate_records(bookmark.id)


def get_document_by_bookmark_id(bookmark_id) -> Document:
    session = Session(engine)
    doc = session.scalar(
        select(Document)
        .join(Bookmark, Bookmark.document_id == Document.id)
        .where(Bookmark.id == bookmark_id)
    )
    session.close()
    return doc

def get_documents_by_user_id(user_id) -> list[Document]:
    session = Session(engine)
    docs = session.scalars(
        select(Document)
        .join(Bookmark, Bookmark.document_id == Document.id)
        .where(Bookmark.user_id == user_id)
    ).unique().all()
    session.close()
    return docs



def get_document_by_id(document_id) -> Document:
    session = Session(engine)
    doc = session.scalar(select(Document).where(Document.id == document_id))
    session.close()
    return doc


def get_document_by_url(url) -> Document:
    session = Session(engine)
    doc = session.scalar(select(Document).where(Document.url == url))
    session.close()


def get_documents_ids() -> list[int]:
    session = Session(engine)
    docs_ids = session.scalars(select(Document.id))
    session.close()
    return docs_ids


def get_entities_by_document_id(document_id) -> Entity:
    session = Session(engine)
    entities = session.scalars(
        select(Entity).where(Entity.document_id == document_id)
    ).all()
    session.close()
    return entities




def create_page(payload: PagePayload) -> Page:
    page = html_parser.create_page(payload)
    if page == None:
        logging.info(f"Page not found for url {payload.url}")
        return None

    return page


def create_document(page: Page):
    session = Session(engine)
    doc = session.scalar(select(Document).where(Document.url == page.clean_url))

    ## If Document isn't already exist, create it
    if doc:
        session.close()
        return doc

    doc = Document()
    doc.title = page.title.strip()
    doc.url = page.clean_url
    doc.original_text = page.full_text
    session.add(doc)
    session.commit()
    session.refresh(doc)
    session.close()

    return doc


def clone_document(doc: Document):

    old_doc = get_document_by_id(doc.id)

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
            select(Bookmark).where(Bookmark.document_id == old_document_id)
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


async def extract_info_from_doc(doc: Document):
    """
    Function that takes pages and return a document with the generated summary,
    bullet points and entities generate by LLM
    """

    doc.status = "Processing"
    update_document(doc)

    try:
        logging.info(f"Generating summary for document {doc.id}")
        summary = summarizer(doc.original_text)
        response = await mixtralClient.generate(messages=DocumentPromptOne.get_messages(summary), model=DocumentPromptOne)
        logging.info(f"Response from LLM {response}")

    except ApiCallException as e:
        logging.error(f"Error generating answer with LLM API {e}")
        ## TODO store exception in DB
        doc.status = "Api Failure"
        update_document(doc)
        return None

    except Exception as e:
        logging.error(f"Error generating with LLM {e}")
        doc.status = "Failure"
        update_document(doc)
        return None

    try:
        doc = response.populate_document(doc)
        doc.status = "Done"
        doc.update_at = datetime.datetime.now()
        update_document(doc)
        logging.info(f"Document {doc.id} was updated with summary and bullet points")
        await generate_documents_embeddings()

    except Exception as e:
        doc.status = "Failure"
        logging.error(f"Error generating with LLM {e}")
        update_document(doc)

    
    # Generate entities
    try:
        logging.info(f"Generating entities for document {doc.id}")
        response = await mixtralClient.generate(
            messages=DocumentPromptTwo.get_messages(summary), 
            model=DocumentPromptTwo)
        logging.info(f"Response from LLM {response}")

        # Using DocumentPromptTwo generate entities methods to create entities    
        entities = response.generate_entities()
        
        for entity in entities:
            entity.document_id = doc.id

        entities = await app.transformers_util.get_entity_embeddings(entities)

        with Session(engine) as session:
            session.add_all(entities)
            session.commit()
            logging.info(f"{len(entities)} Entities for Document {doc.id} were created")

        ## Run generate document embeddings again, to include the new entities
        await generate_documents_embeddings()

        ## Generate subtopics, one day this will be moved to a background task
        ## Although the factory takes entities, I am not using it to generate subtopics 
        ## for entities that are already in the database    
        bookmark = get_bookmark_by_document_id(doc.id)
        logging.info(f"Generating subtopics for user {bookmark.user_id}")
        await subtopics_util.subtopics_factory(bookmark.user_id)

        return doc # to indicate process completed.   

    except ApiCallException as e:
        logging.error(f"Error generating entities with LLM {e}")
        ## TODO store exception in DB
        #doc.status = "Api Failure"
        #update_document(doc)
        return

    except Exception as e:
        logging.error(f"Error generating entities from LLM API {e}")
        #doc.status = "Failure"
        #update_document(doc)
        return



def create_bookmark(page: Page, user_id: str) -> Bookmark:
    session = Session(engine)

    # Check if document exists, retrieve the bookmark and return
    # if exists. Else, create the document, bookmark.

    bookmark = session.scalar(
        select(Bookmark).where(
            and_(Bookmark.url == page.clean_url, Bookmark.user_id == user_id)
        )
    )

    if bookmark:
        logging.info(f"Bookmark from url {page.clean_url} already exists")
        session.close()
        return bookmark

    doc = create_document(page)

    bookmark = Bookmark()
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


def get_bookmarks_by_user_id(user_id: str) -> list[Bookmark]:
    session = Session(engine)
    bookmarks = session.scalars(
        select(Bookmark)
        .where(Bookmark.user_id == user_id)
        .order_by(Bookmark.update_at.desc())
    ).all()
    session.close()
    return bookmarks


def get_bookmark_by_document_id(document_id: int) -> Bookmark:
    session = Session(engine)
    bookmark = session.scalar(
        select(Bookmark).where(Bookmark.document_id == document_id)
    )
    session.close()
    return bookmark


def get_bookmark_by_url(user_id: str, url: str) -> Bookmark:
    url = html_parser.clean_url(url)
    session = Session(engine)
    bookmark = session.scalar(select(Bookmark).where(
        and_(Bookmark.url == url, Bookmark.user_id == user_id)))
    session.close()
    return bookmark


def get_bookmark_document(id: int) -> Document:
    session = Session(engine)
    doc = session.scalar(select(Document).where(Document.bookmark_id == id))
    session.close()
    return doc


def get_bookmark_by_id(id: int) -> Bookmark:
    session = Session(engine)
    bookmark = session.scalar(select(Bookmark).where(Bookmark.id == id))
    session.close()
    return bookmark


def get_entities_by_document_id(document_id) -> list[Entity]:
    session = Session(engine)
    entities = session.scalars(
        select(Entity).where(Entity.document_id == document_id)
    ).all()
    session.close()
    return entities


def get_entities_by_user_id(user_id: str) -> list[Entity]:
    session = Session(engine)
    entities = session.scalars(
        select(Entity)
        .join(Document, Document.id == Entity.document_id)
        .join(Bookmark, Bookmark.document_id == Document.id)
        .where(Bookmark.user_id == user_id)
    ).all()
    session.close()
    return entities


def get_entities_by_user_id_and_type(user_id: str, type: str) -> list[Entity]:
    session = Session(engine)
    entities = session.scalars(
        select(Entity)
        .join(Document, Document.id == Entity.document_id)
        .join(Bookmark, Bookmark.document_id == Document.id)
        .where(Bookmark.user_id == user_id, Entity.type == type)
    ).all()
    session.close()
    return entities


def get_documenets_by_entity_id(entity_id: int) -> list[Document]:
    session = Session(engine)
    documents = session.scalars(
        select(Document)
        .join(Entity, Entity.document_id == Document.id)
        .where(Entity.id == entity_id)
    ).all()
    session.close()
    return documents


def get_user_subtopics(user_id: str) -> list[SubTopicDisplay]:
    
    results = []
    with Session(engine) as session:
        query = text(
                """SELECT s.id, s.name, s.description, 
                    count(distinct d.id) as number_of_docs,
                    json_agg(distinct d.id)
                    FROM subtopic s
                    JOIN subtopic_entity_link l ON l.subtopic_id = s.id
                    JOIN entity e ON e.id = l.entity_id
                    JOIN document d ON d.id = e.document_id
                    WHERE s.user_id = '{USER_ID}'
                GROUP BY s.id, s.name, s.description
                ORDER BY count(distinct d.id) DESC""".format(USER_ID=user_id)
            )

        subtopics_touples = session.execute(query).fetchall()
        for touple in subtopics_touples:
            results.append(SubTopicDisplay.from_touple(touple))

    return results


def get_document_subtopics(document_id: str) -> list[SubTopicDisplay]:
    
    results = []
    with Session(engine) as session:
        query = text(
                """SELECT s.id, s.name, s.description, 
                    count(distinct d.id) as number_of_docs,
                    json_agg(distinct d.id)
                    FROM subtopic s
                    JOIN subtopic_entity_link l ON l.subtopic_id = s.id
                    JOIN entity e ON e.id = l.entity_id
                    JOIN document d ON d.id = e.document_id
                    WHERE d.id = '{DOC_ID}'
                GROUP BY s.id, s.name, s.description
                ORDER BY count(distinct d.id) DESC""".format(DOC_ID=document_id)
            )

        subtopics_touples = session.execute(query).fetchall()
        for touple in subtopics_touples:
            results.append(SubTopicDisplay.from_touple(touple))

    return results



async def generate_documents_embeddings():
    """
    This function generates embeddings for a list of documents
    The reason this is not being done in the extract_info_from_doc function is because we want to delay returning the response to the user
    """

    ## Get Documents that don't have embeddings, by joining with DocumentEmbeddings
    with Session(engine) as session:
        documents = session.scalars(
            select(Document)
            .join(
                Document_Embeddings,
                Document_Embeddings.document_id == Document.id,
                isouter=True,
            )
            .filter(Document_Embeddings.id == None)
        ).unique().all()

        entities = session.scalars(
            select(Entity)\
                .outerjoin(Document_Embeddings, Entity.id == Document_Embeddings.entity_id)\
                    .filter(Document_Embeddings.entity_id == None)
        ).unique().all()

    try:
        embeddings = await app.transformers_util.get_document_embeddings(documents)
        embeddings_from_entities = await app.transformers_util.get_document_embeddings_from_entities(entities)
        embeddings.extend(embeddings_from_entities)
    except Exception as e:
        logging.error(f"Error generating embeddings {e}")
        raise e

    try:
         with Session(engine) as session:
            session.add_all(embeddings)
            session.commit()
    except Exception as e:
        logging.error(f"Error saving embeddings {e}")
        raise e
    

        



async def generate_entities_embeddings():
    """
    This method generate embeddings for all entities in the database, it's used to retroactively generate embeddings for entities
    """
    with Session(engine) as session:
        ## Get Entities that don't have embeddings, by checking embeddings field is Null
        entities = session.scalars(
            select(Entity).filter(Entity.embedding == None)
        ).all()

        try:
            entities = await app.transformers_util.get_entity_embeddings(entities)
        except Exception as e:
            logging.error(f"Generate_entities_embeddings - Error generating embeddings {e}")
            raise e
        
        ## Save entities with embeddings
        try:
            session.add_all(entities)
            session.commit()

        except Exception as e:
            logging.error(f"Generate_entities_embeddings - Error saving embeddings {e}")
            raise e


def get_document_display_by_id(document_id: int) -> DocumentDisplay:
    doc = get_document_by_id(document_id)
    subtopic = get_document_subtopics(document_id)
    entities = get_entities_by_document_id(document_id)
    display = DocumentDisplay.from_orm(doc, entities=entities)
    return display


