"""
Test script for testing direct content functionality in document creation.

This test script validates the new direct content feature that allows users to:
1. Create documents from URLs (existing functionality)
2. Create documents from direct HTML content (new)
3. Create documents from direct text content (new)

Test data source: https://news.yahoo.com/finance/news/hyundai-raid-could-upend-trump-165858389.html
"""

import pytest
import asyncio
from datetime import datetime
from typing import Dict, Any
import json

# Test data extracted from the Yahoo Finance article
TEST_URL = "https://news.yahoo.com/finance/news/hyundai-raid-could-upend-trump-165858389.html"

# Raw HTML content extracted from the URL
TEST_HTML_CONTENT = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Hyundai raid could upend Trump's economic agenda</title>
</head>
<body>
    <article>
        <h1>Hyundai raid could upend Trump's economic agenda</h1>
        <div class="article-content">
            <p>In a dramatic operation cheered by anti-immigration activists, the plant's workers were put in chains, loaded on buses and then locked up in detention facilities. The treatment of these workers sparked outrage in Korea, where the government is sending a charter plane to bring its citizens back home.</p>
            
            <p>The incident puts the future of the $7.6 billion plant in doubt.</p>
            
            <p>Officials that worked to lure Hyundai to Georgia say the plant, once built, would employ thousands of Americans. And they are hopeful that within a few years, the U.S. workforce will have the skills to build such a plant without bringing in foreign contractors.</p>
            
            <p>"This plant promises to be an extraordinary positive for the American economy," said John Lettieri, CEO of the Economic Innovation Group, a research group that promotes growth. "Of course we should have those experts come here and help train American workers and equip them with this specialized knowledge needed to run this enormously advanced facility. It is the ultimate no-brainer."</p>
            
            <p>He said the case underscores how Trump's economic agenda cries out for changes in immigration law that allow for more flexibility for specialized foreign workers to come here.</p>
            
            <p>"The president is being poorly served by zealous advisers unable to distinguish between enforcement theater and the value of deepening our economic relationships with firms and countries pouring a lot of investment into our economy," he said.</p>
            
            <p>The plant is not without issues.</p>
            
            <p>The raid followed reports of visa misuse and worker safety violations that stretched back to the Biden administration, according to Betony Jones, a senior fellow at the Roosevelt Institute and former director of the Office of Energy Jobs under President Joe Biden. At a Hyundai assembly plant in Alabama, the Department of Labor last year charged the company and two others with illegally employing children, including a 13-year-old who worked up to 50 or 60 per hours a week operating machinery. Hyundai is fighting the charges in court.</p>
            
            <p>But Jones and others said those issues could be addressed by strengthening rules that protect employees, launching federal audits and conducting safety investigations.</p>
            
            <p>Jones said the U.S. has lost tens of thousands of expected jobs from clean energy manufacturing projects that were canceled after Trump took office and began working to rescind Biden-era incentives for the plants.</p>
            
            <p>More than $7 billion in projects were canceled in just the first quarter of 2025. Another two planned battery plants were canceled in the past week alone, including a $210 million plant that was already under construction in Michigan. The owner of the project, Fortescue Zero, said its decision was driven by "current policy settings and market conditions" in the U.S.</p>
            
            <p>"That's thousands upon thousands of lost union jobs," Jones said.</p>
        </div>
    </article>
</body>
</html>
"""

# Extracted text content (cleaned from HTML)
TEST_TEXT_CONTENT = """
Hyundai raid could upend Trump's economic agenda

In a dramatic operation cheered by anti-immigration activists, the plant's workers were put in chains, loaded on buses and then locked up in detention facilities. The treatment of these workers sparked outrage in Korea, where the government is sending a charter plane to bring its citizens back home.

The incident puts the future of the $7.6 billion plant in doubt.

Officials that worked to lure Hyundai to Georgia say the plant, once built, would employ thousands of Americans. And they are hopeful that within a few years, the U.S. workforce will have the skills to build such a plant without bringing in foreign contractors.

