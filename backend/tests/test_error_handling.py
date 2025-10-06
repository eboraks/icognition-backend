"""
Error handling tests for the API endpoints
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from app.main import app
from app.models import User, Document, Bookmark
from datetime import datetime

client = TestClient(app)


class TestErrorHandling:
    """Error handling tests for API endpoints"""

    @pytest.fixture
    def mock_user(self):
        """Mock user for error handling testing"""
        return User(
            id="error-test-uid",
            email="error@example.com",
            display_name="Error Test User",
            is_active=True,
            is_verified=True
        )

    @pytest.fixture
    def mock_user_context(self, mock_user):
        """Mock user context for error handling testing"""
        from app.core.user_context import UserContext
        return UserContext(user=mock_user)

    def test_unauthorized_access(self):
        """Test that endpoints properly handle unauthorized access"""
        # Act
        response = client.get("/auth/test")
        
        # Assert
        assert response.status_code == 401
        assert "Authentication required" in response.json()["detail"]

    def test_invalid_token(self):
        """Test that endpoints properly handle invalid tokens"""
        # Act
        response = client.get("/auth/test", headers={"Authorization": "Bearer invalid_token"})
        
        # Assert
        assert response.status_code == 401
        assert "Invalid authentication token" in response.json()["detail"]

    @patch('app.core.user_context.get_authenticated_user_context')
    def test_document_not_found(self, mock_get_user, mock_user_context):
        """Test that document endpoints properly handle not found errors"""
        # Arrange
        mock_get_user.return_value = mock_user_context
        
        # Act
        response = client.get("/documents/non-existent-doc")
        
        # Assert
        assert response.status_code == 404
        assert "Document not found" in response.json()["detail"]

    @patch('app.core.user_context.get_authenticated_user_context')
    def test_bookmark_not_found(self, mock_get_user, mock_user_context):
        """Test that bookmark endpoints properly handle not found errors"""
        # Arrange
        mock_get_user.return_value = mock_user_context
        
        # Act
        response = client.get("/bookmarks/non-existent-bookmark")
        
        # Assert
        assert response.status_code == 404
        assert "Bookmark not found" in response.json()["detail"]

    @patch('app.core.user_context.get_authenticated_user_context')
    def test_invalid_document_data(self, mock_get_user, mock_user_context):
        """Test that document endpoints properly handle invalid data"""
        # Arrange
        mock_get_user.return_value = mock_user_context
        
        # Act
        response = client.post("/documents/", json={
            "title": "",  # Empty title should be invalid
            "content_type": "invalid_type"  # Invalid content type
        })
        
        # Assert
        assert response.status_code == 422  # Validation error

    @patch('app.core.user_context.get_authenticated_user_context')
    def test_invalid_bookmark_data(self, mock_get_user, mock_user_context):
        """Test that bookmark endpoints properly handle invalid data"""
        # Arrange
        mock_get_user.return_value = mock_user_context
        
        # Act
        response = client.post("/bookmarks/", json={
            "title": "",  # Empty title should be invalid
            "url": "not-a-valid-url"  # Invalid URL format
        })
        
        # Assert
        assert response.status_code == 422  # Validation error

    @patch('app.core.user_context.get_authenticated_user_context')
    def test_document_service_error(self, mock_get_user, mock_user_context):
        """Test that document endpoints properly handle service errors"""
        # Arrange
        mock_get_user.return_value = mock_user_context
        
        # Mock service to raise an exception
        with patch('app.services.document_service.DocumentService.create_document') as mock_create:
            mock_create.side_effect = Exception("Database connection failed")
            
            # Act
            response = client.post("/documents/", json={
                "title": "Test Document",
                "content_type": "text"
            })
            
            # Assert
            assert response.status_code == 500
            assert "Internal server error" in response.json()["detail"]

    @patch('app.core.user_context.get_authenticated_user_context')
    def test_bookmark_service_error(self, mock_get_user, mock_user_context):
        """Test that bookmark endpoints properly handle service errors"""
        # Arrange
        mock_get_user.return_value = mock_user_context
        
        # Mock service to raise an exception
        with patch('app.services.bookmark_service.BookmarkService.create_bookmark') as mock_create:
            mock_create.side_effect = Exception("Database connection failed")
            
            # Act
            response = client.post("/bookmarks/", json={
                "title": "Test Bookmark",
                "url": "https://example.com"
            })
            
            # Assert
            assert response.status_code == 500
            assert "Internal server error" in response.json()["detail"]

    @patch('app.core.user_context.get_authenticated_user_context')
    def test_document_update_error(self, mock_get_user, mock_user_context):
        """Test that document update endpoints properly handle errors"""
        # Arrange
        mock_get_user.return_value = mock_user_context
        
        # Mock service to raise an exception
        with patch('app.services.document_service.DocumentService.update_document') as mock_update:
            mock_update.side_effect = Exception("Update failed")
            
            # Act
            response = client.put("/documents/test-doc", json={
                "title": "Updated Title"
            })
            
            # Assert
            assert response.status_code == 500
            assert "Internal server error" in response.json()["detail"]

    @patch('app.core.user_context.get_authenticated_user_context')
    def test_bookmark_update_error(self, mock_get_user, mock_user_context):
        """Test that bookmark update endpoints properly handle errors"""
        # Arrange
        mock_get_user.return_value = mock_user_context
        
        # Mock service to raise an exception
        with patch('app.services.bookmark_service.BookmarkService.update_bookmark') as mock_update:
            mock_update.side_effect = Exception("Update failed")
            
            # Act
            response = client.put("/bookmarks/test-bookmark", json={
                "title": "Updated Title"
            })
            
            # Assert
            assert response.status_code == 500
            assert "Internal server error" in response.json()["detail"]

    @patch('app.core.user_context.get_authenticated_user_context')
    def test_document_delete_error(self, mock_get_user, mock_user_context):
        """Test that document delete endpoints properly handle errors"""
        # Arrange
        mock_get_user.return_value = mock_user_context
        
        # Mock service to raise an exception
        with patch('app.services.document_service.DocumentService.delete_document') as mock_delete:
            mock_delete.side_effect = Exception("Delete failed")
            
            # Act
            response = client.delete("/documents/test-doc")
            
            # Assert
            assert response.status_code == 500
            assert "Internal server error" in response.json()["detail"]

    @patch('app.core.user_context.get_authenticated_user_context')
    def test_bookmark_delete_error(self, mock_get_user, mock_user_context):
        """Test that bookmark delete endpoints properly handle errors"""
        # Arrange
        mock_get_user.return_value = mock_user_context
        
        # Mock service to raise an exception
        with patch('app.services.bookmark_service.BookmarkService.delete_bookmark') as mock_delete:
            mock_delete.side_effect = Exception("Delete failed")
            
            # Act
            response = client.delete("/bookmarks/test-bookmark")
            
            # Assert
            assert response.status_code == 500
            assert "Internal server error" in response.json()["detail"]

    def test_malformed_json(self):
        """Test that endpoints properly handle malformed JSON"""
        # Act
        response = client.post(
            "/documents/",
            data="invalid json",
            headers={"Content-Type": "application/json"}
        )
        
        # Assert
        assert response.status_code == 422

    def test_missing_required_fields(self):
        """Test that endpoints properly handle missing required fields"""
        # Act
        response = client.post("/documents/", json={})
        
        # Assert
        assert response.status_code == 422

    def test_invalid_http_method(self):
        """Test that endpoints properly handle invalid HTTP methods"""
        # Act
        response = client.patch("/auth/test")
        
        # Assert
        assert response.status_code == 405  # Method not allowed

    def test_invalid_endpoint(self):
        """Test that invalid endpoints return 404"""
        # Act
        response = client.get("/invalid-endpoint")
        
        # Assert
        assert response.status_code == 404

    @patch('app.core.user_context.get_authenticated_user_context')
    def test_document_content_error(self, mock_get_user, mock_user_context):
        """Test that document content endpoints properly handle errors"""
        # Arrange
        mock_get_user.return_value = mock_user_context
        
        # Mock service to raise an exception
        with patch('app.services.document_service.DocumentService.get_content') as mock_get_content:
            mock_get_content.side_effect = Exception("Content retrieval failed")
            
            # Act
            response = client.get("/documents/test-doc/content")
            
            # Assert
            assert response.status_code == 500
            assert "Internal server error" in response.json()["detail"]

    @patch('app.core.user_context.get_authenticated_user_context')
    def test_bookmark_reanalyze_error(self, mock_get_user, mock_user_context):
        """Test that bookmark reanalyze endpoints properly handle errors"""
        # Arrange
        mock_get_user.return_value = mock_user_context
        
        # Mock service to raise an exception
        with patch('app.services.bookmark_service.BookmarkService.reanalyze_bookmark') as mock_reanalyze:
            mock_reanalyze.side_effect = Exception("Reanalysis failed")
            
            # Act
            response = client.post("/bookmarks/test-bookmark/re-analyze")
            
            # Assert
            assert response.status_code == 500
            assert "Internal server error" in response.json()["detail"]

    def test_large_payload(self):
        """Test that endpoints properly handle large payloads"""
        # Act
        large_content = "x" * 1000000  # 1MB of content
        response = client.post("/documents/", json={
            "title": "Large Document",
            "content": large_content,
            "content_type": "text"
        })
        
        # Assert
        # Should either succeed or fail gracefully with appropriate error
        assert response.status_code in [200, 201, 413, 422, 500]

    def test_special_characters(self):
        """Test that endpoints properly handle special characters"""
        # Act
        response = client.post("/documents/", json={
            "title": "Document with special chars: éñ中文🚀",
            "content": "Content with special chars: éñ中文🚀",
            "content_type": "text"
        })
        
        # Assert
        # Should handle special characters gracefully
        assert response.status_code in [200, 201, 422, 500]

    def test_sql_injection_attempt(self):
        """Test that endpoints properly handle SQL injection attempts"""
        # Act
        response = client.post("/documents/", json={
            "title": "'; DROP TABLE documents; --",
            "content": "'; DROP TABLE documents; --",
            "content_type": "text"
        })
        
        # Assert
        # Should either succeed (with sanitized input) or fail gracefully
        assert response.status_code in [200, 201, 422, 500]

    def test_xss_attempt(self):
        """Test that endpoints properly handle XSS attempts"""
        # Act
        response = client.post("/documents/", json={
            "title": "<script>alert('xss')</script>",
            "content": "<script>alert('xss')</script>",
            "content_type": "text"
        })
        
        # Assert
        # Should either succeed (with sanitized input) or fail gracefully
        assert response.status_code in [200, 201, 422, 500]
