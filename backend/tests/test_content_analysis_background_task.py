"""
Test script for Content Analysis Background Task functionality
"""

import asyncio
import pytest
import uuid
from typing import Dict, Any
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.main_new import app
from app.db.database import get_session
from app.models import Document, User
from app.services.content_analysis_service import get_content_analysis_service
from app.services.content_analysis_task_manager import get_content_analysis_task_manager
from app.services.gemini_service import get_gemini_service


class TestContentAnalysisBackgroundTask:
    """Test suite for content analysis background task functionality"""

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
    async def test_content_analysis_service_initialization(self):
        """Test that the content analysis service can be initialized"""
        session_gen = get_session()
        session = await session_gen.__anext__()
        
        try:
            analysis_service = get_content_analysis_service(session)
            assert analysis_service is not None
            assert analysis_service.gemini_service is not None
        finally:
            await session.close()

    @pytest.mark.asyncio
    async def test_generate_bullet_points(self, test_user_firebase_uid, sample_document_content):
        """Test bullet point generation from document content"""
        session_gen = get_session()
        session = await session_gen.__anext__()
        
        try:
            # Create a test document
            from app.services.document_service import DocumentService
            document_service = DocumentService(session)
            
            document = await document_service.create_document_from_content(
                firebase_uid=test_user_firebase_uid,
                content=sample_document_content,
                content_type="text",
                title="AI and ML Overview"
            )
            
            # Test bullet point generation
            analysis_service = get_content_analysis_service(session)
            result = await analysis_service._generate_bullet_points(sample_document_content)
            
            assert result is not None
            assert result['success'] is True
            assert 'bullet_points' in result
            assert isinstance(result['bullet_points'], list)
            assert len(result['bullet_points']) <= 6  # Should not exceed 6 bullet points
            assert len(result['bullet_points']) > 0   # Should have at least some bullet points
            
            # Verify bullet points contain meaningful content
            for bullet_point in result['bullet_points']:
                assert isinstance(bullet_point, str)
                assert len(bullet_point.strip()) > 5  # Should be meaningful length
                
        finally:
            await session.close()

    @pytest.mark.asyncio
    async def test_analyze_document_content(self, test_user_firebase_uid, sample_document_content):
        """Test full document content analysis workflow"""
        session_gen = get_session()
        session = await session_gen.__anext__()
        
        try:
            # Create a test document
            from app.services.document_service import DocumentService
            document_service = DocumentService(session)
            
            document = await document_service.create_document_from_content(
                firebase_uid=test_user_firebase_uid,
                content=sample_document_content,
                content_type="text",
                title="AI and ML Overview"
            )
            
            # Test content analysis
            analysis_service = get_content_analysis_service(session)
            result = await analysis_service.analyze_document_content(
                firebase_uid=test_user_firebase_uid,
                document_id=document.id,
                analysis_type="bullet_points"
            )
            
            assert result is not None
            assert result.status == "analyzed"
            assert result.document_metadata is not None
            assert 'content_analysis' in result.document_metadata
            
            analysis_data = result.document_metadata['content_analysis']
            assert analysis_data['success'] is True
            assert 'bullet_points' in analysis_data
            assert len(analysis_data['bullet_points']) > 0
            
        finally:
            await session.close()

    @pytest.mark.asyncio
    async def test_task_manager_functionality(self, test_user_firebase_uid, sample_document_content):
        """Test the background task manager"""
        session_gen = get_session()
        session = await session_gen.__anext__()
        
        try:
            # Create a test document
            from app.services.document_service import DocumentService
            document_service = DocumentService(session)
            
            document = await document_service.create_document_from_content(
                firebase_uid=test_user_firebase_uid,
                content=sample_document_content,
                content_type="text",
                title="AI and ML Overview"
            )
            
            # Test task manager
            task_manager = get_content_analysis_task_manager()
            
            # Start analysis task
            result = await task_manager.analyze_document_async(
                firebase_uid=test_user_firebase_uid,
                document_id=document.id,
                analysis_type="bullet_points"
            )
            
            assert result['status'] == 'started'
            assert 'task_id' in result
            
            # Wait for task to complete (with timeout)
            task_id = result['task_id']
            max_wait_time = 30  # seconds
            wait_time = 0
            
            while wait_time < max_wait_time:
                task_status = task_manager.get_task_status(task_id)
                if task_status and task_status.get('status') in ['completed', 'failed']:
                    break
                await asyncio.sleep(1)
                wait_time += 1
            
            # Verify task completed
            final_status = task_manager.get_task_status(task_id)
            assert final_status is not None
            assert final_status['status'] in ['completed', 'failed']
            
        finally:
            await session.close()

    @pytest.mark.asyncio
    async def test_batch_analysis(self, test_user_firebase_uid):
        """Test batch analysis functionality"""
        session_gen = get_session()
        session = await session_gen.__anext__()
        
        try:
            # Create multiple test documents
            from app.services.document_service import DocumentService
            document_service = DocumentService(session)
            
            documents = []
            for i in range(3):
                document = await document_service.create_document_from_content(
                    firebase_uid=test_user_firebase_uid,
                    content=f"Test content for document {i+1}. This is sample text for analysis.",
                    content_type="text",
                    title=f"Test Document {i+1}"
                )
                documents.append(document)
            
            # Test batch analysis
            analysis_service = get_content_analysis_service(session)
            document_ids = [doc.id for doc in documents]
            
            result = await analysis_service.batch_analyze_documents(
                firebase_uid=test_user_firebase_uid,
                document_ids=document_ids,
                analysis_type="bullet_points"
            )
            
            assert result['total_documents'] == 3
            assert result['successful_analyses'] + result['failed_analyses'] == 3
            assert len(result['results']) == 3
            
        finally:
            await session.close()

    @pytest.mark.asyncio
    async def test_error_handling(self, test_user_firebase_uid):
        """Test error handling in content analysis"""
        session_gen = get_session()
        session = await session_gen.__anext__()
        
        try:
            # Test with non-existent document
            analysis_service = get_content_analysis_service(session)
            result = await analysis_service.analyze_document_content(
                firebase_uid=test_user_firebase_uid,
                document_id=99999,  # Non-existent ID
                analysis_type="bullet_points"
            )
            
            assert result is None
            
            # Test with document that has no content
            from app.services.document_service import DocumentService
            document_service = DocumentService(session)
            
            document = await document_service.create_document_from_content(
                firebase_uid=test_user_firebase_uid,
                content="",  # Empty content
                content_type="text",
                title="Empty Document"
            )
            
            result = await analysis_service.analyze_document_content(
                firebase_uid=test_user_firebase_uid,
                document_id=document.id,
                analysis_type="bullet_points"
            )
            
            assert result is not None
            assert result.status == "analysis_failed"
            assert result.document_metadata is not None
            assert 'analysis_error' in result.document_metadata
            
        finally:
            await session.close()

    def test_api_endpoints(self, test_user_firebase_uid, sample_document_content):
        """Test the API endpoints for content analysis"""
        client = TestClient(app)
        
        # Create a test document first
        response = client.post(
            "/api/documents/",
            json={
                "content": sample_document_content,
                "content_type": "text",
                "title": "AI and ML Overview"
            },
            headers={"Authorization": f"Bearer {test_user_firebase_uid}"}
        )
        
        if response.status_code == 201:
            document_data = response.json()
            document_id = document_data["id"]
            
            # Test analyze endpoint
            analyze_response = client.post(
                f"/api/documents/{document_id}/analyze",
                params={"analysis_type": "bullet_points"},
                headers={"Authorization": f"Bearer {test_user_firebase_uid}"}
            )
            
            assert analyze_response.status_code in [200, 201]
            analyze_data = analyze_response.json()
            assert "task_id" in analyze_data
            assert "status" in analyze_data
            
            # Test analysis report endpoint (may not have data yet)
            report_response = client.get(
                f"/api/documents/{document_id}/analysis-report",
                headers={"Authorization": f"Bearer {test_user_firebase_uid}"}
            )
            
            # Should either return report or 404 if not analyzed yet
            assert report_response.status_code in [200, 404]
            
            # Test batch analyze endpoint
            batch_response = client.post(
                "/api/documents/batch/analyze",
                params={"analysis_type": "bullet_points"},
                headers={"Authorization": f"Bearer {test_user_firebase_uid}"}
            )
            
            assert batch_response.status_code in [200, 201]
            batch_data = batch_response.json()
            assert "task_id" in batch_data
            
            # Test analysis tasks endpoint
            tasks_response = client.get(
                "/api/documents/analysis/tasks",
                headers={"Authorization": f"Bearer {test_user_firebase_uid}"}
            )
            
            assert tasks_response.status_code == 200
            tasks_data = tasks_response.json()
            assert "tasks" in tasks_data
            assert "total" in tasks_data
            
            # Test analysis statistics endpoint
            stats_response = client.get(
                "/api/documents/analysis/statistics",
                headers={"Authorization": f"Bearer {test_user_firebase_uid}"}
            )
            
            assert stats_response.status_code == 200
            stats_data = stats_response.json()
            assert "total_tasks" in stats_data
            assert "active_tasks" in stats_data

    def test_gemini_service_integration(self):
        """Test Gemini service integration"""
        gemini_service = get_gemini_service()
        assert gemini_service is not None
        
        # Test that we can generate content (will use mock mode if no API key)
        import asyncio
        
        async def test_generation():
            result = await gemini_service.generate_content(
                prompt="Generate 3 bullet points about artificial intelligence",
                retry_count=1
            )
            assert result is not None
            assert 'content' in result
            assert result['success'] is True
        
        asyncio.run(test_generation())

    def test_bullet_point_parsing(self):
        """Test bullet point parsing functionality"""
        from app.services.content_analysis_service import ContentAnalysisService
        from sqlalchemy.ext.asyncio import AsyncSession
        
        # Create a mock session for testing
        class MockSession:
            pass
        
        service = ContentAnalysisService(MockSession())
        
        # Test JSON parsing
        json_response = '{"bullet_points": ["Point 1", "Point 2", "Point 3"]}'
        result = service._parse_bullet_points_response(json_response)
        assert result == ["Point 1", "Point 2", "Point 3"]
        
        # Test text parsing with bullet points
        text_response = """• First important point
        • Second important point
        • Third important point"""
        result = service._parse_bullet_points_response(text_response)
        assert len(result) == 3
        assert "First important point" in result[0]
        
        # Test numbered list parsing
        numbered_response = """1. First point
        2. Second point
        3. Third point"""
        result = service._parse_bullet_points_response(numbered_response)
        assert len(result) == 3
        assert "First point" in result[0]


