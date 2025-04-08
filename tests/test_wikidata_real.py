import pytest
import asyncio
import uuid
from app.wikidata_client import WikidataClient
from app.response_models import ExtractedEntity, Status
from app.entity_handler import find_wikidata_entity, insert_entities
from app.models import Entity, Document_Entity_Link, Entity_User_Link, User, Document
from sqlalchemy.orm import Session
from app.db_connector import get_engine
from sqlalchemy import select

@pytest.mark.asyncio
async def test_real_wikidata_search():
    """
    Test that makes real calls to Wikidata API to search for entities.
    """
    # Arrange
    client = WikidataClient()
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
        search_results = await client.text_search(entity_name)
        
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
            
            details = await client.search_by_id(entity_id)
            print(f"  Label: {details.label}")
            print(f"  Description: {details.description}")
            print(f"  Instance of: {details.instance_of}")
        
        # Add a small delay to avoid rate limiting
        await asyncio.sleep(1)

@pytest.mark.asyncio
async def test_real_entity_enrichment():
    """
    Test that makes real calls to Wikidata API to enrich entities.
    """
    # Arrange
    client = WikidataClient()
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
        
        # Search for the entity by name
        search_results = await client.text_search(entity.name)
        
        if search_results:
            # Get the first result
            wikidata_result = search_results[0]
            
            print(f"  Wikidata ID: {wikidata_result.id}")
            print(f"  Wikidata Label: {wikidata_result.label}")
            print(f"  Wikidata Description: {wikidata_result.description}")
            print(f"  Wikidata Instance Of: {wikidata_result.instance_of}")
        else:
            print(f"  No Wikidata results found for {entity.name}")
        
        # Add a small delay to avoid rate limiting
        await asyncio.sleep(1)

@pytest.mark.asyncio
async def test_find_wikidata_entity():
    """
    Test the find_wikidata_entity function directly.
    """
    # Test entities with different characteristics
    test_entities = [
        ExtractedEntity(
            type="Person",
            name="Elon Musk",
            description="Technology entrepreneur and CEO",
            status=Status.SUCCESS
        ),
        ExtractedEntity(
            type="Organization",
            name="United Nations",
            description="International organization",
            status=Status.SUCCESS
        ),
        ExtractedEntity(
            type="Place",
            name="Mount Everest",
            description="Highest mountain on Earth",
            status=Status.SUCCESS
        ),
        # Test with an entity unlikely to have a direct Wikidata match
        ExtractedEntity(
            type="Concept",
            name="XYZ123NonExistentEntity",
            description="A made-up entity that should not exist in Wikidata",
            status=Status.SUCCESS
        )
    ]
    
    for entity in test_entities:
        print(f"\nFinding Wikidata entity for: {entity.name} ({entity.type})")
        
        # Call the function we want to test
        result = await find_wikidata_entity(entity)
        
        # Display the results
        print(f"  Result ID: {result.id}")
        print(f"  Name: {result.name}")
        print(f"  Normalized Label: {result.normalized_label}")
        print(f"  Type: {result.type}")
        print(f"  Wikidata ID: {result.wikidata_id}")
        if result.wikidata_id:
            print(f"  Wikidata Label: {result.wikidata_label}")
            print(f"  Wikidata Description: {result.wikidata_description}")
            print(f"  Wikidata Instance Of: {result.wikidata_instance_of}")
        
        # Add a small delay to avoid rate limiting
        await asyncio.sleep(1)

