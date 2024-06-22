import datetime
import json
import sys
import logging
import os, pickle
import app.transformers_util as transformers_util
import app.subtopics_util as subtopics_util
import app.getters as getter
from app import html_parser
from app.db_connector import get_engine
from app.icog_util import DocSummarizer, original_text_to_sentences, sentences_to_text
from app.models import (
    Bookmark,
    Entity,
    Page,
    Document,
    PagePayload,
    Embedding,
    Document_Entity_Link,
    SubTopic_Document_Link,
    SubTopic_Embedding_Link,
    Answer
)
from app.prompt_models import DocumentPromptOne, DocumentPromptTwo, DocumentPromptVerbatim
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

doc_counter_for_subtopics = 0

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
    doc = getter.get_document_by_bookmark_id(bookmark_id)
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
        delete_subt_links = session.scalars(select(SubTopic_Document_Link).where(SubTopic_Document_Link.document_id == document_id)).all()
        for link in delete_subt_links:
            session.delete(link)

        session.flush()
        delete_doc_ent_links = session.scalars(select(Document_Entity_Link).where(Document_Entity_Link.document_id == document_id)).all()
        for delink in delete_doc_ent_links:
            session.delete(delink)

        delete_doc_embs = session.scalars(select(Embedding).where(Embedding.source_id == document_id)).all()
        emb_ids = []
        for emb in delete_doc_embs:
            emb_ids.append(emb.id)
            session.delete(emb)

        session.flush()
        delete_subt_emb_links = session.scalars(select(SubTopic_Embedding_Link).where(SubTopic_Embedding_Link.embedding_id.in_(emb_ids))).all()
        for emblink in delete_subt_emb_links:
            session.delete(emblink)
        
        session.execute(delete(Document).where(Document.id == document_id))

        session.commit()
        logging.info(f"Document {document_id} and associated records deleted")


def delete_all_of_users_records(user_id: str) -> None:
    """Delete all of the records for a user. This function was create for testing

    Args:
        user_id int
    """
    bookmarks = getter.get_bookmarks_by_user_id(user_id)
    for bookmark in bookmarks:
        delete_bookmark_and_associate_records(bookmark.id)



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
    doc.title = page.title
    doc.url = page.clean_url
    doc.original_text = page.full_text
    doc.authors = ", ".join(page.authors) if page.authors else None
    doc.metadata_keywords = ", ".join(page.keywords) if page.keywords else None
    doc.locale = page.locale
    doc.publication_date = page.publish_date
    doc.image_url = page.image_url
    doc.site_name = page.site_name
    doc.metadata_description = page.metadata_description
    doc.html_elements = page.html_elements

    session.add(doc)
    session.commit()
    session.refresh(doc)
    session.close()

    return doc


def clone_document(doc: Document):

    old_doc = getter.get_document_by_id(doc.id)

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

def insert_entities(entities: list[Entity], doc: Document = None) -> None:

    
    session_entities = []
    for entity in entities:
        ## Safe insert, return existing entity if it already exists or the new one
        session_entities.append(insert_entity_safe(entity))
    
    with Session(engine) as session:
        for entity in session_entities:
            session.merge(Document_Entity_Link(document_id=doc.id, entity_id=entity.id))
        session.commit()
       
        
        logging.info(f"{len(entities)} Entities for Document {doc.id} were associated")


def  insert_entity_safe(new_entity: Entity) -> Entity: 
    with Session(engine) as session:

        ## If the entity name is <=5 characters, reduce the levenshtein distance to 1
        if len(new_entity.name) <= 2:
            distance = 0
        elif len(new_entity.name) <= 5:
            distance = 1
        else:
            distance = 2

        query = text("""
            SELECT e.id
                FROM entity e 
                WHERE (levenshtein_less_equal(LOWER(e.name), LOWER(:search), :dist) <=:dist)
                LIMIT 1
            """).bindparams(search=new_entity.name, dist=distance)
        
        exist_entity = session.execute(query).scalar_one_or_none()
        if exist_entity:
            logging.info(f"Entity {new_entity.name} already exists")
            ent = session.scalar(select(Entity).where(Entity.id == exist_entity))
            
            if ent.descriptions_bank == None:   
                ent.descriptions_bank = f"{new_entity.description}"
            else:
                ent.descriptions_bank += f"; {new_entity.description}" 
            
            ent.version += 1
            ent.update_at = datetime.datetime.now()
            session.commit()
            session.refresh(ent)
            return ent
        else:
            session.add(new_entity)
            session.commit()
            session.refresh(new_entity)
            return new_entity



