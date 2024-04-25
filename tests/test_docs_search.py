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

    results = await search(user_id=user_id, query=query)
    assert type(results[0]) == RAGPrompt

    results = await search(user_id = user_id, query = "Phil Jackson leadership style")
    assert len(results) > 0
    for result in results:
        assert type(result) == DocumentDisplay
        assert result.title 
        assert result.cosine_similarity

    results = await search(user_id = user_id)
    assert len(results) > 0
    for result in results:
        assert type(result) == DocumentDisplay
        assert result.title

    
    