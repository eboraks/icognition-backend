"""
Integration tests for DSPy content and entity services
Tests the new DSPy services in realistic scenarios
"""

import asyncio
import pytest
import uuid
from typing import Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_session
from app.models import Document, Entity, EntityDocument
from app.services.dspy_content_service import get_dspy_content_service
from app.services.dspy_entity_service import get_dspy_entity_service
from app.services.dspy_entity_adapter import DspyEntityAdapter
from app.services.document_service import DocumentService


class TestDspyContentService:
    """Test suite for DSPy content service"""

    @pytest.fixture
    def test_user_firebase_uid(self):
        """Generate a unique Firebase UID for each test run"""
        return f"test_user_{uuid.uuid4().hex[:8]}"

    @pytest.fixture
    def sample_document_content(self):
        """Sample document content for testing"""
        return """
        Artificial Intelligence and Machine Learning
        
        Artificial Intelligence (AI) and Machine Learning (ML) are rapidly transforming the technology landscape. 
        AI refers to the simulation of human intelligence in machines, while ML is a subset of AI that enables 
        computers to learn and improve from experience without being explicitly programmed.
        
        Key Applications:
        - Healthcare: AI is revolutionizing medical diagnosis and treatment planning
        - Finance: Machine learning algorithms are used for fraud detection and risk assessment
        - Transportation: Autonomous vehicles rely heavily on AI and ML technologies
        - Education: Personalized learning experiences are being created using AI
        - Manufacturing: Predictive maintenance and quality control are improved through ML
        
        Challenges and Considerations:
        The rapid advancement of AI brings both opportunities and challenges. Ethical considerations around 
        bias, privacy, and job displacement are critical areas that need attention. Additionally, the need 
        for robust data governance and algorithmic transparency is becoming increasingly important.
        
        Future Outlook:
        As AI and ML technologies continue to evolve, we can expect to see more sophisticated applications 
        across various industries. The integration of AI with other emerging technologies like IoT and 
        blockchain will likely create new possibilities and transform existing business models.
        """

    @pytest.mark.asyncio
    async def test_content_service_initialization(self):
        """Test that the DSPy content service can be initialized"""
        service = get_dspy_content_service()
        assert service is not None
        assert service.api_key is not None

    @pytest.mark.asyncio
    async def test_analyze_document_content(self, sample_document_content):
        """Test document content analysis with DSPy"""
        service = get_dspy_content_service()
        
        result = await service.analyze_document_content(
            content=sample_document_content,
            title="AI and ML Overview",
            url="https://example.com/ai-ml"
        )
        
        # Verify result structure
        assert result is not None
        assert 'summary' in result
        assert 'markdown_content' in result
        assert 'extracted_content' in result
        
        # Verify content quality
        assert len(result['summary']) > 50
        assert isinstance(result['markdown_content'], str)
        assert len(result['markdown_content']) > 50
        
        # Verify extracted_content structure
        ec = result['extracted_content']
        assert 'title' in ec
        assert 'source_type' in ec
        assert 'summary' in ec
        assert 'markdown_content' in ec
        assert 'analysis' in ec
        assert 'objectivity' in ec['analysis']
        assert 'tone' in ec['analysis']
        assert 'intent' in ec['analysis']
        
        print(f"\n✓ Content analysis successful")
        print(f"  Summary: {result['summary'][:100]}...")
        print(f"  Markdown content length: {len(result['markdown_content'])}")
        print(f"  Source type: {ec['source_type']}")


