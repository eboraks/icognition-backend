import datetime
import json
import sys
import logging
import os, pickle
import app.transformers_util as transformers_util
import app.subtopics_util as subtopics_util
import app.getters as getter
from types import SimpleNamespace
from app import html_parser
from app.db_connector import get_engine
from app.icog_util import DocSummarizer, original_text_to_sentences, sentences_to_text
from pydantic.json import pydantic_encoder
from app.models import (
    Bookmark,
    Entity,
    Page,
    Document,
    PagePayload,
    Embedding,
    Document_Entity_Link,
    Question_Answer,
    Question_Answer_Display,
    SubTopic_Document_Link,
    SubTopic_Embedding_Link
)
from app.prompt_models import CustomQuestionPrompt, DocumentPromptTwo, DocumentPromptVerbatim
from app.gemini_client import GeminiClient
from sqlalchemy import (
    select,
    delete,
    and_,
    or_,
    text,
    exc,
)
from sqlalchemy.orm import Session

from app.gemini_prompts_models import AskQuestionPrompt, EntitiesPrompt, FoundQuestionAnswer, IdentifyQuestionsAnswerPrompt, SummarizePrompt, TopicPrompt

logging.basicConfig(
    stream=sys.stdout,
    format="%(asctime)s - %(message)s",
    level=logging.INFO,
    datefmt="%Y-%m-%d %H:%M:%S",
)

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
    doc.html_elements = json.loads(page.html_elements)

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

def generate_entities_vectors():
    with Session(engine) as session:
        entities = session.scalars(select(Entity).where(Entity.name_vector == None)).all()

        for entity in entities:
            
            entity.name_vector = transformers_util.generate_embeddings(entity.name)
            session.add(entity)
        
        session.commit()
        logging.info(f"Vector names for {len(entities)} entities were generated")


def insert_entities(user_id, entities: list[Entity], doc: Document) -> bool:

    generate_entities_vectors()
    
    try:
        session_entities = []
        for entity in entities:
            ## Safe insert, return existing entity if it already exists or the new one
            session_entities.append(insert_entity_safe(user_id, entity))
        
        with Session(engine) as session:
            for entity in session_entities:
                session.merge(Document_Entity_Link(document_id=doc.id, entity_id=entity.id))
            session.commit()
        
        logging.info(f"{len(entities)} Entities for Document {doc.id} were associated")

        return True
    except Exception as e:
        logging.error(f"Error inserting entities {e}")
        return False   
        
    

       

def insert_entity_safe(user_id: str, new_entity: Entity) -> Entity: 
    

    needle_vector = transformers_util.generate_embeddings(new_entity.name)
    matched = getter.get_similar_entity_by_name_vector(user_id=user_id, vector=needle_vector)
    
    with Session(engine) as session:
        
        if matched:
            logging.info(f"Entity {new_entity.name} already exists, adding synonyms to it.")
            ent = session.scalar(select(Entity).where(Entity.id == matched["entity_id"]))
            
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
            new_entity.name_vector = needle_vector
            session.add(new_entity)
            session.commit()
            session.refresh(new_entity)
            return new_entity



async def generate_summary(doc: Document, testing: bool = False) -> Document:
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

            response = await genimi_client.generate_response(
                SummarizePrompt.build_prompt(doc.original_text), 
                SummarizePrompt)
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
        doc.summary_vector = await doc.generate_vector(geminiClient=genimi_client)
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



async def generate_entities(user_id: str, doc: Document, testing: bool = False) -> bool:
    """
    Generate entities for a document

    args:
        user_id: str
        doc: Document
        testing: bool
    """
    try:
        logging.info(f"Generating entities for document {doc.id}")
        
        ## If file exists, load it and return payload
        filename = f"response_two_{doc.id}.json"
        if os.path.exists(filename):
            with open(filename, "rb") as f:
                response = pickle.load(f)
                logging.info(f"Response loaded from file for document {doc.id}")
        else:
            response = await genimi_client.generate_response(
                EntitiesPrompt.build_prompt(doc.original_text), 
                EntitiesPrompt)
            logging.info(f"Response from LLM {response}")
            
            if testing:
                with open(filename, "wb") as f:
                    pickle.dump(response, f)

        # Using the entities builder to get the entities from the response    
        entities = response.entities_builder()

        results = insert_entities(user_id, entities, doc)  
        return results

    except Exception as e:
        logging.error(f"Error generating entities from LLM API {e}")
        return False


