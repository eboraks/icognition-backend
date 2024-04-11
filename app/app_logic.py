import datetime
import sys
import logging
import os
import app.transformers_util
from app import html_parser
from app.db_connector import get_engine
from app.models import (
    Bookmark,
    Entity,
    Page,
    Document,
    PagePayload,
    DocumentDisplay,
    Document_Embeddings,
)
from app.prompt_models import DocumentPromptOne, DocumentPromptTwo
from app.together_api_client import (
    TogetherMixtralClient,
    ApiCallException,
)
from sqlalchemy import (
    select,
    delete,
    create_engine,
    and_,
    or_,
    Integer,
    String,
    func,
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

    logging.info(f"Deleting bookmark {bookmark_id} and associated records")
    with Session(engine) as session:
        session.execute(delete(Document).where(Document.id == doc.id))
        session.execute(delete(Bookmark).where(Bookmark.id == bookmark_id))
        session.execute(delete(Entity).where(Entity.document_id == doc.id))
        session.commit()
        logging.info(f"Bookmark {bookmark_id} and associated records deleted")


def delete_document_and_associate_records(document_id) -> None:
    """
    This function deletes a document and all associated records from the database.
    This function was create for testing purposes.
    """
    logging.info(f"Deleting document {document_id} and associated records")
    with Session(engine) as session:
        session.execute(delete(Document).where(Document.id == document_id))
        session.execute(delete(Entity).where(Entity.document_id == document_id))
        session.execute(delete(Concept).where(Concept.document_id == document_id))
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
        response = await mixtralClient.generate(body_text=doc.original_text, model=DocumentPromptOne)
        logging.info(f"Response from LLM {response}")

    except ApiCallException as e:
        logging.error(f"Error generating with LLM {e}. Status code {e.status_code} reason {e.reason}")
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
        generate_documents_embeddings()

    except Exception as e:
        doc.status = "Failure"
        logging.error(f"Error generating with LLM {e}")
        update_document(doc)

    
    # Generate entities
    try:
        logging.info(f"Generating entities for document {doc.id}")
        response = await mixtralClient.generate(body_text=doc.original_text, model=DocumentPromptTwo)
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
        
        ## Return document to indicate success
        return doc

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


def get_bookmark_by_url(url: str) -> Bookmark:
    url = html_parser.clean_url(url)
    session = Session(engine)
    bookmark = session.scalar(select(Bookmark).where(Bookmark.url == url))
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


def get_entities_tree_by_user_id(user_id: str) -> list:
    session = Session(engine)
    queryTypes = text(
        """select e.type 
	            from entity e
	            join document d on e.document_id = d.id
	            join bookmark b on b.document_id = d.id
	            where b.user_id = '{USER_ID}'
	        group by 1""".format(
            USER_ID=user_id
        )
    )

    types = session.execute(queryTypes).fetchall()
    nodes = []
    for index, type in enumerate(types):
        node = {}
        node["key"] = str(index)
        node["label"] = type[0]
        node["data"] = type[0] + " folder"
        node["children"] = []

        entities_nodes = get_entities_by_user_id_and_type(user_id, type[0])
        for index2, entity in enumerate(entities_nodes):
            entity_node = {}
            entity_node["key"] = node["key"] + "-" + str(index2)
            entity_node["label"] = entity.name
            entity_node["data"] = entity.name + " entity"
            entity_node["children"] = []

            node["children"].append(entity_node)

            documents = get_documenets_by_entity_id(entity.id)
            for index3, document in enumerate(documents):
                document_node = {}
                document_node["key"] = entity_node["key"] + "-" + str(index3)
                document_node["label"] = document.title
                document_node["data"] = document.title + " document"
                entity_node["children"].append(document_node)
        nodes.append(node)

    session.close()
    return nodes


def search_documents(user_id: str, search_term: str = None) -> list[Document]:
    session = Session(engine)

    if search_term is None:
        documents = session.scalars(
            select(Document)
            .join(Bookmark, Bookmark.document_id == Document.id)
            .filter(Bookmark.user_id == user_id)
        ).all()
    else:
        documents = session.scalars(
            select(Document)
            .join(Bookmark, Bookmark.document_id == Document.id)
            .filter(
                Bookmark.user_id == user_id,
                or_(
                    Document.title.ilike(f"%{search_term}%"),
                    Document.short_summary.ilike(f"%{search_term}%"),
                ),
            ).order_by(Document.update_at.desc())
        ).all()

    session.close()

    results = []
    for document in documents:
        entities = get_entities_by_document_id(document.id)
        display = DocumentDisplay.from_orm(document, entities=entities)
        results.append(display)

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
        ).all()

    try:
        embeddings = await app.transformers_util.get_document_embeddings(documents)
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





def search_embeddings(user_id: str, search_term: str) -> list[DocumentDisplay]:
    """
    This function searches for document embeddings by search term
    """
    logging.info(f"Generate embeddings for term {search_term}")
    embedded_term = app.transformers_util.generate_embeddings(search_term) ## Generate embeddings for search term
    logging.info(f"Embeddings for term {search_term} are length is {len(embedded_term)}")

    # Get document with some embeddings that are closest to the search term
    logging.info(f"Searching for documents with embeddings closest to term {search_term}")

    with Session(engine) as session:
        stmt = text("""SELECT a.document_id, a.cosine_similarity
                    FROM (SELECT de.document_id, MIN(1 - (de.embeddings <=> :vector)) AS cosine_similarity 
                        FROM document_embeddings AS de
                        JOIN bookmark ON de.document_id = bookmark.document_id
                        WHERE bookmark.user_id = :user_id 
                        GROUP BY de.document_id) a
                    WHERE a.cosine_similarity > 0.05
                    ORDER BY a.cosine_similarity DESC""")
        
        matched_documents = session.execute(stmt, {"vector": str(embedded_term.tolist()), "user_id": user_id}).all()
        
    logging.info(f"Found {len(matched_documents)} matched document for term {search_term}")

    results = []
    for md in matched_documents:
        document = get_document_by_id(md[0])
        entities = get_entities_by_document_id(md[0])
        display = DocumentDisplay.from_orm(document, entities=entities, cosine_similarity=md[1])
        results.append(display)    

    return results