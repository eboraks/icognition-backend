"""
Integration tests for the API endpoints
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from app.main import app
from app.models import User, Document, Bookmark
from datetime import datetime

client = TestClient(app)


class TestIntegration:
    """Integration tests for API endpoints"""

    @pytest.fixture
    def mock_user(self):
        """Mock user for integration testing"""
        return User(
            id="integration-test-uid",
            email="integration@example.com",
            display_name="Integration Test User",
            is_active=True,
            is_verified=True
        )

    @pytest.fixture
    def mock_user_context(self, mock_user):
        """Mock user context for integration testing"""
        from app.core.user_context import UserContext
        return UserContext(user=mock_user)

    @patch('app.core.user_context.get_authenticated_user_context')
    @patch('app.services.document_service.DocumentService.create_document')
    @patch('app.services.bookmark_service.BookmarkService.create_bookmark')
    def test_document_to_bookmark_workflow(self, mock_create_bookmark, mock_create_doc, mock_get_user, mock_user_context):
        """Test the complete workflow from document creation to bookmark creation"""
        # Arrange
        mock_get_user.return_value = mock_user_context
        
        # Mock document creation
        mock_doc = Document(
            id="doc-integration-123",
            title="Integration Test Document",
            url="https://example.com/integration",
            content="Integration test content",
            status="processed",
            user_id="integration-test-uid"
        )
        mock_create_doc.return_value = mock_doc
        
        # Mock bookmark creation
        mock_bookmark = Bookmark(
            id="bookmark-integration-123",
            url="https://example.com/integration",
            title="Integration Test Bookmark",
            description="Integration test description",
            user_id="integration-test-uid",
            is_processed=True,
            processing_status="completed"
        )
        mock_create_bookmark.return_value = mock_bookmark
        
        # Act - Create document
        doc_response = client.post("/documents/", json={
            "url": "https://example.com/integration",
            "title": "Integration Test Document",
            "content_type": "url"
        })
        
        # Act - Create bookmark
        bookmark_response = client.post("/bookmarks/", json={
            "url": "https://example.com/integration",
            "title": "Integration Test Bookmark",
            "description": "Integration test description"
        })
        
        # Assert
        assert doc_response.status_code == 201
        assert bookmark_response.status_code == 201
        
        doc_data = doc_response.json()
        bookmark_data = bookmark_response.json()
        
        assert doc_data["id"] == "doc-integration-123"
        assert bookmark_data["id"] == "bookmark-integration-123"
        assert doc_data["url"] == bookmark_data["url"]

    @patch('app.core.user_context.get_authenticated_user_context')
    @patch('app.services.document_service.DocumentService.get_user_documents')
    @patch('app.services.bookmark_service.BookmarkService.get_user_bookmarks')
    def test_user_data_consistency(self, mock_get_bookmarks, mock_get_docs, mock_get_user, mock_user_context):
        """Test that user data is consistent across different endpoints"""
        # Arrange
        mock_get_user.return_value = mock_user_context
        
        # Mock documents
        mock_docs = [
            Document(
                id="doc-1",
                title="Document 1",
                url="https://example.com/doc1",
                user_id="integration-test-uid"
            ),
            Document(
                id="doc-2",
                title="Document 2",
                url="https://example.com/doc2",
                user_id="integration-test-uid"
            )
        ]
        mock_get_docs.return_value = (mock_docs, 2)
        
        # Mock bookmarks
        mock_bookmarks = [
            Bookmark(
                id="bookmark-1",
                title="Bookmark 1",
                url="https://example.com/bookmark1",
                user_id="integration-test-uid"
            )
        ]
        mock_get_bookmarks.return_value = (mock_bookmarks, 1)
        
        # Act
        docs_response = client.get("/documents/")
        bookmarks_response = client.get("/bookmarks/")
        
        # Assert
        assert docs_response.status_code == 200
        assert bookmarks_response.status_code == 200
        
        docs_data = docs_response.json()
        bookmarks_data = bookmarks_response.json()
        
        assert docs_data["total"] == 2
        assert bookmarks_data["total"] == 1
        
        # Check that all documents belong to the same user
        for doc in docs_data["documents"]:
            assert doc["user_id"] == "integration-test-uid"
        
        # Check that all bookmarks belong to the same user
        for bookmark in bookmarks_data["bookmarks"]:
            assert bookmark["user_id"] == "integration-test-uid"

    @patch('app.core.user_context.get_authenticated_user_context')
    @patch('app.services.document_service.DocumentService.get_by_id')
    @patch('app.services.bookmark_service.BookmarkService.get_by_id')
    def test_cross_reference_consistency(self, mock_get_bookmark, mock_get_doc, mock_get_user, mock_user_context):
        """Test that document and bookmark data can be cross-referenced consistently"""
        # Arrange
        mock_get_user.return_value = mock_user_context
        
        # Mock document
        mock_doc = Document(
            id="cross-ref-doc",
            title="Cross Reference Document",
            url="https://example.com/crossref",
            content="Cross reference content",
            user_id="integration-test-uid"
        )
        mock_get_doc.return_value = mock_doc
        
        # Mock bookmark
        mock_bookmark = Bookmark(
            id="cross-ref-bookmark",
            title="Cross Reference Bookmark",
            url="https://example.com/crossref",
            user_id="integration-test-uid"
        )
        mock_get_bookmark.return_value = mock_bookmark
        
        # Act
        doc_response = client.get("/documents/cross-ref-doc")
        bookmark_response = client.get("/bookmarks/cross-ref-bookmark")
        
        # Assert
        assert doc_response.status_code == 200
        assert bookmark_response.status_code == 200
        
        doc_data = doc_response.json()
        bookmark_data = bookmark_response.json()
        
        # Both should reference the same URL
        assert doc_data["url"] == bookmark_data["url"]
        assert doc_data["url"] == "https://example.com/crossref"
        
        # Both should belong to the same user
        assert doc_data["user_id"] == bookmark_data["user_id"]
        assert doc_data["user_id"] == "integration-test-uid"

    @patch('app.core.user_context.get_authenticated_user_context')
    @patch('app.services.document_service.DocumentService.update_document')
    @patch('app.services.bookmark_service.BookmarkService.update_bookmark')
    def test_update_workflow(self, mock_update_bookmark, mock_update_doc, mock_get_user, mock_user_context):
        """Test updating both documents and bookmarks"""
        # Arrange
        mock_get_user.return_value = mock_user_context
        
        # Mock updated document
        updated_doc = Document(
            id="update-doc",
            title="Updated Document Title",
            url="https://example.com/updated",
            content="Updated content",
            user_id="integration-test-uid"
        )
        mock_update_doc.return_value = updated_doc
        
        # Mock updated bookmark
        updated_bookmark = Bookmark(
            id="update-bookmark",
            title="Updated Bookmark Title",
            url="https://example.com/updated",
            description="Updated description",
            user_id="integration-test-uid"
        )
        mock_update_bookmark.return_value = updated_bookmark
        
        # Act
        doc_update_response = client.put("/documents/update-doc", json={
            "title": "Updated Document Title",
            "content": "Updated content"
        })
        
        bookmark_update_response = client.put("/bookmarks/update-bookmark", json={
            "title": "Updated Bookmark Title",
            "description": "Updated description"
        })
        
        # Assert
        assert doc_update_response.status_code == 200
        assert bookmark_update_response.status_code == 200
        
        doc_data = doc_update_response.json()
        bookmark_data = bookmark_update_response.json()
        
        assert doc_data["title"] == "Updated Document Title"
        assert bookmark_data["title"] == "Updated Bookmark Title"

    @patch('app.core.user_context.get_authenticated_user_context')
    @patch('app.services.document_service.DocumentService.delete_document')
    @patch('app.services.bookmark_service.BookmarkService.delete_bookmark')
    def test_delete_workflow(self, mock_delete_bookmark, mock_delete_doc, mock_get_user, mock_user_context):
        """Test deleting both documents and bookmarks"""
        # Arrange
        mock_get_user.return_value = mock_user_context
        mock_delete_doc.return_value = True
        mock_delete_bookmark.return_value = True
        
        # Act
        doc_delete_response = client.delete("/documents/delete-doc")
        bookmark_delete_response = client.delete("/bookmarks/delete-bookmark")
        
        # Assert
        assert doc_delete_response.status_code == 204
        assert bookmark_delete_response.status_code == 204

    def test_system_endpoints_integration(self):
        """Test that system endpoints work together"""
        # Act
        root_response = client.get("/")
        ping_response = client.get("/ping")
        health_response = client.get("/health")
        
        # Assert
        assert root_response.status_code == 200
        assert ping_response.status_code == 200
        assert health_response.status_code == 200
        
        # Check that all return valid JSON
        root_data = root_response.json()
        ping_data = ping_response.json()
        health_data = health_response.json()
        
        assert isinstance(root_data, dict)
        assert isinstance(ping_data, dict)
        assert isinstance(health_data, dict)
        
        # Check version consistency
        assert root_data["version"] == health_data["version"]

    @patch('app.core.user_context.get_authenticated_user_context')
    def test_authentication_flow(self, mock_get_user, mock_user_context):
        """Test authentication flow across endpoints"""
        # Arrange
        mock_get_user.return_value = mock_user_context
        
        # Act
        auth_response = client.get("/auth/test")
        
        # Assert
        assert auth_response.status_code == 200
        auth_data = auth_response.json()
        
        assert auth_data["message"] == "Firebase authentication successful"
        assert auth_data["user"]["id"] == "integration-test-uid"
        assert auth_data["user"]["email"] == "integration@example.com"

    @patch('app.core.user_context.get_authenticated_user_context')
    @patch('app.services.document_service.DocumentService.get_by_status')
    def test_filtering_consistency(self, mock_get_by_status, mock_get_user, mock_user_context):
        """Test that filtering works consistently across endpoints"""
        # Arrange
        mock_get_user.return_value = mock_user_context
        
        # Mock filtered documents
        filtered_docs = [
            Document(
                id="filtered-doc",
                title="Filtered Document",
                status="processed",
                user_id="integration-test-uid"
            )
        ]
        mock_get_by_status.return_value = filtered_docs
        
        # Act
        filtered_response = client.get("/documents/status/processed")
        
        # Assert
        assert filtered_response.status_code == 200
        filtered_data = filtered_response.json()
        
        assert len(filtered_data) == 1
        assert filtered_data[0]["status"] == "processed"
        assert filtered_data[0]["user_id"] == "integration-test-uid"

    @patch('app.core.user_context.get_authenticated_user_context')
    @patch('app.services.document_service.DocumentService.get_user_documents')
    def test_pagination_consistency(self, mock_get_docs, mock_get_user, mock_user_context):
        """Test that pagination works consistently"""
        # Arrange
        mock_get_user.return_value = mock_user_context
        
        # Mock paginated documents
        mock_docs = [Document(id=f"doc-{i}", title=f"Document {i}", user_id="integration-test-uid") for i in range(10)]
        mock_get_docs.return_value = (mock_docs, 25)
        
        # Act
        page1_response = client.get("/documents/?page=1&page_size=10")
        page2_response = client.get("/documents/?page=2&page_size=10")
        
        # Assert
        assert page1_response.status_code == 200
        assert page2_response.status_code == 200
        
        page1_data = page1_response.json()
        page2_data = page2_response.json()
        
        assert page1_data["page"] == 1
        assert page2_data["page"] == 2
        assert page1_data["page_size"] == 10
        assert page2_data["page_size"] == 10
        assert page1_data["total"] == 25
        assert page2_data["total"] == 25
