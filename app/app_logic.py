import datetime
import json
import sys
import logging
import os, pickle
#import app.transformers_util as transformers_util
import app.getters as getter
from app import html_parser
from app.db_connector import get_engine
from app.source_doc_handler import SourceDocHandler
from app.models import (
    Source,
    Entity,
    Page,
    Document,
    PagePayload,
    Embedding,
    Document_Entity_Link,
    RagAnswerPublic,
)
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

async def generate_entities_vectors():
    with Session(engine) as session:
        entities = session.scalars(select(Entity).where(Entity.name_vector == None)).all()

        for entity in entities:
            
            entity.name_vector = await genimi_client.generate_embedding(entity.name)
            session.add(entity)
        
        session.commit()
        logging.info(f"Vector names for {len(entities)} entities were generated")


async def insert_entities(user_id, entities: list[Entity], doc: Document) -> list[Entity]:

    ## Make sure all previous created entities have vectors
    ## This allow search for similar entities before creating a new one
    await generate_entities_vectors()
    
    try:
        session_entities = []
        for entity in entities:
            ## Safe insert, return existing entity if it already exists or the new one
            session_entities.append(await insert_entity_safe(user_id, entity))
        
        with Session(engine) as session:
            for entity in session_entities:
                session.merge(Document_Entity_Link(document_id=doc.id, entity_id=entity.id))
            session.commit()
        
        logging.info(f"{len(entities)} Entities for Document {doc.id} were associated")

        return session_entities
    except Exception as e:
        logging.error(f"Error inserting entities {e}")
        return None   
        
    

       

async def insert_entity_safe(user_id: str, new_entity: Entity) -> Entity: 
    

    needle_vector = await genimi_client.generate_embedding(new_entity.name)
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

        ## For testing, if file exists, load it and return payload
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



async def generate_entities(user_id: str, doc: Document, testing: bool = False) -> list[Entity]:
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
            #logging.info(f"Response from LLM {response}")
            
            if testing:
                with open(filename, "wb") as f:
                    pickle.dump(response, f)

        # Using the entities builder to get the entities from the response    
        entities = response.entities_builder()

        return await insert_entities(user_id, entities, doc)  
        
    except Exception as e:
        logging.error(f"Error generating entities from LLM API {e}")
        return None


async def generate_topics(user_id: str, doc: Document, testing: bool = False) -> list[Entity]:
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
            #logging.info(f"Response from LLM {response}")
            
            if testing:
                with open(filename, "wb") as f:
                    pickle.dump(response, f)

        # Using the entities builder to get the topics (also entities) from the response
        entities = response.entities_builder()

        return await insert_entities(user_id, entities, doc)  
        
    except Exception as e:
        logging.error(f"Error generating entities from LLM API {e}")
        return None


async def generate_doc_quesions_answers(user_id: str, doc: Document, testing: bool = False) -> bool:

    try:
        logging.info(f"Generating questions and answers for document {doc.id}")
        
        ## If file exists, load it and return payload
        prompt = IdentifyQuestionsAnswerPrompt.build_prompt(doc.original_text)
        response = await genimi_client.generate_response(prompt, IdentifyQuestionsAnswerPrompt)
        ## Using the entities builder to get the entities from the response    
        qans = await response.questions_answers_builder(document_id = doc.id)
 

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
        docs_embedding = select(Embedding.source_id)\
        .filter(and_(Embedding.source_type == 'document', Embedding.user_id == user_id))\
            .group_by(Embedding.source_id)

        docs = session.scalars(
            select(Document)\
            .join(Source, Source.document_id == Document.id)\
            .where(and_(
                Document.id.not_in(docs_embedding),
                Document.ai_is_about != None,
                Document.status == 'Done', Source.user_id == user_id))).unique().all()
        
        ## Find entities that don't have embeddings
        entity_embedding = select(Embedding.source_id)\
        .filter(and_(Embedding.source_type == 'entity', Embedding.user_id == user_id))\
            .group_by(Embedding.source_id)

        entities = session.scalars(
            select(Entity)\
            .join(Document_Entity_Link, Document_Entity_Link.entity_id == Entity.id)\
            .join(Source, Source.document_id == Document_Entity_Link.document_id)\
            .where(and_(
                Entity.id.not_in(entity_embedding), Source.user_id == user_id)
                )).unique().all()

    try:
        await generate_embeddings_for_docs(documents=docs, user_id=user_id)   
    except Exception as e:
        logging.error(f"Error generating embeddings for documents {e}")
    
    try:
        await generate_embeddings_for_entities(entities=entities, user_id=user_id)
    except Exception as e:
        logging.error(f"Error generating embeddings for entities {e}")
    
    ## Generate embeddings for entities that don't have embeddings
    ## May, 22. Remove Embedding.version < Entity.version) from where clause, becuase embedding have old versions (versions add additive)
    ## results in always generating embeddings for entities with version above 1. That mean that updated entities will not generate new embeddings
    ## for now. In the future this can be improved, but for now it's ok.
    

        


async def generate_embeddings_for_entities(entities: list[Entity], user_id: str):

    logging.info(f"Generating embeddings for {len(entities)} entities")
    
    embeddings = []
    for entity in entities:
        for emb in entity.to_embeddings():
            if emb.text:
                emb.vector = await genimi_client.generate_embedding(emb.text)
                emb.user_id = user_id
                embeddings.append(emb)
        
    with Session(engine) as session:        
    
        session.add_all(embeddings)
        session.commit()


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
        embedding = session.scalar(select(Embedding).where(Embedding.source_id == entity.id))
        embedding.vector = await genimi_client.generate_embedding(entity.name)
        session.add(embedding)
        session.commit()
        logging.info(f"Embedding for entity {entity.id} was updated")





async def custom_question(document_id: int, question: str) -> RagAnswerPublic:
    """
    This function generates a summary with verbatim sentences
    """
    doc = getter.get_document_by_id(document_id) 
    
    prompt = AskQuestionPrompt.build_prompt([doc], question)
    generated_response = await genimi_client.generate_response(prompt, AskQuestionPrompt) 
    
    return generated_response.question_answer_builder(question=question)