@pytest.mark.asyncio
async def test_insert_entities():
    """
    Test the insert_entities function with real database operations.
    
    This test will:
    1. Create test entities
    2. Insert them into the database
    3. Verify they were correctly stored with Wikidata enrichment
    4. Clean up by removing test entities
    """
    # Create a test user ID
    test_user_id = "test_user_" + str(uuid.uuid4()).replace("-", "")[:8]
    
    # Create a test document ID
    test_doc_id = str(uuid.uuid4())
    
    # Test entities to insert
    test_entities = [
        ExtractedEntity(
            type="Person",
            name="Marie Curie",
            description="Physicist and chemist who conducted pioneering research on radioactivity",
            status=Status.SUCCESS
        ),
        ExtractedEntity(
            type="Organization",
            name="World Health Organization",
            description="Specialized agency of the United Nations responsible for international public health",
            status=Status.SUCCESS
        ),
        # Include an entity that probably won't have a Wikidata match to test fallback behavior
        ExtractedEntity(
            type="Product",
            name="Test Product XYZ789",
            description="A fictional product for testing purposes",
            status=Status.SUCCESS
        )
    ]
    
    try:
        print("\nTesting insert_entities function")
        
        # Call the insert_entities function
        await insert_entities(test_user_id, test_entities, test_doc_id)
        
        # Verify the entities were stored in the database
        engine = get_engine()
        with Session(engine) as session:
            # Check each test entity
            for test_entity in test_entities:
                entity_id = (test_entity.name + test_entity.type).replace(" ", "").lower()
                
                # Query the entity
                entity = session.get(Entity, entity_id)
                if entity:
                    print(f"\nFound entity in database: {entity.name}")
                    print(f"  ID: {entity.id}")
                    print(f"  Description: {entity.description}")
                    print(f"  Type: {entity.type}")
                    print(f"  Wikidata ID: {entity.wikidata_id}")
                    
                    if entity.wikidata_id:
                        print(f"  Wikidata Label: {entity.wikidata_label}")
                        print(f"  Wikidata Description: {entity.wikidata_description}")
                        print(f"  Wikidata Instance Of: {entity.wikidata_instance_of}")
                        print(f"  Has description vector: {entity.description_vector is not None}")
                    
                    # Check that links were created
                    user_link = session.query(Entity_User_Link).filter_by(
                        entity_id=entity_id, user_id=test_user_id
                    ).first()
                    
                    doc_link = session.query(Document_Entity_Link).filter_by(
                        entity_id=entity_id, document_id=test_doc_id
                    ).first()
                    
                    print(f"  User link created: {user_link is not None}")
                    print(f"  Document link created: {doc_link is not None}")
                else:
                    print(f"Entity not found in database: {test_entity.name}")
    
    finally:
        # Clean up test data
        print("\nCleaning up test data...")
        engine = get_engine()
        with Session(engine) as session:
            # Delete entity links first
            for test_entity in test_entities:
                entity_id = (test_entity.name + test_entity.type).replace(" ", "").lower()
                
                # Delete user links
                session.query(Entity_User_Link).filter_by(
                    entity_id=entity_id, user_id=test_user_id
                ).delete()
                
                # Delete document links
                session.query(Document_Entity_Link).filter_by(
                    entity_id=entity_id, document_id=test_doc_id
                ).delete()
                
                # Delete the entity itself
                entity = session.get(Entity, entity_id)
                if entity:
                    session.delete(entity)
            
            session.commit()
            print("Test data cleanup completed")

