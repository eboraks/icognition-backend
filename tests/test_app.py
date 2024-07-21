from app.db_connector import get_engine
import app.app_logic as app_logic
import app.getters as getter
import app.main as main
from sqlalchemy.orm import Session
from sqlalchemy import delete, select
import pytest

from app.models import Document_Entity_Link, Entity 


user_id = 'yU13Hk9BwEQiREgh91YM6EFKR7M2'
engine = get_engine()



url = "https://www.yahoo.com/finance/news/collecting-degrees-thermometer-atlanta-woman-110000419.html"


def test_create_page():
    page = app_logic.create_page(url)
    assert page != None


async def test_bookmark_page():
    # Check if bookmark already exist, if yes delete it.
    # This is make the test more realistic.
    bookmark = app_logic.get_bookmark_by_url(url)
    if bookmark:
        app_logic.delete_bookmark_and_associate_records(bookmark.id)

    page = app_logic.create_page(url)
    bm = app_logic.create_bookmark(page)
    bookmark = app_logic.get_bookmark_by_url(url)
    assert bookmark != None

    doc = app_logic.get_document_by_id(bookmark.document_id)
    assert doc.id != None
    assert doc.url == url
    assert len(doc.original_text) > 0
    assert type(doc.original_text) == str

    # store the docuement id for future method
    document_id = doc.id
    app_logic.extract_info_from_doc(doc)

    # Testing the retrivel of document from the database
    doc = None
    doc = app_logic.get_document_by_id(document_id)

    # Testing the LLM extraction worked
    assert doc != None

@pytest.mark.asyncio
async def test_information_extration():
    tdoc = getter.get_document_by_id(130)
    assert tdoc != None

    await app_logic.extract_info_from_doc(doc = tdoc, testing=True)

    # Testing the LLM extraction worked
    with Session(engine) as session:
        session.add(tdoc)
        session.refresh(tdoc)
        assert len(tdoc.summary_bullet_points) > 0
        assert len(tdoc.entities) > 0

    await app_logic.generate_embeddings(user_id=user_id)

    # Testing the embeddings were generated
    doc_embeddings = getter.get_document_embeddings(tdoc.id)
    assert len(doc_embeddings) > 0
    for emb in doc_embeddings:
        assert len(emb.vector) > 0
        assert emb.field != None
        assert emb.text != None

    for ent in tdoc.entities:
        assert ent.id != None
        ent_embeddings = getter.get_entity_embeddings(ent.id)
        for ent_emb in ent_embeddings:
            assert len(ent_emb.vector) > 0
            assert ent_emb.field != None
            assert ent_emb.text != None
    
    

def test_get_document():
    doc = getter.get_document_by_id(130)
    assert doc.id == 130
    
    display = doc.to_display()
    assert display != None

    for ent in display.entities_and_concepts:
        assert ent.id != None
        assert ent.name != None
        assert ent.type != None

def test_insert_entities():
    
    doc = getter.get_document_by_id(65)
    
    user_id = 'HqAXhad3jrUWmPibnMf1xZczNIq2'
    entities_one = [
        Entity(name="Larry David", description="Comedian, writer, actor, and television producer", type="person"),
        Entity(name="Jerry Seinfeld", description="Comedian, actor, and writer", type="person"),
        Entity(name="Seinfeld", description="American television sitcom", type="concept"),
    ]

    entities_two = [
        Entity(name="Seinfeld", description="American television sitcom from the 1990s", type="concept"),
        Entity(name="Curb Your Enthusiasm", description="American television sitcom", type="concept"),
        Entity(name="HBO", description="American premium cable and satellite television network", type="concept"),
        Entity(name="Seinfeld", description="American television comedy show with Jerry Seinfeld from the 1990s", type="concept"),
    ]

    with Session(engine) as session:
        agg_entities = entities_one + entities_two
        for ent in agg_entities:
            ents = session.scalars(select(Entity).where(Entity.name == ent.name)).all()
            for ent in ents:
                session.execute(delete(Document_Entity_Link).where(Document_Entity_Link.entity_id == ent.id))
                session.execute(delete(Entity).where(Entity.id == ent.id))

        session.commit()

    existing_entities = getter.get_entities_by_document_id(doc.id)
    num_existing_entities = len(existing_entities)

    app_logic.insert_entities(user_id, entities_one, doc)

    app_logic.insert_entities(user_id, entities_two, doc)

    entities = getter.get_entities_by_document_id(doc.id)
    assert len(entities) == num_existing_entities + 5

@pytest.mark.asyncio
async def test_main_generate_document():
    bookmark = getter.get_bookmark_by_id(185)

    await main.generate_document(bookmark) 

    doc = getter.get_document_by_id(bookmark.document_id)
    assert doc != None
    