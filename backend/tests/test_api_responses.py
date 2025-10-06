"""
API response tests for the API endpoints
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from app.main import app
from app.models import User, Document, Bookmark
from datetime import datetime

client = TestClient(app)


class TestAPIResponses:
    """API response tests for API endpoints"""

    @pytest.fixture
    def mock_user(self):
        """Mock user for API response testing"""
        return User(
            id="response-test-uid",
            email="response@example.com",
            display_name="Response Test User",
            is_active=True,
            is_verified=True
        )

    @pytest.fixture
    def mock_user_context(self, mock_user):
        """Mock user context for API response testing"""
        from app.core.user_context import UserContext
        return UserContext(user=mock_user)

    def test_system_endpoints_response_format(self):
        """Test that system endpoints return correct response format"""
        # Act
        root_response = client.get("/")
        ping_response = client.get("/ping")
        health_response = client.get("/health")
        
        # Assert
        assert root_response.status_code == 200
        assert ping_response.status_code == 200
        assert health_response.status_code == 200
        
        # Check response format
        root_data = root_response.json()
        ping_data = ping_response.json()
        health_data = health_response.json()
        
        assert "message" in root_data
        assert "version" in root_data
        assert "message" in ping_data
        assert "status" in health_data
        assert "uptime" in health_data

    @patch('app.core.user_context.get_authenticated_user_context')
    def test_auth_endpoint_response_format(self, mock_get_user, mock_user_context):
        """Test that auth endpoints return correct response format"""
        # Arrange
        mock_get_user.return_value = mock_user_context
        
        # Act
        response = client.get("/auth/test")
        
        # Assert
        assert response.status_code == 200
        data = response.json()
        
        assert "message" in data
        assert "user" in data
        assert data["message"] == "Firebase authentication successful"
        assert data["user"]["id"] == "response-test-uid"
        assert data["user"]["email"] == "response@example.com"

    @patch('app.core.user_context.get_authenticated_user_context')
    def test_document_creation_response_format(self, mock_get_user, mock_user_context):
        """Test that document creation returns correct response format"""
        # Arrange
        mock_get_user.return_value = mock_user_context
        
        # Mock document creation
        with patch('app.services.document_service.DocumentService.create_document') as mock_create:
            mock_doc = Document(
                id="response-doc-123",
                title="Response Document",
                content="Response content",
                user_id="response-test-uid"
            )
            mock_create.return_value = mock_doc
            
            # Act
            response = client.post("/documents/", json={
                "title": "Response Document",
                "content": "Response content",
                "content_type": "text"
            })
            
            # Assert
            assert response.status_code == 201
            data = response.json()
            
            assert "id" in data
            assert "title" in data
            assert "content" in data
            assert "user_id" in data
            assert data["id"] == "response-doc-123"
            assert data["title"] == "Response Document"

    @patch('app.core.user_context.get_authenticated_user_context')
    def test_bookmark_creation_response_format(self, mock_get_user, mock_user_context):
        """Test that bookmark creation returns correct response format"""
        # Arrange
        mock_get_user.return_value = mock_user_context
        
        # Mock bookmark creation
        with patch('app.services.bookmark_service.BookmarkService.create_bookmark') as mock_create:
            mock_bookmark = Bookmark(
                id="response-bookmark-123",
                title="Response Bookmark",
                url="https://example.com/response",
                user_id="response-test-uid"
            )
            mock_create.return_value = mock_bookmark
            
            # Act
            response = client.post("/bookmarks/", json={
                "title": "Response Bookmark",
                "url": "https://example.com/response"
            })
            
            # Assert
            assert response.status_code == 201
            data = response.json()
            
            assert "id" in data
            assert "title" in data
            assert "url" in data
            assert "user_id" in data
            assert data["id"] == "response-bookmark-123"
            assert data["title"] == "Response Bookmark"

    @patch('app.core.user_context.get_authenticated_user_context')
    def test_document_retrieval_response_format(self, mock_get_user, mock_user_context):
        """Test that document retrieval returns correct response format"""
        # Arrange
        mock_get_user.return_value = mock_user_context
        
        # Mock document retrieval
        with patch('app.services.document_service.DocumentService.get_by_id') as mock_get:
            mock_doc = Document(
                id="response-doc-123",
                title="Response Document",
                content="Response content",
                user_id="response-test-uid"
            )
            mock_get.return_value = mock_doc
            
            # Act
            response = client.get("/documents/response-doc-123")
            
            # Assert
            assert response.status_code == 200
            data = response.json()
            
            assert "id" in data
            assert "title" in data
            assert "content" in data
            assert "user_id" in data
            assert data["id"] == "response-doc-123"
            assert data["title"] == "Response Document"

    @patch('app.core.user_context.get_authenticated_user_context')
    def test_bookmark_retrieval_response_format(self, mock_get_user, mock_user_context):
        """Test that bookmark retrieval returns correct response format"""
        # Arrange
        mock_get_user.return_value = mock_user_context
        
        # Mock bookmark retrieval
        with patch('app.services.bookmark_service.BookmarkService.get_by_id') as mock_get:
            mock_bookmark = Bookmark(
                id="response-bookmark-123",
                title="Response Bookmark",
                url="https://example.com/response",
                user_id="response-test-uid"
            )
            mock_get.return_value = mock_bookmark
            
            # Act
            response = client.get("/bookmarks/response-bookmark-123")
            
            # Assert
            assert response.status_code == 200
            data = response.json()
            
            assert "id" in data
            assert "title" in data
            assert "url" in data
            assert "user_id" in data
            assert data["id"] == "response-bookmark-123"
            assert data["title"] == "Response Bookmark"

    @patch('app.core.user_context.get_authenticated_user_context')
    def test_document_listing_response_format(self, mock_get_user, mock_user_context):
        """Test that document listing returns correct response format"""
        # Arrange
        mock_get_user.return_value = mock_user_context
        
        # Mock document listing
        with patch('app.services.document_service.DocumentService.get_user_documents') as mock_get_docs:
            mock_docs = [
                Document(
                    id=f"response-doc-{i}",
                    title=f"Response Document {i}",
                    user_id="response-test-uid"
                ) for i in range(3)
            ]
            mock_get_docs.return_value = (mock_docs, 3)
            
            # Act
            response = client.get("/documents/")
            
            # Assert
            assert response.status_code == 200
            data = response.json()
            
            assert "documents" in data
            assert "total" in data
            assert "page" in data
            assert "page_size" in data
            assert len(data["documents"]) == 3
            assert data["total"] == 3

    @patch('app.core.user_context.get_authenticated_user_context')
    def test_bookmark_listing_response_format(self, mock_get_user, mock_user_context):
        """Test that bookmark listing returns correct response format"""
        # Arrange
        mock_get_user.return_value = mock_user_context
        
        # Mock bookmark listing
        with patch('app.services.bookmark_service.BookmarkService.get_user_bookmarks') as mock_get_bookmarks:
            mock_bookmarks = [
                Bookmark(
                    id=f"response-bookmark-{i}",
                    title=f"Response Bookmark {i}",
                    url=f"https://example.com/response{i}",
                    user_id="response-test-uid"
                ) for i in range(3)
            ]
            mock_get_bookmarks.return_value = (mock_bookmarks, 3)
            
            # Act
            response = client.get("/bookmarks/")
            
            # Assert
            assert response.status_code == 200
            data = response.json()
            
            assert "bookmarks" in data
            assert "total" in data
            assert "page" in data
            assert "page_size" in data
            assert len(data["bookmarks"]) == 3
            assert data["total"] == 3

    @patch('app.core.user_context.get_authenticated_user_context')
    def test_document_update_response_format(self, mock_get_user, mock_user_context):
        """Test that document update returns correct response format"""
        # Arrange
        mock_get_user.return_value = mock_user_context
        
        # Mock document update
        with patch('app.services.document_service.DocumentService.update_document') as mock_update:
            updated_doc = Document(
                id="response-doc-123",
                title="Updated Response Document",
                content="Updated response content",
                user_id="response-test-uid"
            )
            mock_update.return_value = updated_doc
            
            # Act
            response = client.put("/documents/response-doc-123", json={
                "title": "Updated Response Document",
                "content": "Updated response content"
            })
            
            # Assert
            assert response.status_code == 200
            data = response.json()
            
            assert "id" in data
            assert "title" in data
            assert "content" in data
            assert "user_id" in data
            assert data["title"] == "Updated Response Document"

    @patch('app.core.user_context.get_authenticated_user_context')
    def test_bookmark_update_response_format(self, mock_get_user, mock_user_context):
        """Test that bookmark update returns correct response format"""
        # Arrange
        mock_get_user.return_value = mock_user_context
        
        # Mock bookmark update
        with patch('app.services.bookmark_service.BookmarkService.update_bookmark') as mock_update:
            updated_bookmark = Bookmark(
                id="response-bookmark-123",
                title="Updated Response Bookmark",
                url="https://example.com/updated",
                user_id="response-test-uid"
            )
            mock_update.return_value = updated_bookmark
            
            # Act
            response = client.put("/bookmarks/response-bookmark-123", json={
                "title": "Updated Response Bookmark",
                "url": "https://example.com/updated"
            })
            
            # Assert
            assert response.status_code == 200
            data = response.json()
            
            assert "id" in data
            assert "title" in data
            assert "url" in data
            assert "user_id" in data
            assert data["title"] == "Updated Response Bookmark"

    @patch('app.core.user_context.get_authenticated_user_context')
    def test_document_deletion_response_format(self, mock_get_user, mock_user_context):
        """Test that document deletion returns correct response format"""
        # Arrange
        mock_get_user.return_value = mock_user_context
        
        # Mock document deletion
        with patch('app.services.document_service.DocumentService.delete_document') as mock_delete:
            mock_delete.return_value = True
            
            # Act
            response = client.delete("/documents/response-doc-123")
            
            # Assert
            assert response.status_code == 204
            assert response.content == b""  # No content for 204

    @patch('app.core.user_context.get_authenticated_user_context')
    def test_bookmark_deletion_response_format(self, mock_get_user, mock_user_context):
        """Test that bookmark deletion returns correct response format"""
        # Arrange
        mock_get_user.return_value = mock_user_context
        
        # Mock bookmark deletion
        with patch('app.services.bookmark_service.BookmarkService.delete_bookmark') as mock_delete:
            mock_delete.return_value = True
            
            # Act
            response = client.delete("/bookmarks/response-bookmark-123")
            
            # Assert
            assert response.status_code == 204
            assert response.content == b""  # No content for 204

    @patch('app.core.user_context.get_authenticated_user_context')
    def test_document_content_response_format(self, mock_get_user, mock_user_context):
        """Test that document content returns correct response format"""
        # Arrange
        mock_get_user.return_value = mock_user_context
        
        # Mock content retrieval
        with patch('app.services.document_service.DocumentService.get_content') as mock_get_content:
            mock_content = {
                "document_id": "response-doc-123",
                "content": "Response document content"
            }
            mock_get_content.return_value = mock_content
            
            # Act
            response = client.get("/documents/response-doc-123/content")
            
            # Assert
            assert response.status_code == 200
            data = response.json()
            
            assert "document_id" in data
            assert "content" in data
            assert data["document_id"] == "response-doc-123"
            assert data["content"] == "Response document content"

    @patch('app.core.user_context.get_authenticated_user_context')
    def test_bookmark_reanalysis_response_format(self, mock_get_user, mock_user_context):
        """Test that bookmark reanalysis returns correct response format"""
        # Arrange
        mock_get_user.return_value = mock_user_context
        
        # Mock reanalysis
        with patch('app.services.bookmark_service.BookmarkService.reanalyze_bookmark') as mock_reanalyze:
            mock_reanalyze.return_value = True
            
            # Act
            response = client.post("/bookmarks/response-bookmark-123/re-analyze")
            
            # Assert
            assert response.status_code == 200
            data = response.json()
            
            assert "message" in data
            assert "bookmark_id" in data
            assert data["message"] == "Analysis re-triggered for bookmark"
            assert data["bookmark_id"] == "response-bookmark-123"

    @patch('app.core.user_context.get_authenticated_user_context')
    def test_document_status_patch_response_format(self, mock_get_user, mock_user_context):
        """Test that document status patch returns correct response format"""
        # Arrange
        mock_get_user.return_value = mock_user_context
        
        # Mock status patching
        with patch('app.services.document_service.DocumentService.patch_status') as mock_patch_status:
            mock_status = {
                "document_id": "response-doc-123",
                "status": "updated"
            }
            mock_patch_status.return_value = mock_status
            
            # Act
            response = client.patch("/documents/response-doc-123/status", json={
                "status": "updated"
            })
            
            # Assert
            assert response.status_code == 200
            data = response.json()
            
            assert "document_id" in data
            assert "status" in data
            assert data["document_id"] == "response-doc-123"
            assert data["status"] == "updated"

    @patch('app.core.user_context.get_authenticated_user_context')
    def test_document_fetch_response_format(self, mock_get_user, mock_user_context):
        """Test that document fetch returns correct response format"""
        # Arrange
        mock_get_user.return_value = mock_user_context
        
        # Mock content fetching
        with patch('app.services.document_service.DocumentService.fetch_content') as mock_fetch:
            fetched_doc = Document(
                id="response-doc-123",
                title="Response Document",
                status="fetching",
                user_id="response-test-uid"
            )
            mock_fetch.return_value = fetched_doc
            
            # Act
            response = client.post("/documents/response-doc-123/fetch")
            
            # Assert
            assert response.status_code == 200
            data = response.json()
            
            assert "id" in data
            assert "title" in data
            assert "status" in data
            assert "user_id" in data
            assert data["id"] == "response-doc-123"
            assert data["status"] == "fetching"

    @patch('app.core.user_context.get_authenticated_user_context')
    def test_document_embedding_response_format(self, mock_get_user, mock_user_context):
        """Test that document embedding returns correct response format"""
        # Arrange
        mock_get_user.return_value = mock_user_context
        
        # Mock embedding generation
        with patch('app.services.document_service.DocumentService.generate_embedding') as mock_embed:
            embedded_doc = Document(
                id="response-doc-123",
                title="Response Document",
                status="embedding",
                user_id="response-test-uid"
            )
            mock_embed.return_value = embedded_doc
            
            # Act
            response = client.post("/documents/response-doc-123/embed")
            
            # Assert
            assert response.status_code == 200
            data = response.json()
            
            assert "id" in data
            assert "title" in data
            assert "status" in data
            assert "user_id" in data
            assert data["id"] == "response-doc-123"
            assert data["status"] == "embedding"

    def test_error_response_format(self):
        """Test that error responses return correct format"""
        # Act
        response = client.get("/auth/test")
        
        # Assert
        assert response.status_code == 401
        data = response.json()
        
        assert "detail" in data
        assert "Authentication required" in data["detail"]

    def test_validation_error_response_format(self):
        """Test that validation error responses return correct format"""
        # Act
        response = client.post("/documents/", json={
            "title": "",  # Empty title should cause validation error
            "content": "Test content",
            "content_type": "text"
        })
        
        # Assert
        assert response.status_code == 422
        data = response.json()
        
        assert "detail" in data
        assert isinstance(data["detail"], list)  # Validation errors are lists
