import pytest
from app.db_connector import get_engine
import app.app_logic as app_logic
import app.getters as getter
import time


user_id = 'yU13Hk9BwEQiREgh91YM6EFKR7M2'
document_id = '099cbb20-4272-48bd-ad76-e038bfa77a86'

def test_get_ducument():
    docs = getter.get_documents_by_user_id(user_id)
    assert docs is not None
    for doc in docs:
        assert doc.title
        for ent in doc.entities:
            assert ent.id
            assert ent.type
            assert ent.name

def test_get_ducument_public():
    docs = getter.get_documents_public_by_user_id(user_id)
    assert docs is not None

    for doc in docs:
        assert doc.id
        for ent in doc.entities:
            assert ent.id
            assert ent.type
            assert ent.name

@pytest.mark.asyncio
async def test_entities():
    entities = getter.get_entities_by_document_id('083819cf-0b16-4be3-b8b1-a6f126d9070e')
    assert entities is not None
    for ent in entities:
        start_time = time.time()
        await getter.test_query_1(ent.id, ent.name_vector, ent.description_vector)
        print("Query 1 --- %s seconds ---" % (time.time() - start_time))
        start_time = time.time()
        await getter.test_query_2(ent.id, ent.name_vector, ent.description_vector)
        print("Query 2 --- %s seconds ---" % (time.time() - start_time))
        