class TestDspyEntityService:
    """Test suite for DSPy entity service"""

    @pytest.fixture
    def test_user_firebase_uid(self):
        """Generate a unique Firebase UID for each test run"""
        return f"test_user_{uuid.uuid4().hex[:8]}"

    @pytest.fixture
    def sample_document_content(self):
        """Sample document content for testing"""
        return """
        SpaceX Successfully Launches Starship Super Heavy Rocket
        
        SpaceX's Starship Super Heavy rocket successfully completed its fifth test flight from 
        Starbase in Boca Chica, Texas, marking a significant milestone for Elon Musk's company. 
        The 400-foot tall rocket lifted off at dawn, with both stages performing as expected.
        
        The mission demonstrated several key capabilities including:
        - Successful stage separation at 40 miles altitude
        - Starship upper stage reaching orbital velocity
        - Controlled water landing in the Gulf of Mexico
        - Recovery of the Super Heavy booster using innovative "chopstick" catch mechanism
        
        NASA Administrator Bill Nelson congratulated the SpaceX team, noting that this success 
        brings the Artemis Moon program one step closer to reality. The space agency has contracted 
        SpaceX to provide lunar lander services for upcoming Artemis missions.
        
        Industry experts from Blue Origin and United Launch Alliance have acknowledged this as 
        a major achievement for commercial spaceflight, despite being competitors in the space industry.
        """

    @pytest.mark.asyncio
    async def test_entity_service_initialization(self):
        """Test that the DSPy entity service can be initialized"""
        service = get_dspy_entity_service()
        assert service is not None
        assert service.api_key is not None

    @pytest.mark.asyncio
    async def test_extract_entities_from_content(self, sample_document_content):
        """Test entity extraction with DSPy"""
        service = get_dspy_entity_service()
        
        entities = await service.extract_entities_from_content(
            content=sample_document_content,
            document_id=1
        )
        
        # Verify entities extracted
        assert entities is not None
        assert isinstance(entities, list)
        assert len(entities) >= 5  # Should extract meaningful entities
        assert len(entities) <= 15  # Should not exceed limit
        
        # Verify entity structure
        for entity in entities:
            assert 'name' in entity
            assert 'type' in entity
            assert 'description' in entity
            assert len(entity['name']) > 0
            assert len(entity['description']) > 0
        
        print(f"\n✓ Entity extraction successful")
        print(f"  Extracted {len(entities)} entities")
        for i, entity in enumerate(entities[:5], 1):
            print(f"  {i}. {entity['name']} ({entity['type']})")

    @pytest.mark.asyncio
    async def test_entity_adapter(self, test_user_firebase_uid, sample_document_content):
        """Test entity adapter for database storage"""
        session_gen = get_session()
        session = await session_gen.__anext__()
        
        try:
            # Create a test document
            document_service = DocumentService(session)
            document = await document_service.create_document_from_content(
                user_id=test_user_firebase_uid,
                content=sample_document_content,
                content_type="text",
                title="SpaceX Test Flight"
            )
            
            # Extract entities
            entity_service = get_dspy_entity_service()
            entities = await entity_service.extract_entities_from_content(
                content=sample_document_content,
                document_id=document.id
            )
            
            # Test adapter
            adapter = DspyEntityAdapter(session)
            result = await adapter.process_document_entities(
                firebase_uid=test_user_firebase_uid,
                document_id=document.id,
                entities=entities
            )
            
            # Commit to test database operations
            await session.commit()
            
            # Verify result
            assert result['status'] == 'success'
            assert result['entities_processed'] > 0
            assert result['entities_processed'] <= len(entities)
            
            print(f"\n✓ Entity adapter test successful")
            print(f"  Processed: {result['entities_processed']}/{result['entities_extracted']} entities")
            
        finally:
            await session.close()


class TestDspyIntegration:
    """Integration tests for complete DSPy workflow"""

    @pytest.mark.asyncio
    async def test_full_document_processing(self):
        """Test complete document processing with both services"""
        test_user_firebase_uid = f"test_user_{uuid.uuid4().hex[:8]}"
        
        session_gen = get_session()
        session = await session_gen.__anext__()
        
        try:
            # Create document
            document_service = DocumentService(session)
            content = """
            Google Announces Gemini 2.0 AI Model
            
            Google has unveiled Gemini 2.0, its most advanced AI model to date, at the Google I/O 
            conference in Mountain View, California. The new model shows significant improvements 
            in reasoning, coding, and multimodal understanding compared to its predecessor.
            
            Key features include enhanced performance on mathematical reasoning benchmarks, improved 
            code generation capabilities, and better understanding of images, audio, and video content.
            
            CEO Sundar Pichai emphasized Google's commitment to responsible AI development and 
            announced partnerships with several universities for AI safety research.
            """
            
            document = await document_service.create_document_from_content(
                user_id=test_user_firebase_uid,
                content=content,
                content_type="text",
                title="Google Gemini 2.0 Announcement"
            )
            
            # Test content analysis
            content_service = get_dspy_content_service()
            content_result = await content_service.analyze_document_content(
                content=content,
                title=document.title,
                url=document.url
            )
            
            # Update document with content analysis
            document.ai_is_about = content_result['summary']
            document.ai_markdown_content = content_result['markdown_content']
            document.extracted_content = content_result['extracted_content']
            document.source_type = content_result['extracted_content']['source_type']
            
            # Test entity extraction
            entity_service = get_dspy_entity_service()
            entities = await entity_service.extract_entities_from_content(
                content=content,
                document_id=document.id
            )
            
            # Store entities
            adapter = DspyEntityAdapter(session)
            entity_result = await adapter.process_document_entities(
                firebase_uid=test_user_firebase_uid,
                document_id=document.id,
                entities=entities
            )
            
            await session.commit()
            
            # Verify complete processing
            assert document.ai_is_about is not None
            assert len(document.ai_markdown_content) > 0
            assert document.extracted_content is not None
            assert entity_result['entities_processed'] > 0
            
            print(f"\n✓ Full document processing successful")
            print(f"  Summary: {document.ai_is_about[:100]}...")
            print(f"  Markdown length: {len(document.ai_markdown_content)}")
            print(f"  Entities: {entity_result['entities_processed']}")
            print(f"  Source type: {document.source_type}")
            
        finally:
            await session.close()


if __name__ == "__main__":
    # Run the tests
    pytest.main([__file__, "-v"])