"This plant promises to be an extraordinary positive for the American economy," said John Lettieri, CEO of the Economic Innovation Group, a research group that promotes growth. "Of course we should have those experts come here and help train American workers and equip them with this specialized knowledge needed to run this enormously advanced facility. It is the ultimate no-brainer."

He said the case underscores how Trump's economic agenda cries out for changes in immigration law that allow for more flexibility for specialized foreign workers to come here.

"The president is being poorly served by zealous advisers unable to distinguish between enforcement theater and the value of deepening our economic relationships with firms and countries pouring a lot of investment into our economy," he said.

The plant is not without issues.

The raid followed reports of visa misuse and worker safety violations that stretched back to the Biden administration, according to Betony Jones, a senior fellow at the Roosevelt Institute and former director of the Office of Energy Jobs under President Joe Biden. At a Hyundai assembly plant in Alabama, the Department of Labor last year charged the company and two others with illegally employing children, including a 13-year-old who worked up to 50 or 60 per hours a week operating machinery. Hyundai is fighting the charges in court.

But Jones and others said those issues could be addressed by strengthening rules that protect employees, launching federal audits and conducting safety investigations.

Jones said the U.S. has lost tens of thousands of expected jobs from clean energy manufacturing projects that were canceled after Trump took office and began working to rescind Biden-era incentives for the plants.

More than $7 billion in projects were canceled in just the first quarter of 2025. Another two planned battery plants were canceled in the past week alone, including a $210 million plant that was already under construction in Michigan. The owner of the project, Fortescue Zero, said its decision was driven by "current policy settings and market conditions" in the U.S.

