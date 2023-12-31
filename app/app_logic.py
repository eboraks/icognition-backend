import datetime
import sys
import logging
from app import html_parser
from app.models import (
    Bookmark,
    Keyphrase,
    Page,
    Document,
    Entity,
    Concept,
    ConceptDoc,
    EntitytDoc,
)
from app.process_exacted_info import ProcessConcepts, ProcessEntities
from app.hf_api_client import (
    HfApiClient,
    PeopleCompaniesPlacesTemplate,
    ConceptsTemplate,
    BulletPointTemplate,
)
from app.spacy_ner_client import NerClient
from sqlalchemy import select, delete, create_engine, and_, text
from sqlalchemy.orm import Session
from dotenv import dotenv_values


logging.basicConfig(
    stream=sys.stdout,
    format="%(asctime)s - %(message)s",
    level=logging.DEBUG,
    datefmt="%Y-%m-%d %H:%M:%S",
)

config = dotenv_values(".env")

engine = create_engine(config["LOCAL_PSQL"])


hf_client = HfApiClient()
ner_client = NerClient()
process_entities = ProcessEntities()
process_concepts = ProcessConcepts()


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
        session.execute(delete(Concept).where(Concept.document_id == doc.id))
        session.commit()
        logging.info(f"Bookmark {bookmark_id} and associated records deleted")


def delete_all_of_users_records(user_id: int) -> None:
    """Delete all of the records for a user. This function was create for testing

    Args:
        user_id int
    """
    bookmarks = get_bookmark_by_user_id(user_id)
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
    return doc


def get_documents_ids() -> list[int]:
    session = Session(engine)
    docs_ids = session.scalars(select(Document.id))
    session.close()
    return docs_ids


def get_keyphrases_by_document_id(document_id) -> Keyphrase:
    session = Session(engine)
    keyphrases = session.scalars(
        select(Keyphrase).where(Keyphrase.document_id == document_id)
    ).all()
    session.close()
    return keyphrases


def get_keyphrases_by_document_url(url) -> list[Keyphrase]:
    session = Session(engine)
    stmt = (
        select(Keyphrase)
        .join(Bookmark, Keyphrase.document_id == Bookmark.id)
        .where(Bookmark.url == url)
    )
    keyphrases = session.scalars(stmt).all()
    session.close()
    return keyphrases


def create_page(url: str) -> Page:
    page = html_parser.create_page(url)
    if page == None:
        logging.info(f"Page not found for url {url}")
        return None

    return page


async def create_document(page: Page):
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
    session.add(doc)
    session.commit()
    session.refresh(doc)
    session.close()

    return doc


async def update_document(doc: Document):
    with Session(engine) as session:
        session.add(doc)
        session.commit()
        session.refresh(doc)

    if doc.spacy_entities_json:
        entities = await process_entities(document_id=doc.id)
        if entities:
            await add_entities(entities, doc.id)

    if doc.concepts_generated:
        concepts = await process_concepts(document_id=doc.id)
        if concepts:
            await add_concepts(concepts, doc.id)


async def extract_meaning(doc: Document):
    """
    Function that takes pages and return a document with the generated summary,
    bullet points and entities generate by LLM
    """

    doc.status = "Processing"
    with Session(engine) as session:
        session.add(doc)
        session.commit()
        session.refresh(doc)

    try:
        found_entities_raw = hf_client.generate(
            doc.original_text, PeopleCompaniesPlacesTemplate()
        )
        concepts = hf_client.generate(doc.original_text, ConceptsTemplate())
        summary_bullet_points = hf_client.generate(
            doc.original_text, BulletPointTemplate()
        )
        ner_entities = ner_client(doc.original_text)

        if found_entities_raw:
            doc.llama2_entities_raw = found_entities_raw
        else:
            logging.info(f"No entities found for url {doc.url}")

        if concepts:
            doc.concepts_generated = concepts
        else:
            logging.info(f"No summary generated for url {doc.url}")
        if summary_bullet_points:
            doc.summary_bullet_points = summary_bullet_points
        else:
            logging.info(f"No bullet points generated for url {doc.url}  ")

        if ner_entities:
            doc.spacy_entities_json = ner_entities
        else:
            logging.info(f"No NER entities were found")

        doc.update_at = datetime.datetime.now()
        doc.status = "Done"

    except Exception as e:
        doc.status = "Failure"
        logging.error(f"Error generating with LLM {e}")
    finally:
        await update_document(doc)


async def add_entities(entities: list[Entity], document_id: int):
    ## Check that there are no entities and refs already in the DB
    delete_ent_str = f"DELETE FROM entity e USING entitytdoc d WHERE d.entity_id = e.id AND d.document_id = {document_id}"
    delete_ent_sql = text(delete_ent_str)

    delete_ref_str = f"DELETE FROM entitytdoc WHERE document_id = {document_id}"
    delete_refs = text(delete_ref_str)

    refs = []
    for entity in entities:
        ed = EntitytDoc(entity_id=entity.id, document_id=document_id)
        refs.append(ed)

    with Session(engine) as session:
        session.execute(delete_ent_sql)
        session.execute(delete_refs)
        session.commit()
        session.add_all(entities)
        session.add_all(refs)
        session.commit()


async def add_concepts(concepts: list[Concept], document_id: int):
    ## Check that there are no concept and refs already in the DB
    delete_con_str = f"DELETE FROM concept c USING conceptdoc d WHERE d.concept_id = c.id AND d.document_id = {document_id}"
    delete_con_sql = text(delete_con_str)

    delete_ref_str = f"DELETE FROM conceptdoc WHERE document_id = {document_id}"
    delete_refs = text(delete_ref_str)
    refs = []
    for concept in concepts:
        cd = ConceptDoc(concept_id=concept.id, document_id=document_id)
        refs.append(cd)

    with Session(engine) as session:
        session.execute(delete_con_sql)
        session.execute(delete_refs)
        session.commit()
        session.add_all(concepts)
        session.add_all(refs)
        session.commit()


async def create_bookmark(page: Page) -> Bookmark:
    session = Session(engine)

    # Check if document exists, retrieve the bookmark and keyphrases and return
    # if exists. Else, create the document, bookmark and keyphrase.
    user_id = config["DUMMY_USER"]

    bookmark = session.scalar(
        select(Bookmark).where(
            and_(Bookmark.url == page.clean_url, Bookmark.user_id == user_id)
        )
    )

    if bookmark:
        logging.info(f"Bookmark from url {page.clean_url} already exists")
        session.close()
        return bookmark

    doc = await create_document(page)

    bookmark = Bookmark()
    bookmark.url = page.clean_url
    bookmark.update_at = datetime.datetime.now()
    bookmark.document_id = doc.id

    session.add(bookmark)
    session.commit()
    session.refresh(bookmark)
    logging.info(f"Bookmark was created with id {bookmark.id}")

    session.close()

    return bookmark


def get_bookmark_by_user_id(user_id: int) -> list[Bookmark]:
    session = Session(engine)
    bookmarks = session.scalars(
        select(Bookmark).where(Bookmark.user_id == user_id)
    ).all()
    session.close()
    return bookmarks


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


def get_entities_by_document_id(document_id: int) -> list[Entity]:
    with Session(engine) as session:
        entities = session.scalars(
            select(Entity).where(Entity.document_id == document_id)
        ).all()
    return entities


def get_concepts_by_document_id(document_id: int) -> list[Concept]:
    with Session(engine) as session:
        concepts = session.scalars(
            select(Concept).where(Concept.document_id == document_id)
        ).all()
    return concepts
