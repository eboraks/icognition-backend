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

async def generate_entities_vectors():
    with Session(engine) as session:
        entities = session.scalars(select(Entity).where(Entity.name_vector == None)).all()

        for entity in entities:
            
            entity.name_vector = await genimi_client.generate_embedding(entity.name)
            session.add(entity)
        
        session.commit()
        logging.info(f"Vector names for {len(entities)} entities were generated")

    with Session(engine) as session:
        entities = session.scalars(select(Entity).where(Entity.description_vector == None)).all()
        logging.info(f"Entities without description vector {len(entities)}")

        for entity in entities:
            entity.description_vector = await genimi_client.generate_embedding(entity.name + ': ' + entity.description)
            session.add(entity)
            session.commit()
        logging.info(f"Vector descriptions for {len(entities)} entities were generated")





async def insert_entities(user_id, entities: list[Entity], doc: Document) -> list[Entity]:

    ## Make sure all previous created entities have vectors
    ## This allow search for similar entities before creating a new one
    await generate_entities_vectors()
    
    try:
        session_entities = []
        for entity in entities:
            ## Use regex to make sure the entity is words only
            if not re.match(r"^[A-Za-z\s]+$", entity.name):
                logging.warning(f"Entity name '{entity.name}' contains non-word characters and will be skipped")
                continue

            if entity.type == "Other":
                ## Skip entities that are of type 'Other' to save space and computation
                logging.warning(f"Entity name '{entity.name}' is of type 'Other' and will be skipped")
                continue

            ## Safe insert, return existing entity if it already exists or the new one
            session_entities.append(await insert_entity_safe(user_id=user_id, new_entity= entity, _document_id=doc.id))
        
        logging.info(f"{len(session_entities)} Entities for Document {doc.id} were associated")

        return session_entities
    except Exception as e:
        logging.error(f"Error inserting entities {e}")
        return None   
        
    

       

async def insert_entity_safe(user_id: str, new_entity: Entity, _document_id: str) -> Entity: 
    
    matched_entity = await getter.get_similar_entity_by_name_vector(user_id=user_id, new_entity = new_entity)
    
    with Session(engine) as session:
        
        if matched_entity:
        
            logging.info(f"Matched Entity. New: {new_entity.name} Existing: {matched_entity.name}")
            
            
            session.merge(Document_Entity_Link(document_id=_document_id, entity_id=matched_entity.id, 
                                               verbatim_text=new_entity.verbatim_text, description=new_entity.description))
            session.commit()
            return new_entity
        else:
            new_entity.name_vector = await genimi_client.generate_embedding(new_entity.name)
            new_entity.description_vector = await genimi_client.generate_embedding(new_entity.name + ': ' + new_entity.description)
            session.add(new_entity)
            session.commit()
            session.refresh(new_entity)
            
            session.merge(Entity_User_Link(user_id=user_id, entity_id=new_entity.id))
            session.merge(Document_Entity_Link(document_id=_document_id, entity_id=new_entity.id, 
                                               verbatim_text=new_entity.verbatim_text, description=new_entity.description))
           
            session.commit()
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

        if len(entities) == 0:
            logging.info(f"No entities were found for document {doc.id}")
            return []

        ## Iterate over entities check if verbatim_text is in the original_text, if not, remove it
        entities = [entity for entity in entities if doc.original_text.find(entity.verbatim_text) != -1] 

        return await insert_entities(user_id, entities, doc)  
        
    except Exception as e:
        logging.error(f"generate_entities: Error generating entities from LLM API {e}")
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

        if len(entities) == 0:
            logging.info(f"No topic were found for document {doc.id}")
            return []

        ## Iterate over entities check if verbatim_text is in the original_text, if not, remove it
        entities = [entity for entity in entities if doc.original_text.find(entity.verbatim_text) != -1]

        return await insert_entities(user_id, entities, doc)  
        
    except Exception as e:
        logging.error(f"generate_topics: Error generating entities from LLM API {e}")
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
    
    
     
    with Session(engine) as session:

        embeddings = []
        for entity in entities:
            session.add(entity)
            for emb in entity.to_embeddings():
                if emb.text:
                    emb.vector = await genimi_client.generate_embedding(emb.text)
                    emb.user_id = user_id
                    embeddings.append(emb)        
    
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



async def update_question_answer_citation_format():
    with Session(engine) as session:
        qas = session.scalars(select(Question_Answer).where(Question_Answer.citations != None)).all()
        
        for qa in qas:
            dc = DocumentCitation(document_id = str(qa.document_id),  verbatims = qa.citations)
            qa.citations = dc.to_dict()
        
        session.add_all(qas)
        session.commit()
        logging.info(f"Question and Answer citations format was updated")