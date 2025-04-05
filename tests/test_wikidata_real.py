import pytest
import asyncio
from app.wikidata_function_caller import WikidataFunctionCaller
from app.response_models import ExtractedEntity, Status

@pytest.mark.asyncio
async def test_real_wikidata_search():
    """
    Test that makes real calls to Wikidata API to search for entities.
    """
    # Arrange
    caller = WikidataFunctionCaller()
    test_entities = [
        "Barack Obama",
        "Microsoft",
        "Python (programming language)",
        "The Beatles",
        "Quantum computing"
    ]
    
    # Act & Assert
    for entity_name in test_entities:
        print(f"\nSearching for: {entity_name}")
        
        # Search for the entity
        search_results = await caller.search_entity(entity_name)
        
        print(f"Found {len(search_results)} results:")
        for i, result in enumerate(search_results[:3]):  # Show top 3 results
            print(f"  {i+1}. ID: {result.id}")
            print(f"     Label: {result.label}")
            print(f"     Description: {result.description}")
            print(f"     Aliases: {result.aliases}")
        
        # Get details for the first result
        if search_results:
            entity_id = search_results[0].id
            print(f"\nGetting details for {entity_id}:")
            
            details = await caller.get_entity_details(entity_id)
            print(f"  Label: {details.get('label')}")
            print(f"  Description: {details.get('description')}")
            print(f"  Instance of: {details.get('instance_of')}")
            print(f"  Pageviews: {details.get('pageviews')}")
        
        # Add a small delay to avoid rate limiting
        await asyncio.sleep(1)

@pytest.mark.asyncio
async def test_real_entity_enrichment():
    """
    Test that makes real calls to Wikidata API to enrich entities.
    """
    # Arrange
    caller = WikidataFunctionCaller()
    test_entities = [
        ExtractedEntity(
            type="Person",
            name="Albert Einstein",
            description="German-born theoretical physicist",
            status=Status.SUCCESS
        ),
        ExtractedEntity(
            type="Organization",
            name="Google",
            description="American multinational technology company",
            status=Status.SUCCESS
        ),
        ExtractedEntity(
            type="Technology",
            name="Artificial Intelligence",
            description="Intelligence demonstrated by machines",
            status=Status.SUCCESS
        )
    ]
    
    # Act & Assert
    for entity in test_entities:
        print(f"\nEnriching entity: {entity.name} ({entity.type})")
        
        enriched_entity = await caller.enrich_entity(entity)
        
        print(f"  Wikidata ID: {enriched_entity.wikidata_id}")
        print(f"  Wikidata Label: {enriched_entity.wikidata_label}")
        print(f"  Wikidata Description: {enriched_entity.wikidata_description}")
        print(f"  Wikidata Instance Of: {enriched_entity.wikidata_instance_of}")
        print(f"  Wikidata Pageviews: {enriched_entity.wikidata_pageviews}")
        
        # Add a small delay to avoid rate limiting
        await asyncio.sleep(1) 