@pytest.mark.asyncio
async def test_insert_existing_entity():
    """
    Test the handling of existing entities in insert_entities function.
    This test will:
    1. Insert an entity first time
    2. Try to insert the same entity again with a different document
    3. Verify that the entity wasn't duplicated but new links were created
    """
    # Create test user IDs and document IDs
    test_user_id = "test_user_" + str(uuid.uuid4()).replace("-", "")[:8]
    test_user_id_2 = "test_user_" + str(uuid.uuid4()).replace("-", "")[:8]
    test_doc_id_1 = str(uuid.uuid4())
    test_doc_id_2 = str(uuid.uuid4())
    
    # Create test users and documents in the database
    engine = get_engine()
    with Session(engine) as session:
        # Create first test user
        user1 = User(id=test_user_id)
        session.add(user1)
        # Create second test user
        user2 = User(id=test_user_id_2)
        session.add(user2)
        
        # Create first test document
        doc1 = Document(
            id=test_doc_id_1,
            title="Test Document 1",
            original_text="This is a test document about Albert Einstein.",
            user_id=test_user_id
        )
        session.add(doc1)
        
        # Create second test document
        doc2 = Document(
            id=test_doc_id_2,
            title="Test Document 2",
            original_text="Another test document mentioning Albert Einstein.",
            user_id=test_user_id_2
        )
        session.add(doc2)
        
        session.commit()
    
    # Test entity that will be inserted twice
    test_entity = ExtractedEntity(
        type="Person",
        name="Albert Einstein",
        description="German-born theoretical physicist that won the Nobel Prize in Physics in 1921. He is known for the theory of relativity and E=mc^2.",
        status=Status.SUCCESS
    )
    
    # Calculate expected entity ID
    expected_entity_id = (test_entity.name + test_entity.type).replace(" ", "").lower()
    print(f"\nExpected entity ID: {expected_entity_id}")
    
    try:
        print("\nTesting existing entity handling")
        
        # First insertion
        print("\nFirst insertion with first user and document")
        print(f"User ID: {test_user_id}")
        print(f"Document ID: {test_doc_id_1}")
        await insert_entities(test_user_id, [test_entity], test_doc_id_1)
        
        # Wait a bit for Wikidata enrichment and vector generation
        print("\nWaiting for Wikidata enrichment and vector generation...")
        await asyncio.sleep(2)
        
        # Verify first insertion
        engine = get_engine()
        with Session(engine) as session:
            # Try to find entity by ID
            entity = session.get(Entity, expected_entity_id)
            if not entity:
                print("\nTrying to find entity by name...")
                # Try to find by name if ID search failed
                entity = session.scalar(
                    select(Entity).where(Entity.name == test_entity.name)
                )
            
            if not entity:
                # List all entities in the database for debugging
                print("\nListing all entities in database:")
                all_entities = session.scalars(select(Entity)).all()
                for e in all_entities:
                    print(f"  - ID: {e.id}, Name: {e.name}, Type: {e.type}")
                raise AssertionError("First entity insertion failed - entity not found in database")
            
            print(f"\nFirst insertion successful: {entity.name}")
            print(f"  ID: {entity.id}")
            print(f"  Name: {entity.name}")
            print(f"  Type: {entity.type}")
            print(f"  Wikidata ID: {entity.wikidata_id}")
            print(f"  Description vector exists: {entity.description_vector is not None}")
        
        # Second insertion with different user and document
        print("\nSecond insertion with second user and document")
        print(f"User ID: {test_user_id_2}")
        print(f"Document ID: {test_doc_id_2}")
        await insert_entities(test_user_id_2, [test_entity], test_doc_id_2)
        
        # Wait a bit for links to be created
        print("\nWaiting for links to be created...")
        await asyncio.sleep(1)
        
        # Verify the results
        with Session(engine) as session:
            # Check that only one entity exists
            entity = session.get(Entity, expected_entity_id)
            if not entity:
                print("\nTrying to find entity by name...")
                entity = session.scalar(
                    select(Entity).where(Entity.name == test_entity.name)
                )
            
            if not entity:
                print("\nListing all entities in database:")
                all_entities = session.scalars(select(Entity)).all()
                for e in all_entities:
                    print(f"  - ID: {e.id}, Name: {e.name}, Type: {e.type}")
                raise AssertionError("Entity not found in database after second insertion")
                
            print(f"\nFound entity in database: {entity.name}")
            print(f"  ID: {entity.id}")
            print(f"  Name: {entity.name}")
            print(f"  Type: {entity.type}")
            print(f"  Wikidata ID: {entity.wikidata_id}")
            
            # Check user links - should have both users
            user_links = session.query(Entity_User_Link).filter_by(entity_id=entity.id).all()
            user_ids = [link.user_id for link in user_links]
            print(f"  User links count: {len(user_links)}")
            print(f"  Linked users: {user_ids}")
            assert len(user_links) == 2, "Should have links to both users"
            assert test_user_id in user_ids, "Should have link to first user"
            assert test_user_id_2 in user_ids, "Should have link to second user"
            
            # Check document links - should have both documents
            doc_links = session.query(Document_Entity_Link).filter_by(entity_id=entity.id).all()
            doc_ids = [str(link.document_id) for link in doc_links]
            print(f"  Document links count: {len(doc_links)}")
            print(f"  Linked documents: {doc_ids}")
            assert len(doc_links) == 2, "Should have links to both documents"
            assert test_doc_id_1 in doc_ids, "Should have link to first document"
            assert test_doc_id_2 in doc_ids, "Should have link to second document"
    
    finally:
        # Clean up test data
        print("\nCleaning up test data...")
        engine = get_engine()
        with Session(engine) as session:
            # Try both the expected ID and searching by name
            entity = session.get(Entity, expected_entity_id)
            if not entity:
                entity = session.scalar(
                    select(Entity).where(Entity.name == test_entity.name)
                )
            
            if entity:
                entity_id = entity.id
                # Delete all user links
                deleted_user_links = session.query(Entity_User_Link).filter_by(entity_id=entity_id).delete()
                print(f"Deleted {deleted_user_links} user links")
                
                # Delete all document links
                deleted_doc_links = session.query(Document_Entity_Link).filter_by(entity_id=entity_id).delete()
                print(f"Deleted {deleted_doc_links} document links")
                
                # Delete the entity
                session.delete(entity)
                print(f"Deleted entity: {entity.name} (ID: {entity.id})")
            else:
                print("No entity found to clean up")
            
            # Delete test documents
            doc1 = session.get(Document, test_doc_id_1)
            if doc1:
                session.delete(doc1)
                print(f"Deleted test document 1: {test_doc_id_1}")
            
            doc2 = session.get(Document, test_doc_id_2)
            if doc2:
                session.delete(doc2)
                print(f"Deleted test document 2: {test_doc_id_2}")
            
            # Delete test users
            user1 = session.get(User, test_user_id)
            if user1:
                session.delete(user1)
                print(f"Deleted test user 1: {test_user_id}")
            
            user2 = session.get(User, test_user_id_2)
            if user2:
                session.delete(user2)
                print(f"Deleted test user 2: {test_user_id_2}")
            
            session.commit()
            print("Test data cleanup completed") 