async def generate_topics(user_id: str, doc: Document, testing: bool = False) -> bool:
    """
    # Generate topics for a document
    """
    try:
        logging.info(f"Generating entities for document {doc.id}")
        
        ## If file exists, load it and return payload
        filename = f"response_two_{doc.id}.json"
        if os.path.exists(filename):
            with open(filename, "rb") as f:
                response = pickle.load(f)
                logging.info(f"Response loaded from file for document {doc.id}")
        else:
            response = await genimi_client.generate_response(
                TopicPrompt.build_prompt(doc.original_text), 
                TopicPrompt)
            logging.info(f"Response from LLM {response}")
            
            if testing:
                with open(filename, "wb") as f:
                    pickle.dump(response, f)

        # Using the entities builder to get the topics (also entities) from the response
        entities = response.entities_builder()

        results = insert_entities(user_id, entities, doc)  
        return results

    except Exception as e:
        logging.error(f"Error generating entities from LLM API {e}")
        return False


async def generate_doc_quesions_answers(user_id: str, doc: Document, testing: bool = False) -> bool:

    try:
        logging.info(f"Generating questions and answers for document {doc.id}")
        
        ## If file exists, load it and return payload
        prompt = IdentifyQuestionsAnswerPrompt.build_prompt(doc.original_text)
        response = await genimi_client.generate_response(prompt, IdentifyQuestionsAnswerPrompt)
        ## Using the entities builder to get the entities from the response    
        qans = response.questions_answers_builder(document_id = doc.id)
 

    except Exception as e:
        logging.error(f"Error generating entities from LLM API {e}")


    try:
        with Session(engine) as session:
            session.add_all(qans)
            session.commit()
        return True
    except Exception as e:
        logging.error(f"Error saving questions and answers {e}")

        return False



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
        
        docs_embedding = select(Embedding.source_id)\
        .filter(and_(Embedding.source_type == 'document', Embedding.user_id == user_id))\
            .group_by(Embedding.source_id)

        docs = session.scalars(
            select(Document)\
            .join(Bookmark, Bookmark.document_id == Document.id)\
            .where(and_(
                Document.id.not_in(docs_embedding),
                Document.is_about != None,
                Document.learning_from_document != None, 
                Document.status == 'Done', Bookmark.user_id == user_id))).unique().all()

    generate_embeddings_for_docs(docs, user_id)   

    ## Generate embeddings for entities that don't have embeddings
    ## May, 22. Remove Embedding.version < Entity.version) from where clause, becuase embedding have old versions (versions add additive)
    ## results in always generating embeddings for entities with version above 1. That mean that updated entities will not generate new embeddings
    ## for now. In the future this can be improved, but for now it's ok.
    

    generate_embeddings_for_entities(user_id)
        


async def generate_embeddings_for_entities(user_id: str):

    ## Find entities that don't have embeddings
    with Session(engine) as session:
        entities = session.scalars(
            select(Entity)\
            .join(Document_Entity_Link, Document_Entity_Link.entity_id == Entity.id)\
            .join(Bookmark, Bookmark.document_id == Document_Entity_Link.document_id)\
            .outerjoin(Embedding, Embedding.source_id == Entity.id)\
            .where(Embedding.source_id == None, Embedding.user_id == user_id, Bookmark.user_id == user_id)).unique().all()
    
        embeddings = []
        for entity in entities:
            emb = entity.to_embeddings()
            emb.vector = transformers_util.generate_embeddings(emb.text)
            emb.user_id = user_id
            embeddings.append(emb)
        
        session.add_all(embeddings)
        session.commit()


async def generate_embeddings_for_docs(docs: list[Document], user_id: str):

    embeddings = []
    for doc in docs:
        for emb in doc.to_embeddings():
            emb.vector = transformers_util.generate_embeddings(emb.text)
            emb.user_id = user_id
            embeddings.append(emb)
    
    with Session(engine) as session:
        session.add_all(embeddings)
        session.commit() 


def update_entity_embedding(entity: Entity):
    with Session(engine) as session:
        embedding = session.scalar(select(Embedding).where(Embedding.source_id == entity.id))
        embedding.vector = transformers_util.generate_embeddings(entity.name)
        session.add(embedding)
        session.commit()
        logging.info(f"Embedding for entity {entity.id} was updated")





async def custom_question(document_id: int, question: str) -> Question_Answer_Display:
    """
    This function generates a summary with verbatim sentences
    """
    doc = getter.get_document_by_id(document_id) 
    
    prompt = AskQuestionPrompt.build_prompt([doc], question)
    generated_response = await genimi_client.generate_response(prompt, AskQuestionPrompt) 
    
    return generated_response.question_answer_builder(question=question)
