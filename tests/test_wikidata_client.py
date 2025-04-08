import pytest
from unittest.mock import patch, Mock, AsyncMock
from app.wikidata_client import WikidataClient, WikidataSearchResult
from app.models import Entity
from app.db_connector import get_engine
from sqlalchemy import select
from sqlalchemy.orm import Session
import asyncio

@pytest.mark.asyncio
async def test_text_search_success():
    # Arrange
    mock_response = {
    "search": [
            {
                "id": "Q123",
                "label": "Test Entity",
                "description": "Test Description",
                "aliases": ["Test Alias"],
                "sitelinks": ["Test Sitelink"],
                "concepts": ["Q456"]
            }
        ]
    }
    
    client = WikidataClient()
    
    # Act
    with patch('aiohttp.ClientSession.get') as mock_get:
        mock_response_obj = AsyncMock()
        mock_response_obj.status = 200
        mock_response_obj.json = AsyncMock(return_value=mock_response)
        mock_get.return_value.__aenter__.return_value = mock_response_obj
        
        results = await client.text_search("Test Entity")
        
        # Assert
        assert len(results) == 1
        assert isinstance(results[0], WikidataSearchResult)
        assert results[0].id == "Q123"
        assert results[0].label == "Test Entity"
        assert results[0].description == "Test Description"
        assert results[0].aliases == ["Test Alias"]
        assert results[0].sitelinks == ["Test Sitelink"]
        assert results[0].instance_of == ["Q456"]

@pytest.mark.asyncio
async def test_text_search_no_results():
    # Arrange
    mock_response = {"search": []}
    
    client = WikidataClient()
    
    # Act
    with patch('aiohttp.ClientSession.get') as mock_get:
        mock_response_obj = AsyncMock()
        mock_response_obj.status = 200
        mock_response_obj.json = AsyncMock(return_value=mock_response)
        mock_get.return_value.__aenter__.return_value = mock_response_obj
        
        results = await client.text_search("Nonexistent Entity")
        
        # Assert
        assert len(results) == 0

@pytest.mark.asyncio
async def test_text_search_error():
    # Arrange
    client = WikidataClient()
    
    # Act & Assert
    with patch('aiohttp.ClientSession.get') as mock_get:
        mock_response_obj = AsyncMock()
        mock_response_obj.status = 404
        mock_response_obj.raise_for_status = Mock(side_effect=Exception("Not found"))
        mock_get.return_value.__aenter__.return_value = mock_response_obj
        
        with pytest.raises(Exception):
            await client.text_search("Test Entity")

@pytest.mark.asyncio
async def test_search_by_label_success():
    # Arrange
    mock_response = {
        "results": {
            "bindings": [
                {
                    "item": {"value": "http://www.wikidata.org/entity/Q123"},
                    "itemLabel": {"value": "Test Entity"},
                    "itemDescription": {"value": "Test Description"},
                    "alias": {"value": "Test Alias"},
                    "instanceOf": {"value": "http://www.wikidata.org/entity/Q456"},
                    "sitelinkCount": {"value": "5"}
                }
            ]
        }
    }
    
    client = WikidataClient()
    
    # Act
    with patch('aiohttp.ClientSession.get') as mock_get:
        mock_response_obj = AsyncMock()
        mock_response_obj.status = 200
        mock_response_obj.json = AsyncMock(return_value=mock_response)
        mock_get.return_value.__aenter__.return_value = mock_response_obj
        
        results = await client.search_by_label("Test Entity")
        
        # Assert
        assert len(results) == 1
        assert isinstance(results[0], WikidataSearchResult)
        assert results[0].id == "Q123"
        assert results[0].label == "Test Entity"
        assert results[0].description == "Test Description"
        assert results[0].aliases == ["Test Alias"]
        assert results[0].instance_of == ["Q456"]

@pytest.mark.asyncio
async def test_search_by_label_no_results():
    # Arrange
    mock_response = {"results": {"bindings": []}}
    
    client = WikidataClient()
    
    # Act
    with patch('aiohttp.ClientSession.get') as mock_get:
        mock_response_obj = AsyncMock()
        mock_response_obj.status = 200
        mock_response_obj.json = AsyncMock(return_value=mock_response)
        mock_get.return_value.__aenter__.return_value = mock_response_obj
        
        results = await client.search_by_label("Nonexistent Entity")
        
        # Assert
        assert len(results) == 0

@pytest.mark.asyncio
async def test_search_by_label_error():
    # Arrange
    client = WikidataClient()
    
    # Act & Assert
    with patch('aiohttp.ClientSession.get') as mock_get:
        mock_response_obj = AsyncMock()
        mock_response_obj.status = 404
        mock_response_obj.raise_for_status = Mock(side_effect=Exception("Not found"))
        mock_get.return_value.__aenter__.return_value = mock_response_obj
        
        with pytest.raises(Exception):
            await client.search_by_label("Test Entity")

@pytest.mark.asyncio
async def test_search_by_label_missing_fields():
    # Arrange
    mock_response = {
        "results": {
            "bindings": [
                {
                    "item": {"value": "http://www.wikidata.org/entity/Q123"},
                    "itemLabel": {"value": "Test Entity"}
                    # Missing description, aliases, and instanceOf
                }
            ]
        }
    }
    
    client = WikidataClient()
    
    # Act
    with patch('aiohttp.ClientSession.get') as mock_get:
        mock_response_obj = AsyncMock()
        mock_response_obj.status = 200
        mock_response_obj.json = AsyncMock(return_value=mock_response)
        mock_get.return_value.__aenter__.return_value = mock_response_obj
        
        results = await client.search_by_label("Test Entity")
        
        # Assert
        assert len(results) == 1
        assert results[0].id == "Q123"
        assert results[0].label == "Test Entity"
        assert results[0].description == "No description"
        assert results[0].aliases == []
        assert results[0].instance_of == []

@pytest.mark.asyncio
async def test_wikidata_real_search():
    # Arrange
    client = WikidataClient()
    
    # Get some real entities from the database
    with Session(get_engine()) as session:
        # Get a few entities with different types
        entities = session.scalars(
            select(Entity)
            .where(Entity.name != None)
            .limit(5)
        ).all()
    
    # Act & Assert
    for entity in entities:
        print(f"\nTesting entity: {entity.name} (Type: {entity.type})")
        
        # Test text_search
        text_results = await client.text_search(entity.name)
        print(f"\nText search results for '{entity.name}':")
        for result in text_results:
            print(f"- ID: {result.id}")
            print(f"  Label: {result.label}")
            print(f"  Description: {result.description}")
            print(f"  Aliases: {result.aliases}")
            print(f"  Instance of: {result.instance_of}")
        
        # Test search_by_label
        label_results = await client.search_by_label(entity.name)
        print(f"\nLabel search results for '{entity.name}':")
        for result in label_results:
            print(f"- ID: {result.id}")
            print(f"  Label: {result.label}")
            print(f"  Description: {result.description}")
            print(f"  Aliases: {result.aliases}")
            print(f"  Instance of: {result.instance_of}")
        
        # Add a small delay to avoid rate limiting
        await asyncio.sleep(1) 