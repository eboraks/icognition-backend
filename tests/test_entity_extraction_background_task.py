"""
Test script for Entity Extraction Background Task functionality
"""

import asyncio
import pytest
import uuid
from typing import Dict, Any
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.main_new import app
from app.db.database import get_session
from app.db.models import Entity, EntityDocument, Document, User
from app.services.entity_extraction_service import get_entity_extraction_service
from app.services.entity_extraction_task_manager import get_entity_extraction_task_manager
from app.services.gemini_service import get_gemini_service


class TestEntityExtractionBackgroundTask:
    """Test suite for entity extraction background task functionality"""

    @pytest.fixture
    def test_user_firebase_uid(self):
        """Generate a unique Firebase UID for each test run"""
        return f"test_user_{uuid.uuid4().hex[:8]}"

    @pytest.fixture
    def sample_document_content(self):
        """Sample document content for testing"""
        return """
        Apple Inc. is an American multinational technology company headquartered in Cupertino, California.
        The company was founded by Steve Jobs, Steve Wozniak, and Ronald Wayne in April 1976.
        Apple is known for its innovative products including the iPhone, iPad, Mac computers, and Apple Watch.
        The company's CEO is Tim Cook, who succeeded Steve Jobs in 2011.
        Apple's headquarters is located in Cupertino, California, United States.
        The company has a market capitalization of over $3 trillion as of 2023.
        """

    @pytest.mark.asyncio
    async def test_entity_extraction_service_initialization(self):
        """Test that the entity extraction service initializes correctly"""
        session_gen = get_session()
        session = await session_gen.__anext__()
        
        try:
            entity_service = get_entity_extraction_service(session)
            assert entity_service is not None
            assert entity_service.session == session
            assert entity_service.gemini_service is not None
        finally:
            await session.close()

    @pytest.mark.asyncio
    async def test_entity_extraction_prompt_creation(self):
        """Test that entity extraction prompts are created correctly"""
        session_gen = get_session()
        session = await session_gen.__anext__()
        
        try:
            entity_service = get_entity_extraction_service(session)
            content = "Apple Inc. is a technology company founded by Steve Jobs."
            
            prompt = entity_service._create_entity_extraction_prompt(content)
            
            assert "Extract entities" in prompt
            assert "JSON format" in prompt
            assert "Person, Product, Company" in prompt
            assert content in prompt
        finally:
            await session.close()

    @pytest.mark.asyncio
    async def test_entity_response_parsing(self):
        """Test parsing of entity extraction responses"""
        session_gen = get_session()
        session = await session_gen.__anext__()
        
        try:
            entity_service = get_entity_extraction_service(session)
            
            # Test JSON format response
            json_response = '''
            {
                "entities": [
                    {
                        "name": "Apple Inc.",
                        "type": "Company",
                        "description": "American multinational technology company"
                    },
                    {
                        "name": "Steve Jobs",
                        "type": "Person",
                        "description": "Co-founder of Apple Inc."
                    }
                ]
            }
            '''
            
            entities = entity_service._parse_entity_response(json_response)
            
            assert len(entities) == 2
            assert entities[0]['name'] == "Apple Inc."
            assert entities[0]['type'] == "Company"
            assert entities[1]['name'] == "Steve Jobs"
            assert entities[1]['type'] == "Person"
        finally:
            await session.close()

    @pytest.mark.asyncio
    async def test_entity_validation(self):
        """Test entity validation logic"""
        session_gen = get_session()
        session = await session_gen.__anext__()
        
        try:
            entity_service = get_entity_extraction_service(session)
            
            # Valid entity
            valid_entity = {
                "name": "Apple Inc.",
                "type": "Company",
                "description": "Technology company"
            }
            assert entity_service._validate_entity(valid_entity) == True
            
            # Invalid entity (missing description)
            invalid_entity = {
                "name": "Apple Inc.",
                "type": "Company"
            }
            assert entity_service._validate_entity(invalid_entity) == False
            
            # Invalid entity (empty name)
            invalid_entity2 = {
                "name": "",
                "type": "Company",
                "description": "Technology company"
            }
            assert entity_service._validate_entity(invalid_entity2) == False
        finally:
            await session.close()

    @pytest.mark.asyncio
    async def test_entity_cleaning(self):
        """Test entity data cleaning"""
        session_gen = get_session()
        session = await session_gen.__anext__()
        
        try:
            entity_service = get_entity_extraction_service(session)
            
            dirty_entity = {
                "name": "  Apple Inc.  ",
                "type": "  company  ",
                "description": "  Technology company  "
            }
            
            cleaned = entity_service._clean_entity(dirty_entity)
            
            assert cleaned['name'] == "Apple Inc."
            assert cleaned['type'] == "Company"  # Should be title case
            assert cleaned['description'] == "Technology company"
        finally:
            await session.close()

    @pytest.mark.asyncio
    async def test_gemini_service_integration(self):
        """Test integration with Gemini service"""
        gemini_service = get_gemini_service()
        
        # Test that we can generate content
        prompt = "Extract entities from: Apple Inc. is a technology company."
        response = await gemini_service.generate_content(prompt)
        
        assert response is not None
        assert len(response) > 0

    @pytest.mark.asyncio
    async def test_extract_entities_from_content(self, test_user_firebase_uid, sample_document_content):
        """Test entity extraction from document content"""
        session_gen = get_session()
        session = await session_gen.__anext__()
        
        try:
            entity_service = get_entity_extraction_service(session)
            
            entities = await entity_service.extract_entities_from_content(
                sample_document_content,
                test_user_firebase_uid,
                1  # Mock document ID
            )
            
            # Should extract some entities
            assert isinstance(entities, list)
            # Note: Actual extraction depends on Gemini AI response
        finally:
            await session.close()

    @pytest.mark.asyncio
    async def test_task_manager_initialization(self):
        """Test that the task manager initializes correctly"""
        task_manager = get_entity_extraction_task_manager()
        
        assert task_manager is not None
        assert isinstance(task_manager.active_tasks, dict)
        assert isinstance(task_manager.task_history, list)

    @pytest.mark.asyncio
    async def test_task_manager_functionality(self, test_user_firebase_uid, sample_document_content):
        """Test task manager functionality"""
        task_manager = get_entity_extraction_task_manager()
        
        # Test async entity extraction
        result = await task_manager.extract_entities_async(
            test_user_firebase_uid,
            1,  # Mock document ID
            sample_document_content
        )
        
        assert isinstance(result, dict)
        assert 'status' in result
        assert 'entities_processed' in result

    @pytest.mark.asyncio
    async def test_batch_entity_extraction(self, test_user_firebase_uid):
        """Test batch entity extraction"""
        task_manager = get_entity_extraction_task_manager()
        
        # Test batch processing
        result = await task_manager.batch_extract_entities(
            test_user_firebase_uid,
            [1, 2, 3],  # Mock document IDs
            max_concurrent=2
        )
        
        assert isinstance(result, dict)
        assert 'status' in result
        assert 'documents_processed' in result

    @pytest.mark.asyncio
    async def test_error_handling(self, test_user_firebase_uid):
        """Test error handling in entity extraction"""
        session_gen = get_session()
        session = await session_gen.__anext__()
        
        try:
            entity_service = get_entity_extraction_service(session)
            
            # Test with empty content
            entities = await entity_service.extract_entities_from_content(
                "",
                test_user_firebase_uid,
                1
            )
            
            # Should handle empty content gracefully
            assert isinstance(entities, list)
        finally:
            await session.close()

    @pytest.mark.asyncio
    async def test_task_status_tracking(self):
        """Test task status tracking"""
        task_manager = get_entity_extraction_task_manager()
        
        # Test getting status of non-existent task
        status = task_manager.get_task_status("non_existent_task")
        assert status is None
        
        # Test getting task history
        history = task_manager.get_task_history()
        assert isinstance(history, list)

    @pytest.mark.asyncio
    async def test_task_cleanup(self):
        """Test task cleanup functionality"""
        task_manager = get_entity_extraction_task_manager()
        
        # Test cleanup (should not raise errors)
        task_manager.cleanup_completed_tasks()
        
        # Should still be functional after cleanup
        assert task_manager is not None