class TestContentAnalysisIntegration:
    """Integration tests for content analysis functionality"""

    @pytest.mark.asyncio
    async def test_full_workflow_integration(self):
        """Test the complete workflow from document creation to analysis"""
        test_user_firebase_uid = f"test_user_{uuid.uuid4().hex[:8]}"
        
        session_gen = get_session()
        session = await session_gen.__anext__()
        
        try:
            # Step 1: Create document
            from app.services.document_service import DocumentService
            document_service = DocumentService(session)
            
            sample_content = """
            Machine Learning Fundamentals
            
            Machine learning is a subset of artificial intelligence that focuses on algorithms 
            that can learn from data. There are three main types of machine learning:
            
            1. Supervised Learning: Uses labeled training data to learn patterns
            2. Unsupervised Learning: Finds patterns in data without labels
            3. Reinforcement Learning: Learns through interaction with an environment
            
            Key concepts include feature engineering, model selection, and evaluation metrics.
            """
            
            document = await document_service.create_document_from_content(
                firebase_uid=test_user_firebase_uid,
                content=sample_content,
                content_type="text",
                title="ML Fundamentals"
            )
            
            assert document.status in ["processed", "embedded"]
            
            # Step 2: Analyze document content
            analysis_service = get_content_analysis_service(session)
            analyzed_document = await analysis_service.analyze_document_content(
                firebase_uid=test_user_firebase_uid,
                document_id=document.id,
                analysis_type="bullet_points"
            )
            
            assert analyzed_document is not None
            assert analyzed_document.status == "analyzed"
            assert analyzed_document.document_metadata is not None
            assert 'content_analysis' in analyzed_document.document_metadata
            
            analysis_data = analyzed_document.document_metadata['content_analysis']
            assert analysis_data['success'] is True
            assert 'bullet_points' in analysis_data
            assert len(analysis_data['bullet_points']) > 0
            
            # Step 3: Verify bullet points are meaningful
            bullet_points = analysis_data['bullet_points']
            for point in bullet_points:
                assert isinstance(point, str)
                assert len(point.strip()) > 10  # Should be substantial
                
            print(f"Generated {len(bullet_points)} bullet points:")
            for i, point in enumerate(bullet_points, 1):
                print(f"{i}. {point}")
                
        finally:
            await session.close()

    @pytest.mark.asyncio
    async def test_concurrent_analysis(self):
        """Test concurrent analysis of multiple documents"""
        test_user_firebase_uid = f"test_user_{uuid.uuid4().hex[:8]}"
        
        session_gen = get_session()
        session = await session_gen.__anext__()
        
        try:
            # Create multiple documents
            from app.services.document_service import DocumentService
            document_service = DocumentService(session)
            
            documents = []
            for i in range(5):
                document = await document_service.create_document_from_content(
                    firebase_uid=test_user_firebase_uid,
                    content=f"Document {i+1} content about technology and innovation. This document contains information about various technological advances and their impact on society.",
                    content_type="text",
                    title=f"Tech Document {i+1}"
                )
                documents.append(document)
            
            # Start concurrent analysis tasks
            analysis_service = get_content_analysis_service(session)
            tasks = []
            
            for document in documents:
                task = analysis_service.analyze_document_content(
                    firebase_uid=test_user_firebase_uid,
                    document_id=document.id,
                    analysis_type="bullet_points"
                )
                tasks.append(task)
            
            # Wait for all tasks to complete
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Verify results
            successful_analyses = 0
            for result in results:
                if isinstance(result, Exception):
                    print(f"Analysis failed with exception: {result}")
                elif result and result.status == "analyzed":
                    successful_analyses += 1
            
            print(f"Successfully analyzed {successful_analyses} out of {len(documents)} documents")
            assert successful_analyses > 0  # At least some should succeed
            
        finally:
            await session.close()


if __name__ == "__main__":
    # Run the tests
    pytest.main([__file__, "-v"])
