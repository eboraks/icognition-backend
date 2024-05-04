import json
from app.models import DocumentDisplay
from app.prompt_models import RAGPrompt
from app.db_connector import get_engine
import pytest 


@pytest.mark.asyncio
async def test_workflow():

    from app.search_handler import SearchHandler ## Need to be imported within async becuase it's calling aiohttp via togeter client
    
    search = SearchHandler()

    user_id = "yU13Hk9BwEQiREgh91YM6EFKR7M2"

    query = "Tell me about Phil Jackson leadership style?"
    ##query = "what a test?"

    results = await search(user_id=user_id, query=query)
    assert results is not None
    assert len(results.documents_display) > 0


    results = await search(user_id = user_id, query = "Phil Jackson leadership style")
    assert results is not None
    for doc in results.documents_display:
        assert type(doc) == DocumentDisplay
        assert doc.title 
        assert doc.cosine_similarity

    results = await search(user_id = user_id)
    assert results is not None
    for doc in results.documents_display:
        assert type(doc) == DocumentDisplay
        assert doc.title


def test_search_embeddings():
    
    from app.search_handler import SearchHandler ## Need to be imported within async becuase it's calling aiohttp via togeter client
    
    search = SearchHandler()

    matches = search.search_embeddings(user_id="yU13Hk9BwEQiREgh91YM6EFKR7M2", search_term="Phil Jackson", threshold=0.1)

    for match in matches:
        assert match.cosine_similarity > 0.1
        assert match.id
        assert match.embedding_id