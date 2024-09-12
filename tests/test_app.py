import os
from app.db_connector import get_engine
import app.app_logic as app_logic
import app.getters as getter
import app.deleters as deleter
import app.main as main
from sqlalchemy.orm import Session
from sqlalchemy import delete, select
import pytest
import urllib.parse

from app.models import Document_Entity_Link, Entity, PagePayload
from app.gemini_prompts_models import Verbatim


user_id = 'yU13Hk9BwEQiREgh91YM6EFKR7M2'
engine = get_engine()



url = "https://www.yahoo.com/finance/news/collecting-degrees-thermometer-atlanta-woman-110000419.html"


def test_create_page():
    

    # Get the directory containing the current script
    working_directory = os.path.abspath(os.curdir)
    
    filename = "https%3A%2F%2Fmedium.com%2F%40roma.gordeev%2Fwhy-go-is-the-worst-language-you-could-ever-learn-4a7be0d37509.html"
    with open(f"{working_directory}/data/{filename}", 'r') as file:
        content = file.read()
    
    url = urllib.parse.unquote(filename)
    payload = PagePayload(url=url, user_id=user_id, html=content, source='web')
    page = app_logic.create_page(payload)
    assert page != None


@pytest.mark.asyncio
async def test_bookmark_page():
    # Check if bookmark already exist, if yes delete it.
    # This is make the test more realistic.
    filename = "https%3A%2F%2Fmedium.com%2F%40roma.gordeev%2Fwhy-go-is-the-worst-language-you-could-ever-learn-4a7be0d37509.html"
    url = urllib.parse.unquote(filename)
    
    bookmark = getter.get_source_by_url(user_id=user_id, url=url)
    if bookmark:
        deleter.delete_source_and_associate_records(bookmark.id)

    with open(f"data/{filename}", 'r') as file:
        content = file.read()
    
    payload = PagePayload(url=url, user_id=user_id, html=content, source='web')

    page = app_logic.create_page(payload)
    bm = app_logic.create_source_bookmark(page=page, user_id=user_id)
    bookmark = getter.get_source_by_url(user_id=user_id, url=url)
    assert bookmark != None

    doc = getter.get_document_by_id(bookmark.document_id)
    assert doc.id != None
    assert doc.url == url
    assert len(doc.original_text) > 0
    assert type(doc.original_text) == str

    # store the docuement id for future method
    document_id = doc.id
    await app_logic.generate_summary(doc)

    # Testing the retrivel of document from the database
    doc = None
    doc = getter.get_document_by_id(document_id)

    # Testing the LLM extraction worked
    assert doc != None
    assert len(doc.ai_bullet_points) > 0
    assert doc.ai_is_about != None

@pytest.mark.asyncio
async def test_summary_extration():


    filename = "https%3A%2F%2Fwww.wsj.com%2Fpolitics%2Felections%2Firan-is-working-to-undercut-trump-in-presidential-election-u-s-spy-agencies-say-7f67fad7%3Fmod%3Delections_lead_story.html"
    url = urllib.parse.unquote(filename)
    
    bookmark = getter.get_source_by_url(user_id=user_id, url=url)
    if bookmark:
        deleter.delete_source_and_associate_records(bookmark.id)

    with open(f"data/{filename}", 'r') as file:
        content = file.read()
    
    payload = PagePayload(url=url, user_id=user_id, html=content, source='web')

    page = app_logic.create_page(payload)
    assert page != None
    bm = app_logic.create_source_bookmark(page=page, user_id=user_id)
    tdoc = getter.get_document_by_id(bm.document_id)
    assert tdoc != None

    assert tdoc.ai_is_about is None
    assert len(tdoc.ai_bullet_points) == 0
    assert len(tdoc.ai_citations) == 0

    tdoc = await app_logic.generate_summary(doc = tdoc)

    assert len(tdoc.ai_bullet_points) > 0
    assert tdoc.ai_is_about != None
    assert len(tdoc.ai_citations) > 0    


    match_counter = 0
    for c in tdoc.ai_citations:
        
        citation = Verbatim(**c)
        assert citation.verbatim_text != None
        if (tdoc.original_text.find(citation.verbatim_text) > -1):
            match_counter += 1
        

    match_ratio = float(match_counter)/ float(len(tdoc.ai_citations))
    assert match_ratio > 0.5
    assert match_ratio > 0.9
    assert match_ratio == 1.0
    
    
    ent_success = await app_logic.generate_entities(user_id= user_id, doc = tdoc)
    topic_success = await app_logic.generate_topics(user_id= user_id, doc = tdoc)

    entities = getter.get_entities_by_document_id(tdoc.id)

    assert len(entities) > 0
    assert ent_success == True
    assert topic_success == True

    for ent in entities:
        assert ent.id != None
        assert ent.name != None
        assert ent.type != None
    
    generate_qa = await app_logic.generate_doc_quesions_answers(user_id= user_id, doc = tdoc)

    qans = getter.get_question_answer_by_document_id(document_id=tdoc.id)

    assert generate_qa == True
    assert len(qans) > 0

   




    