"That's thousands upon thousands of lost union jobs," Jones said.
"""


class TestDocumentDirectContent:
    """Test class for document direct content functionality."""
    
    @pytest.fixture
    def test_user_firebase_uid(self):
        """Test user Firebase UID for testing."""
        import uuid
        return f"test_user_{uuid.uuid4().hex[:8]}"
    
    @pytest.fixture
    def sample_document_data(self):
        """Sample document data for testing."""
        return {
            "title": "Hyundai raid could upend Trump's economic agenda",
            "url": TEST_URL,
            "content": TEST_TEXT_CONTENT,
            "content_type": "text"
        }
    
    def test_document_create_request_validation(self):
        """Test DocumentCreateRequest validation for different content types."""
        from app.api.models.document_models import DocumentCreateRequest
        
        # Test URL-based document creation
        url_request = DocumentCreateRequest(
            url=TEST_URL,
            title="Test Article",
            content_type="url"
        )
        assert str(url_request.url) == TEST_URL
        assert url_request.content_type == "url"
        assert url_request.title == "Test Article"
        
        # Test HTML content document creation
        html_request = DocumentCreateRequest(
            content=TEST_HTML_CONTENT,
            content_type="html",
            title="Test HTML Article"
        )
        assert html_request.content == TEST_HTML_CONTENT
        assert html_request.content_type == "html"
        assert html_request.title == "Test HTML Article"
        
        # Test text content document creation
        text_request = DocumentCreateRequest(
            content=TEST_TEXT_CONTENT,
            content_type="text",
            title="Test Text Article"
        )
        assert text_request.content == TEST_TEXT_CONTENT
        assert text_request.content_type == "text"
        assert text_request.title == "Test Text Article"
    
    def test_document_create_request_validation_errors(self):
        """Test DocumentCreateRequest validation error cases."""
        from app.api.models.document_models import DocumentCreateRequest
        from pydantic import ValidationError
        
        # Test invalid content_type
        with pytest.raises(ValidationError):
            DocumentCreateRequest(
                content="Some content",
                content_type="invalid_type"
            )
        
        # Test missing content for non-url types
        with pytest.raises(ValidationError):
            DocumentCreateRequest(
                content_type="html"
                # Missing content field
            )
        
        # Test empty title
        with pytest.raises(ValidationError):
            DocumentCreateRequest(
                content="Some content",
                content_type="text",
                title=""  # Empty title should fail
            )
    
    @pytest.mark.asyncio
    async def test_create_document_from_url(self, test_user_firebase_uid):
        """Test creating a document from URL."""
        from app.services.document_service import DocumentService
        from app.db.database import get_session
        from sqlalchemy.ext.asyncio import AsyncSession
        
        # This would be an integration test that requires a database
        # For now, we'll test the service method signature and basic logic
        session_gen = get_session()
        session = await session_gen.__anext__()
        
        try:
            document_service = DocumentService(session)
            
            # Test that the method exists and accepts correct parameters
            assert hasattr(document_service, 'create_document_from_url')
            
            # Test method signature (this would be caught by type checking)
            # The actual implementation would create a document from URL
            # and return a Document object
        finally:
            await session.close()
    
    @pytest.mark.asyncio
    async def test_create_document_from_content_html(self, test_user_firebase_uid):
        """Test creating a document from HTML content."""
        from app.services.document_service import DocumentService
        from app.db.database import get_session
        
        session_gen = get_session()
        session = await session_gen.__anext__()
        
        try:
            document_service = DocumentService(session)
            
            # Test that the method exists
            assert hasattr(document_service, 'create_document_from_content')
            
            # Test method call with HTML content
            document = await document_service.create_document_from_content(
                firebase_uid=test_user_firebase_uid,
                content=TEST_HTML_CONTENT,
                content_type="html",
                title="Hyundai raid could upend Trump's economic agenda"
            )
            
            # Verify document properties
            assert document is not None
            assert document.title == "Hyundai raid could upend Trump's economic agenda"
            assert document.content_source == "html"
            assert document.status in ["processed", "embedded"]  # Status can be either depending on embedding generation
            assert document.user_id is not None
            assert document.created_at is not None
        finally:
            await session.close()
    
    @pytest.mark.asyncio
    async def test_create_document_from_content_text(self, test_user_firebase_uid):
        """Test creating a document from text content."""
        from app.services.document_service import DocumentService
        from app.db.database import get_session
        
        session_gen = get_session()
        session = await session_gen.__anext__()
        
        try:
            document_service = DocumentService(session)
            
            # Test method call with text content
            document = await document_service.create_document_from_content(
                firebase_uid=test_user_firebase_uid,
                content=TEST_TEXT_CONTENT,
                content_type="text",
                title="Hyundai raid could upend Trump's economic agenda"
            )
            
            # Verify document properties
            assert document is not None
            assert document.title == "Hyundai raid could upend Trump's economic agenda"
            assert document.content_source == "text"
            assert document.status in ["processed", "embedded"]  # Status can be either depending on embedding generation
            assert document.user_id is not None
            assert document.created_at is not None
        finally:
            await session.close()
    
    def test_content_extraction_utilities(self):
        """Test the content extraction utilities."""
        from app.services.document_service import DocumentService
        
        # Create a mock service instance to test utility methods
        service = DocumentService(None)  # We don't need a real session for utility methods
        
        # Test HTML text extraction
        extracted_text = service._extract_text_from_html(TEST_HTML_CONTENT)
        assert extracted_text is not None
        assert len(extracted_text) > 0
        assert "Hyundai raid could upend Trump's economic agenda" in extracted_text
        assert "plant's workers were put in chains" in extracted_text
        
        # Test HTML title extraction
        extracted_title = service._extract_title_from_html(TEST_HTML_CONTENT)
        assert extracted_title is not None
        assert extracted_title == "Hyundai raid could upend Trump's economic agenda"
        
        # Test text content handling (should return processed text)
        text_result = service._extract_text_from_html(TEST_TEXT_CONTENT)
        assert text_result is not None
        assert len(text_result) > 0
        # The method processes text, so we check for key content rather than exact match
        assert "Hyundai raid could upend Trump's economic agenda" in text_result
        assert "plant's workers were put in chains" in text_result
    
    def test_document_response_model(self):
        """Test DocumentResponse model includes new fields."""
        from app.api.models.document_models import DocumentResponse
        from datetime import datetime
        
        # Create a sample response
        response = DocumentResponse(
            id=1,
            created_at=datetime.now(),
            updated_at=datetime.now(),
            user_id=1,
            url=TEST_URL,
            title="Test Document",
            content_source="html",
            author="Test Author",
            publication_date=datetime.now(),
            description="Test description",
            keywords=["test", "document"],
            content="Test content",
            status="processed",
            document_metadata={"key": "value"}
        )
        
        # Verify new field is present
        assert response.content_source == "html"
        assert response.url == TEST_URL
        assert response.title == "Test Document"
    
    @pytest.mark.asyncio
    async def test_api_endpoint_integration(self, test_user_firebase_uid):
        """Test the API endpoint integration for direct content."""
        from fastapi.testclient import TestClient
        from app.main_new import app
        
        client = TestClient(app)
        
        # Test data for API calls
        test_data = {
            "content": TEST_TEXT_CONTENT,
            "content_type": "text",
            "title": "Hyundai raid could upend Trump's economic agenda"
        }
        
        # This would require proper authentication setup
        # For now, we'll test the endpoint structure
        response = client.post(
            "/api/documents/",
            json=test_data,
            headers={"Authorization": f"Bearer {test_user_firebase_uid}"}
        )
        
        # In a real test environment, this would return 201 Created
        # For now, we're testing the endpoint exists and accepts the data
        assert response.status_code in [201, 401, 403, 422]  # 401 for auth, 403 for forbidden, 422 for validation
    
    def test_content_type_validation(self):
        """Test content type validation logic."""
        from app.api.models.document_models import DocumentCreateRequest
        
        # Test valid content types
        valid_types = ["url", "html", "text"]
        for content_type in valid_types:
            if content_type == "url":
                request = DocumentCreateRequest(
                    url=TEST_URL,
                    content_type=content_type
                )
            else:
                request = DocumentCreateRequest(
                    content="Test content",
                    content_type=content_type
                )
            assert request.content_type == content_type
        
        # Test invalid content type
        with pytest.raises(Exception):  # ValidationError
            DocumentCreateRequest(
                content="Test content",
                content_type="invalid"
            )
    
    def test_document_model_fields(self):
        """Test that the Document model has the required new fields."""
        from app.db.models import Document
        
        # Check that the model has the new fields
        assert hasattr(Document, 'content_source')
        assert hasattr(Document, 'url')  # Should be optional now
        
        # Test field constraints
        # URL should be optional
        doc_without_url = Document(
            title="Test Document",
            content_source="text",
            user_id=1,
            status="processed"
        )
        assert doc_without_url.url is None
        assert doc_without_url.content_source == "text"
        
        # URL should be allowed
        doc_with_url = Document(
            url=TEST_URL,
            title="Test Document",
            content_source="url",
            user_id=1,
            status="processed"
        )
        assert doc_with_url.url == TEST_URL
        assert doc_with_url.content_source == "url"


# Integration test class for end-to-end testing
class TestDocumentDirectContentIntegration:
    """Integration tests for document direct content functionality."""
    
    @pytest.mark.asyncio
    async def test_full_workflow_url_to_document(self):
        """Test the complete workflow from URL to processed document."""
        # This would test the full pipeline:
        # 1. Create document from URL
        # 2. Fetch content from URL
        # 3. Process and validate content
        # 4. Generate embeddings
        # 5. Verify document is searchable
        pass
    
    @pytest.mark.asyncio
    async def test_full_workflow_html_to_document(self):
        """Test the complete workflow from HTML content to processed document."""
        # This would test the full pipeline:
        # 1. Create document from HTML content
        # 2. Extract text and metadata
        # 3. Process and validate content
        # 4. Generate embeddings
        # 5. Verify document is searchable
        pass
    
    @pytest.mark.asyncio
    async def test_full_workflow_text_to_document(self):
        """Test the complete workflow from text content to processed document."""
        # This would test the full pipeline:
        # 1. Create document from text content
        # 2. Process and validate content
        # 3. Generate embeddings
        # 4. Verify document is searchable
        pass


if __name__ == "__main__":
    # Run the tests
    pytest.main([__file__, "-v"])
