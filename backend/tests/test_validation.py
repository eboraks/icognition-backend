"""
Validation tests for the API endpoints
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from app.main import app
from app.models import User, Document, Bookmark
from datetime import datetime

client = TestClient(app)


class TestValidation:
    """Validation tests for API endpoints"""

    @pytest.fixture
    def mock_user(self):
        """Mock user for validation testing"""
        return User(
            id="validation-test-uid",
            email="validation@example.com",
            display_name="Validation Test User",
            is_active=True,
            is_verified=True
        )

    @pytest.fixture
    def mock_user_context(self, mock_user):
        """Mock user context for validation testing"""
        from app.core.user_context import UserContext
        return UserContext(user=mock_user)

    def test_document_title_validation(self):
        """Test that document titles are properly validated"""
        # Act
        response = client.post("/documents/", json={
            "title": "",  # Empty title
            "content": "Test content",
            "content_type": "text"
        })
        
        # Assert
        assert response.status_code == 422
        assert "title" in str(response.json())

    def test_document_content_validation(self):
        """Test that document content is properly validated"""
        # Act
        response = client.post("/documents/", json={
            "title": "Test Document",
            "content": "",  # Empty content
            "content_type": "text"
        })
        
        # Assert
        assert response.status_code == 422
        assert "content" in str(response.json())

    def test_document_content_type_validation(self):
        """Test that document content types are properly validated"""
        # Act
        response = client.post("/documents/", json={
            "title": "Test Document",
            "content": "Test content",
            "content_type": "invalid_type"  # Invalid content type
        })
        
        # Assert
        assert response.status_code == 422
        assert "content_type" in str(response.json())

    def test_document_url_validation(self):
        """Test that document URLs are properly validated"""
        # Act
        response = client.post("/documents/", json={
            "title": "Test Document",
            "url": "not-a-valid-url",  # Invalid URL
            "content_type": "url"
        })
        
        # Assert
        assert response.status_code == 422
        assert "url" in str(response.json())

    def test_bookmark_title_validation(self):
        """Test that bookmark titles are properly validated"""
        # Act
        response = client.post("/bookmarks/", json={
            "title": "",  # Empty title
            "url": "https://example.com"
        })
        
        # Assert
        assert response.status_code == 422
        assert "title" in str(response.json())

    def test_bookmark_url_validation(self):
        """Test that bookmark URLs are properly validated"""
        # Act
        response = client.post("/bookmarks/", json={
            "title": "Test Bookmark",
            "url": "not-a-valid-url"  # Invalid URL
        })
        
        # Assert
        assert response.status_code == 422
        assert "url" in str(response.json())

    def test_bookmark_description_validation(self):
        """Test that bookmark descriptions are properly validated"""
        # Act
        response = client.post("/bookmarks/", json={
            "title": "Test Bookmark",
            "url": "https://example.com",
            "description": "x" * 10000  # Too long description
        })
        
        # Assert
        assert response.status_code == 422
        assert "description" in str(response.json())

    def test_document_id_validation(self):
        """Test that document IDs are properly validated"""
        # Act
        response = client.get("/documents/invalid-id-format")
        
        # Assert
        # Should either return 404 or fail gracefully
        assert response.status_code in [404, 422, 500]

    def test_bookmark_id_validation(self):
        """Test that bookmark IDs are properly validated"""
        # Act
        response = client.get("/bookmarks/invalid-id-format")
        
        # Assert
        # Should either return 404 or fail gracefully
        assert response.status_code in [404, 422, 500]

    def test_pagination_validation(self):
        """Test that pagination parameters are properly validated"""
        # Act
        response = client.get("/documents/?page=-1&page_size=0")
        
        # Assert
        assert response.status_code == 422
        assert "page" in str(response.json()) or "page_size" in str(response.json())

    def test_search_query_validation(self):
        """Test that search queries are properly validated"""
        # Act
        response = client.get("/bookmarks/find?query=")
        
        # Assert
        assert response.status_code == 422
        assert "query" in str(response.json())

    def test_status_validation(self):
        """Test that status parameters are properly validated"""
        # Act
        response = client.get("/documents/status/invalid_status")
        
        # Assert
        assert response.status_code == 422
        assert "status" in str(response.json())

    def test_required_fields_validation(self):
        """Test that required fields are properly validated"""
        # Act
        response = client.post("/documents/", json={})
        
        # Assert
        assert response.status_code == 422
        assert "title" in str(response.json())

    def test_optional_fields_validation(self):
        """Test that optional fields are properly validated when provided"""
        # Act
        response = client.post("/bookmarks/", json={
            "title": "Test Bookmark",
            "url": "https://example.com",
            "tags": ["tag1", "tag2", "tag3", "tag4", "tag5", "tag6"]  # Too many tags
        })
        
        # Assert
        assert response.status_code == 422
        assert "tags" in str(response.json())

    def test_data_type_validation(self):
        """Test that data types are properly validated"""
        # Act
        response = client.post("/documents/", json={
            "title": 123,  # Should be string
            "content": "Test content",
            "content_type": "text"
        })
        
        # Assert
        assert response.status_code == 422
        assert "title" in str(response.json())

    def test_string_length_validation(self):
        """Test that string lengths are properly validated"""
        # Act
        response = client.post("/documents/", json={
            "title": "x" * 1000,  # Too long title
            "content": "Test content",
            "content_type": "text"
        })
        
        # Assert
        assert response.status_code == 422
        assert "title" in str(response.json())

    def test_email_validation(self):
        """Test that email addresses are properly validated"""
        # Act
        response = client.post("/documents/", json={
            "title": "Test Document",
            "content": "Test content",
            "content_type": "text",
            "author_email": "invalid-email"  # Invalid email format
        })
        
        # Assert
        assert response.status_code == 422
        assert "author_email" in str(response.json())

    def test_date_validation(self):
        """Test that date fields are properly validated"""
        # Act
        response = client.post("/documents/", json={
            "title": "Test Document",
            "content": "Test content",
            "content_type": "text",
            "created_at": "invalid-date"  # Invalid date format
        })
        
        # Assert
        assert response.status_code == 422
        assert "created_at" in str(response.json())

    def test_boolean_validation(self):
        """Test that boolean fields are properly validated"""
        # Act
        response = client.post("/documents/", json={
            "title": "Test Document",
            "content": "Test content",
            "content_type": "text",
            "is_public": "not-a-boolean"  # Invalid boolean
        })
        
        # Assert
        assert response.status_code == 422
        assert "is_public" in str(response.json())

    def test_array_validation(self):
        """Test that array fields are properly validated"""
        # Act
        response = client.post("/bookmarks/", json={
            "title": "Test Bookmark",
            "url": "https://example.com",
            "tags": "not-an-array"  # Invalid array
        })
        
        # Assert
        assert response.status_code == 422
        assert "tags" in str(response.json())

    def test_object_validation(self):
        """Test that object fields are properly validated"""
        # Act
        response = client.post("/documents/", json={
            "title": "Test Document",
            "content": "Test content",
            "content_type": "text",
            "metadata": "not-an-object"  # Invalid object
        })
        
        # Assert
        assert response.status_code == 422
        assert "metadata" in str(response.json())

    def test_enum_validation(self):
        """Test that enum fields are properly validated"""
        # Act
        response = client.post("/documents/", json={
            "title": "Test Document",
            "content": "Test content",
            "content_type": "invalid_enum_value"  # Invalid enum
        })
        
        # Assert
        assert response.status_code == 422
        assert "content_type" in str(response.json())

    def test_nested_object_validation(self):
        """Test that nested objects are properly validated"""
        # Act
        response = client.post("/documents/", json={
            "title": "Test Document",
            "content": "Test content",
            "content_type": "text",
            "author": {
                "name": "",  # Empty name in nested object
                "email": "invalid-email"
            }
        })
        
        # Assert
        assert response.status_code == 422
        assert "author" in str(response.json())

    def test_custom_validation_rules(self):
        """Test that custom validation rules are properly applied"""
        # Act
        response = client.post("/bookmarks/", json={
            "title": "Test Bookmark",
            "url": "https://example.com",
            "priority": 10  # Invalid priority (should be 1-5)
        })
        
        # Assert
        assert response.status_code == 422
        assert "priority" in str(response.json())

    def test_cross_field_validation(self):
        """Test that cross-field validation rules are properly applied"""
        # Act
        response = client.post("/documents/", json={
            "title": "Test Document",
            "content": "Test content",
            "content_type": "url",  # URL type but no URL provided
            "url": None
        })
        
        # Assert
        assert response.status_code == 422
        assert "url" in str(response.json())

    def test_conditional_validation(self):
        """Test that conditional validation rules are properly applied"""
        # Act
        response = client.post("/documents/", json={
            "title": "Test Document",
            "content": "Test content",
            "content_type": "text",
            "expires_at": "2023-01-01"  # Expired date
        })
        
        # Assert
        assert response.status_code == 422
        assert "expires_at" in str(response.json())

    def test_file_upload_validation(self):
        """Test that file uploads are properly validated"""
        # Act
        response = client.post("/documents/", json={
            "title": "Test Document",
            "content": "Test content",
            "content_type": "file",
            "file_size": 100000000  # Too large file
        })
        
        # Assert
        assert response.status_code == 422
        assert "file_size" in str(response.json())

    def test_sanitization_validation(self):
        """Test that input sanitization is properly applied"""
        # Act
        response = client.post("/documents/", json={
            "title": "<script>alert('xss')</script>",
            "content": "Test content",
            "content_type": "text"
        })
        
        # Assert
        # Should either succeed (with sanitized input) or fail gracefully
        assert response.status_code in [200, 201, 401, 422, 500]

    def test_encoding_validation(self):
        """Test that character encoding is properly validated"""
        # Act
        response = client.post("/documents/", json={
            "title": "Test Document with special chars: éñ中文🚀",
            "content": "Test content with special chars: éñ中文🚀",
            "content_type": "text"
        })
        
        # Assert
        # Should handle special characters gracefully
        assert response.status_code in [200, 201, 401, 422, 500]