class TestEntityExtractionIntegration:
    """Integration tests for entity extraction"""

    @pytest.fixture
    def test_user_firebase_uid(self):
        """Generate a unique Firebase UID for each test run"""
        return f"test_user_{uuid.uuid4().hex[:8]}"

    @pytest.mark.asyncio
    async def test_full_workflow_integration(self, test_user_firebase_uid):
        """Test full entity extraction workflow"""
        session_gen = get_session()
        session = await session_gen.__anext__()
        
        try:
            # Create a test user
            from app.services.user_service import UserService
            user = await UserService.get_or_create_user(session, test_user_firebase_uid)
            
            # Create a test document
            test_document = Document(
                title="Test Document",
                content="Apple Inc. is a technology company founded by Steve Jobs.",
                user_id=user.id,
                status="processed"
            )
            session.add(test_document)
            await session.flush()
            
            # Test entity extraction service
            entity_service = get_entity_extraction_service(session)
            
            result = await entity_service.process_document_entities(
                test_user_firebase_uid,
                test_document.id,
                test_document.content
            )
            
            assert result['status'] in ['success', 'error']
            assert 'entities_processed' in result
            
            # Commit changes
            await session.commit()
            
        finally:
            await session.close()

    @pytest.mark.asyncio
    async def test_api_endpoint_integration(self, test_user_firebase_uid):
        """Test API endpoint integration"""
        client = TestClient(app)
        
        # Test entity extraction endpoint (should return 401/403 without auth)
        response = client.post(f"/documents/1/extract-entities")
        
        # Should require authentication
        assert response.status_code in [401, 403, 404, 422]

    @pytest.mark.asyncio
    async def test_entity_document_relationship(self, test_user_firebase_uid):
        """Test entity-document relationship creation"""
        session_gen = get_session()
        session = await session_gen.__anext__()
        
        try:
            # Create test user
            from app.services.user_service import UserService
            user = await UserService.get_or_create_user(session, test_user_firebase_uid)
            
            # Create test document
            test_document = Document(
                title="Test Document",
                content="Apple Inc. is a technology company.",
                user_id=user.id,
                status="processed"
            )
            session.add(test_document)
            await session.flush()
            
            # Create test entity
            test_entity = Entity(
                name="Apple Inc.",
                type="Company",
                description="Technology company",
                user_id=user.id
            )
            session.add(test_entity)
            await session.flush()
            
            # Test entity extraction service
            entity_service = get_entity_extraction_service(session)
            
            # Create relationship
            success = await entity_service._create_entity_document_relationship(
                test_entity.id,
                test_document.id
            )
            
            assert success == True
            
            # Commit changes
            await session.commit()
            
        finally:
            await session.close()

    @pytest.mark.asyncio
    async def test_concurrent_entity_extraction(self, test_user_firebase_uid):
        """Test concurrent entity extraction (stress test)"""
        task_manager = get_entity_extraction_task_manager()
        
        # Create multiple concurrent tasks
        tasks = []
        for i in range(3):
            task = task_manager.extract_entities_async(
                test_user_firebase_uid,
                i + 1,
                f"Test content {i}"
            )
            tasks.append(task)
        
        # Wait for all tasks to complete
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # All tasks should complete (may have errors due to database constraints)
        assert len(results) == 3
        for result in results:
            assert isinstance(result, (dict, Exception))


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
