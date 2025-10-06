"""
Mock service tests for the API endpoints
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from app.main import app
from app.models import User, Document, Bookmark
from datetime import datetime

client = TestClient(app)


class TestMockServices:
    """Mock service tests for API endpoints"""

    @pytest.fixture
    def mock_user(self):
        """Mock user for service testing"""
        return User(
            id="service-test-uid",
            email="service@example.com",
            display_name="Service Test User",
            is_active=True,
            is_verified=True
        )

    @pytest.fixture
    def mock_user_context(self, mock_user):
        """Mock user context for service testing"""
        from app.core.user_context import UserContext
        return UserContext(user=mock_user)

    @patch('app.core.user_context.get_authenticated_user_context')
    @patch('app.services.document_service.DocumentService.create_document')
    def test_document_service_mock(self, mock_create_doc, mock_get_user, mock_user_context):
        """Test document service with mocked dependencies"""
        # Arrange
        mock_get_user.return_value = mock_user_context
        
        mock_doc = Document(
            id="mock-doc-123",
            title="Mock Document",
            content="Mock content",
            user_id="service-test-uid"
        )
        mock_create_doc.return_value = mock_doc
        
        # Act
        response = client.post("/documents/", json={
            "title": "Mock Document",
            "content": "Mock content",
            "content_type": "text"
        })
        
        # Assert
        assert response.status_code == 201
        data = response.json()
        assert data["id"] == "mock-doc-123"
        assert data["title"] == "Mock Document"
        mock_create_doc.assert_called_once()

    @patch('app.core.user_context.get_authenticated_user_context')
    @patch('app.services.bookmark_service.BookmarkService.create_bookmark')
    def test_bookmark_service_mock(self, mock_create_bookmark, mock_get_user, mock_user_context):
        """Test bookmark service with mocked dependencies"""
        # Arrange
        mock_get_user.return_value = mock_user_context
        
        mock_bookmark = Bookmark(
            id="mock-bookmark-123",
            title="Mock Bookmark",
            url="https://example.com/mock",
            user_id="service-test-uid"
        )
        mock_create_bookmark.return_value = mock_bookmark
        
        # Act
        response = client.post("/bookmarks/", json={
            "title": "Mock Bookmark",
            "url": "https://example.com/mock"
        })
        
        # Assert
        assert response.status_code == 201
        data = response.json()
        assert data["id"] == "mock-bookmark-123"
        assert data["title"] == "Mock Bookmark"
        mock_create_bookmark.assert_called_once()

    @patch('app.core.user_context.get_authenticated_user_context')
    @patch('app.services.document_service.DocumentService.get_by_id')
    def test_document_retrieval_mock(self, mock_get_doc, mock_get_user, mock_user_context):
        """Test document retrieval with mocked service"""
        # Arrange
        mock_get_user.return_value = mock_user_context
        
        mock_doc = Document(
            id="retrieve-doc-123",
            title="Retrieve Document",
            content="Retrieve content",
            user_id="service-test-uid"
        )
        mock_get_doc.return_value = mock_doc
        
        # Act
        response = client.get("/documents/retrieve-doc-123")
        
        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "retrieve-doc-123"
        assert data["title"] == "Retrieve Document"
        mock_get_doc.assert_called_once_with("retrieve-doc-123")

    @patch('app.core.user_context.get_authenticated_user_context')
    @patch('app.services.bookmark_service.BookmarkService.get_by_id')
    def test_bookmark_retrieval_mock(self, mock_get_bookmark, mock_get_user, mock_user_context):
        """Test bookmark retrieval with mocked service"""
        # Arrange
        mock_get_user.return_value = mock_user_context
        
        mock_bookmark = Bookmark(
            id="retrieve-bookmark-123",
            title="Retrieve Bookmark",
            url="https://example.com/retrieve",
            user_id="service-test-uid"
        )
        mock_get_bookmark.return_value = mock_bookmark
        
        # Act
        response = client.get("/bookmarks/retrieve-bookmark-123")
        
        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "retrieve-bookmark-123"
        assert data["title"] == "Retrieve Bookmark"
        mock_get_bookmark.assert_called_once_with("retrieve-bookmark-123")

    @patch('app.core.user_context.get_authenticated_user_context')
    @patch('app.services.document_service.DocumentService.get_user_documents')
    def test_document_list_mock(self, mock_get_docs, mock_get_user, mock_user_context):
        """Test document listing with mocked service"""
        # Arrange
        mock_get_user.return_value = mock_user_context
        
        mock_docs = [
            Document(
                id=f"list-doc-{i}",
                title=f"List Document {i}",
                user_id="service-test-uid"
            ) for i in range(3)
        ]
        mock_get_docs.return_value = (mock_docs, 3)
        
        # Act
        response = client.get("/documents/")
        
        # Assert
        assert response.status_code == 200
        data = response.json()
        assert len(data["documents"]) == 3
        assert data["total"] == 3
        mock_get_docs.assert_called_once()

    @patch('app.core.user_context.get_authenticated_user_context')
    @patch('app.services.bookmark_service.BookmarkService.get_user_bookmarks')
    def test_bookmark_list_mock(self, mock_get_bookmarks, mock_get_user, mock_user_context):
        """Test bookmark listing with mocked service"""
        # Arrange
        mock_get_user.return_value = mock_user_context
        
        mock_bookmarks = [
            Bookmark(
                id=f"list-bookmark-{i}",
                title=f"List Bookmark {i}",
                url=f"https://example.com/list{i}",
                user_id="service-test-uid"
            ) for i in range(3)
        ]
        mock_get_bookmarks.return_value = (mock_bookmarks, 3)
        
        # Act
        response = client.get("/bookmarks/")
        
        # Assert
        assert response.status_code == 200
        data = response.json()
        assert len(data["bookmarks"]) == 3
        assert data["total"] == 3
        mock_get_bookmarks.assert_called_once()

    @patch('app.core.user_context.get_authenticated_user_context')
    @patch('app.services.document_service.DocumentService.update_document')
    def test_document_update_mock(self, mock_update_doc, mock_get_user, mock_user_context):
        """Test document update with mocked service"""
        # Arrange
        mock_get_user.return_value = mock_user_context
        
        updated_doc = Document(
            id="update-doc-123",
            title="Updated Document",
            content="Updated content",
            user_id="service-test-uid"
        )
        mock_update_doc.return_value = updated_doc
        
        # Act
        response = client.put("/documents/update-doc-123", json={
            "title": "Updated Document",
            "content": "Updated content"
        })
        
        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "Updated Document"
        mock_update_doc.assert_called_once()

    @patch('app.core.user_context.get_authenticated_user_context')
    @patch('app.services.bookmark_service.BookmarkService.update_bookmark')
    def test_bookmark_update_mock(self, mock_update_bookmark, mock_get_user, mock_user_context):
        """Test bookmark update with mocked service"""
        # Arrange
        mock_get_user.return_value = mock_user_context
        
        updated_bookmark = Bookmark(
            id="update-bookmark-123",
            title="Updated Bookmark",
            url="https://example.com/updated",
            user_id="service-test-uid"
        )
        mock_update_bookmark.return_value = updated_bookmark
        
        # Act
        response = client.put("/bookmarks/update-bookmark-123", json={
            "title": "Updated Bookmark",
            "url": "https://example.com/updated"
        })
        
        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "Updated Bookmark"
        mock_update_bookmark.assert_called_once()

    @patch('app.core.user_context.get_authenticated_user_context')
    @patch('app.services.document_service.DocumentService.delete_document')
    def test_document_delete_mock(self, mock_delete_doc, mock_get_user, mock_user_context):
        """Test document deletion with mocked service"""
        # Arrange
        mock_get_user.return_value = mock_user_context
        mock_delete_doc.return_value = True
        
        # Act
        response = client.delete("/documents/delete-doc-123")
        
        # Assert
        assert response.status_code == 204
        mock_delete_doc.assert_called_once_with("delete-doc-123")

    @patch('app.core.user_context.get_authenticated_user_context')
    @patch('app.services.bookmark_service.BookmarkService.delete_bookmark')
    def test_bookmark_delete_mock(self, mock_delete_bookmark, mock_get_user, mock_user_context):
        """Test bookmark deletion with mocked service"""
        # Arrange
        mock_get_user.return_value = mock_user_context
        mock_delete_bookmark.return_value = True
        
        # Act
        response = client.delete("/bookmarks/delete-bookmark-123")
        
        # Assert
        assert response.status_code == 204
        mock_delete_bookmark.assert_called_once_with("delete-bookmark-123")

    @patch('app.core.user_context.get_authenticated_user_context')
    @patch('app.services.document_service.DocumentService.get_by_status')
    def test_document_status_filter_mock(self, mock_get_by_status, mock_get_user, mock_user_context):
        """Test document status filtering with mocked service"""
        # Arrange
        mock_get_user.return_value = mock_user_context
        
        mock_docs = [
            Document(
                id="status-doc-123",
                title="Status Document",
                status="processed",
                user_id="service-test-uid"
            )
        ]
        mock_get_by_status.return_value = mock_docs
        
        # Act
        response = client.get("/documents/status/processed")
        
        # Assert
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["status"] == "processed"
        mock_get_by_status.assert_called_once_with("processed")

    @patch('app.core.user_context.get_authenticated_user_context')
    @patch('app.services.bookmark_service.BookmarkService.find_bookmark')
    def test_bookmark_search_mock(self, mock_find_bookmark, mock_get_user, mock_user_context):
        """Test bookmark search with mocked service"""
        # Arrange
        mock_get_user.return_value = mock_user_context
        
        mock_bookmark = Bookmark(
            id="search-bookmark-123",
            title="Search Bookmark",
            url="https://example.com/search",
            user_id="service-test-uid"
        )
        mock_find_bookmark.return_value = mock_bookmark
        
        # Act
        response = client.get("/bookmarks/find?query=search")
        
        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "search-bookmark-123"
        assert data["title"] == "Search Bookmark"
        mock_find_bookmark.assert_called_once_with("search")

    @patch('app.core.user_context.get_authenticated_user_context')
    @patch('app.services.document_service.DocumentService.get_content')
    def test_document_content_mock(self, mock_get_content, mock_get_user, mock_user_context):
        """Test document content retrieval with mocked service"""
        # Arrange
        mock_get_user.return_value = mock_user_context
        
        mock_content = {
            "document_id": "content-doc-123",
            "content": "Mock document content"
        }
        mock_get_content.return_value = mock_content
        
        # Act
        response = client.get("/documents/content-doc-123/content")
        
        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["document_id"] == "content-doc-123"
        assert data["content"] == "Mock document content"
        mock_get_content.assert_called_once_with("content-doc-123")

    @patch('app.core.user_context.get_authenticated_user_context')
    @patch('app.services.bookmark_service.BookmarkService.reanalyze_bookmark')
    def test_bookmark_reanalyze_mock(self, mock_reanalyze, mock_get_user, mock_user_context):
        """Test bookmark reanalysis with mocked service"""
        # Arrange
        mock_get_user.return_value = mock_user_context
        mock_reanalyze.return_value = True
        
        # Act
        response = client.post("/bookmarks/reanalyze-bookmark-123/re-analyze")
        
        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Analysis re-triggered for bookmark"
        assert data["bookmark_id"] == "reanalyze-bookmark-123"
        mock_reanalyze.assert_called_once_with("reanalyze-bookmark-123")

    @patch('app.core.user_context.get_authenticated_user_context')
    @patch('app.services.document_service.DocumentService.patch_status')
    def test_document_status_patch_mock(self, mock_patch_status, mock_get_user, mock_user_context):
        """Test document status patching with mocked service"""
        # Arrange
        mock_get_user.return_value = mock_user_context
        
        mock_status = {
            "document_id": "patch-doc-123",
            "status": "updated"
        }
        mock_patch_status.return_value = mock_status
        
        # Act
        response = client.patch("/documents/patch-doc-123/status", json={
            "status": "updated"
        })
        
        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["document_id"] == "patch-doc-123"
        assert data["status"] == "updated"
        mock_patch_status.assert_called_once()

    @patch('app.core.user_context.get_authenticated_user_context')
    @patch('app.services.document_service.DocumentService.fetch_content')
    def test_document_fetch_mock(self, mock_fetch_content, mock_get_user, mock_user_context):
        """Test document content fetching with mocked service"""
        # Arrange
        mock_get_user.return_value = mock_user_context
        
        fetched_doc = Document(
            id="fetch-doc-123",
            title="Fetch Document",
            status="fetching",
            user_id="service-test-uid"
        )
        mock_fetch_content.return_value = fetched_doc
        
        # Act
        response = client.post("/documents/fetch-doc-123/fetch")
        
        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "fetch-doc-123"
        assert data["status"] == "fetching"
        mock_fetch_content.assert_called_once_with("fetch-doc-123")

    @patch('app.core.user_context.get_authenticated_user_context')
    @patch('app.services.document_service.DocumentService.generate_embedding')
    def test_document_embedding_mock(self, mock_generate_embedding, mock_get_user, mock_user_context):
        """Test document embedding generation with mocked service"""
        # Arrange
        mock_get_user.return_value = mock_user_context
        
        embedded_doc = Document(
            id="embed-doc-123",
            title="Embed Document",
            status="embedding",
            user_id="service-test-uid"
        )
        mock_generate_embedding.return_value = embedded_doc
        
        # Act
        response = client.post("/documents/embed-doc-123/embed")
        
        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "embed-doc-123"
        assert data["status"] == "embedding"
        mock_generate_embedding.assert_called_once_with("embed-doc-123")