async def extract_info_from_doc(doc: Document, testing: bool = False):
    """
    Function that takes pages and return a document with the generated summary,
    bullet points and entities generate by LLM
    """

    doc.status = "Processing"
    update_document(doc)

    try:
        logging.info(f"Generating summary for document {doc.id}")

        ## If file exists, load it and return payload
        filename = f"response_one_{doc.id}.json"
        if os.path.exists(filename):
            with open(filename, "rb") as f:
                response = pickle.load(f)
                logging.info(f"Response loaded from file for document {doc.id}")
        else:

            summary = summarizer(doc.original_text).toStr()
            response = await mixtralClient.generate(messages=DocumentPromptOne.get_messages(summary), model=DocumentPromptOne)
            ## Save response in json file
            if testing:
                with open(filename, "wb") as f:
                    pickle.dump(response, f)

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

    except Exception as e:
        doc.status = "Failure"
        logging.error(f"Error generating with LLM {e}")
        update_document(doc)


    # Generate entities
    try:
        logging.info(f"Generating entities for document {doc.id}")
        
        ## If file exists, load it and return payload
        filename = f"response_two_{doc.id}.json"
        if os.path.exists(filename):
            with open(filename, "rb") as f:
                response = pickle.load(f)
                logging.info(f"Response loaded from file for document {doc.id}")
        else:
            summary = summarizer(doc.original_text).toStr()
            response = await mixtralClient.generate(
                messages=DocumentPromptTwo.get_messages(summary), 
                model=DocumentPromptTwo)
            logging.info(f"Response from LLM {response}")
            
            if testing:
                with open(filename, "wb") as f:
                    pickle.dump(response, f)

        # Using DocumentPromptTwo generate entities methods to create entities    
        entities = response.generate_entities()

        insert_entities(entities, doc)

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






async def generate_embeddings(user_id: str):
    """
    This function generates embeddings for a list of documents
    The reason this is not being done in the extract_info_from_doc function is because we don't want 
    to delay returning the response to the user
    """

    ## Generate embeddings for documents that don't have embeddings
    with Session(engine) as session:
        
        docs = session.scalars(
            select(Document)\
            .join(Bookmark, Bookmark.document_id == Document.id)\
            .outerjoin(Embedding, Embedding.source_id == Document.id)\
            .where(and_(
                Embedding.source_id == None, 
                Document.status == 'Done', Bookmark.user_id == user_id))).unique().all()

        embeddings = []
        for doc in docs:
            embeddings.extend(doc.to_embeddings())
            
        for embedding in embeddings:
            embedding.vector = transformers_util.generate_embeddings(embedding.text)
            embedding.user_id = user_id
        session.add_all(embeddings)
        session.commit()    

    ## Generate embeddings for entities that don't have embeddings
    ## May, 22. Remove Embedding.version < Entity.version) from where clause, becuase embedding have old versions (versions add additive)
    ## results in always generating embeddings for entities with version above 1. That mean that updated entities will not generate new embeddings
    ## for now. In the future this can be improved, but for now it's ok.
    with Session(engine) as session:
        entities = session.scalars(
            select(Entity)\
            .join(Document_Entity_Link, Document_Entity_Link.entity_id == Entity.id)\
            .join(Bookmark, Bookmark.document_id == Document_Entity_Link.document_id)\
            .outerjoin(Embedding, Embedding.source_id == Entity.id)\
            .where(Embedding.source_id == None, Bookmark.user_id == user_id)).unique().all()

        embeddings = []
        for entity in entities:
            embeddings.extend(entity.to_embeddings())
            
        for embedding in embeddings:
            embedding.vector = transformers_util.generate_embeddings(embedding.text)
            embedding.user_id = user_id
        session.add_all(embeddings)
        session.commit()


def update_entity_embedding(entity: Entity):
    with Session(engine) as session:
        embedding = session.scalar(select(Embedding).where(Embedding.source_id == entity.id))
        embedding.vector = transformers_util.generate_embeddings(entity.name)
        session.add(embedding)
        session.commit()
        logging.info(f"Embedding for entity {entity.id} was updated")


def document_key_sentences(bookmark_id: int):
    """
    This function returns the key sentences of a document
    """
    with Session(engine) as session:
        doc = session.scalar(select(Document).join(Bookmark, Bookmark.document_id == Document.id).where(Bookmark.id == bookmark_id))
        if doc is None:
            logging.error(f"Document for bookmark ID {bookmark_id} not found")
            raise ValueError(f"Document for bookmark ID {bookmark_id} not found")

        if doc.original_text == None:
            logging.error(f"Document for bookmark ID {bookmark_id} has no text")
            raise ValueError(f"Document for bookmark ID {bookmark_id} has no text")
        
        summary = summarizer(doc.original_text).toStr()
    
    sentences = original_text_to_sentences(doc.original_text)

    key_sentences = []
    for sentence in sentences:
        if sentence in summary:
            key_sentences.append(sentence)
    
    return key_sentences

async def generate_xray_summary(document_id: int) -> dict:
    """
    This function generates a summary with verbatim sentences
    """
    doc = getter.get_document_by_id(document_id) 
    
    if doc.raw_answer == None:

        sentences = original_text_to_sentences(summarizer(doc.original_text).toStr())
        llmresp = await mixtralClient.generate(DocumentPromptVerbatim, DocumentPromptVerbatim.get_messages(sentences_to_text(sentences)))
        
        if (llmresp is None):
            logging.error(f"Error generating summary with verbatim for document {document_id}")
            return None
        
        results = llmresp.to_display(sentences)
        doc.raw_answer = json.dumps(results, default=vars)
        update_document(doc)
    else:
        results = json.loads(doc.raw_answer)

    docDisplay = getter.get_document_display_by_id(document_id)
    
    return {"results": results, "doc": docDisplay}