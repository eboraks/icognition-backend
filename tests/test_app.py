from app.db_connector import get_engine
import app.app_logic as app_logic
import app.getters as getter
import app.deleters as deleter
import app.main as main
from sqlalchemy.orm import Session
from sqlalchemy import delete, select
import pytest

from app.models import Document_Entity_Link, Entity
from app.gemini_prompts_models import Citation 


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
    bm = app_logic.create_source_bookmark(page)
    bookmark = app_logic.get_bookmark_by_url(url)
    assert bookmark != None

    doc = app_logic.get_document_by_id(bookmark.document_id)
    assert doc.id != None
    assert doc.url == url
    assert len(doc.original_text) > 0
    assert type(doc.original_text) == str

    # store the docuement id for future method
    document_id = doc.id
    app_logic.generate_summary(doc)

    # Testing the retrivel of document from the database
    doc = None
    doc = app_logic.get_document_by_id(document_id)

    # Testing the LLM extraction worked
    assert doc != None

@pytest.mark.asyncio
async def test_summary_extration():


    deleter.reset_document_for_testing(130)

    tdoc = getter.get_document_public_by_id(130)
    assert tdoc != None

    assert tdoc.is_about is None
    assert tdoc.summary_bullet_points is None
    assert tdoc.summary_citations is None

    tdoc = await app_logic.generate_summary(doc = tdoc)

    # Testing the LLM extraction worked
    with Session(engine) as session:
        session.add(tdoc)
        session.refresh(tdoc)
        assert len(tdoc.ai_bullet_points) > 0
        assert tdoc.ai_is_about != None
        assert len(tdoc.ai_citations) > 0


    start_match_counter = []
    end_match_counter = []
    for c in tdoc.ai_citations:
        
        citation = Citation(**c)
        assert citation.start_str != None
        assert citation.end_str != None
        start_match_counter.append(tdoc.original_text.find(citation.start_str))
        end_match_counter.append(tdoc.original_text.find(citation.end_str))

    start_mismatches = len([x for x in start_match_counter if x == -1])
    end_mismatches = len([x for x in end_match_counter if x == -1])
    assert (start_mismatches / len(start_match_counter)) < 0.1
    assert (end_mismatches / len(end_match_counter)) < 0.1
    
    
@pytest.mark.asyncio
async def test_entitties_extraction():
    
    deleter.reset_document_for_testing(27)

    tdoc = getter.get_document_public_by_id(27)
    user_id = getter.get_source_by_document_id(tdoc.id).user_id
    entities = getter.get_entities_ids_by_document_id(tdoc.id)
    assert tdoc != None

    assert len(entities) == 0

    ent_success = await app_logic.generate_entities(user_id= user_id, doc = tdoc)
    topic_success = await app_logic.generate_topics(user_id= user_id, doc = tdoc)

    assert ent_success is not None
    
    entities = getter.get_entities_by_document_id(tdoc.id)

    assert len(entities) > 0
    assert ent_success == True

    for ent in entities:
        assert ent.id != None
        assert ent.name != None
        assert ent.type != None
    
    topic_entities = [ent for ent in entities if ent.type == "topic"]
    assert len(topic_entities) > 0
    assert topic_success == True


@pytest.mark.asyncio
async def test_identify_questions_and_answers():
    
    document_id = 27
    deleter.delete_question_and_answer_associated_with_document(document_id)

    tdoc = getter.get_document_public_by_id(document_id)
    user_id = getter.get_source_by_document_id(tdoc.id).user_id

    success = await app_logic.generate_doc_quesions_answers(user_id= user_id, doc = tdoc)

    qans = getter.get_question_answer_by_document_id(document_id)

    assert success == True
    assert len(qans) > 0



def test_get_document():
    doc = getter.get_document_public_by_id(130)
    assert doc.id == 130
    
    display = doc.to_public()
    assert display != None

    for ent in display.entities_and_concepts:
        assert ent.id != None
        assert ent.name != None
        assert ent.type != None

def test_insert_entities():
    
    doc = getter.get_document_public_by_id(65)
    
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

    doc = getter.get_document_public_by_id(bookmark.document_id)
    assert doc != None
    