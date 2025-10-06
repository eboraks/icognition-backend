"""
Authentication flow tests for the API endpoints
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from app.main import app
from app.models import User, Document, Bookmark
from datetime import datetime

client = TestClient(app)


class TestAuthenticationFlow:
    """Authentication flow tests for API endpoints"""

    @pytest.fixture
    def mock_user(self):
        """Mock user for authentication flow testing"""
        return User(
            id="auth-flow-test-uid",
            email="authflow@example.com",
            display_name="Authentication Flow Test User",
            is_active=True,
            is_verified=True
        )

    @pytest.fixture
    def mock_user_context(self, mock_user):
        """Mock user context for authentication flow testing"""
        from app.core.user_context import UserContext
        return UserContext(user=mock_user)

    def test_unauthenticated_access_to_protected_endpoint(self):
        """Test that unauthenticated access to protected endpoints is rejected"""
        # Act
        response = client.get("/auth/test")
        
        # Assert
        assert response.status_code == 401
        assert "Authentication required" in response.json()["detail"]

    def test_unauthenticated_access_to_document_endpoints(self):
        """Test that unauthenticated access to document endpoints is rejected"""
        # Act
        response = client.get("/documents/")
        
        # Assert
        assert response.status_code == 401
        assert "Authentication required" in response.json()["detail"]

    def test_unauthenticated_access_to_bookmark_endpoints(self):
        """Test that unauthenticated access to bookmark endpoints is rejected"""
        # Act
        response = client.get("/bookmarks/")
        
        # Assert
        assert response.status_code == 401
        assert "Authentication required" in response.json()["detail"]

    def test_authenticated_access_to_protected_endpoint(self, mock_user_context):
        """Test that authenticated access to protected endpoints is allowed"""
        # Arrange
        with patch('app.core.user_context.get_authenticated_user_context') as mock_get_user:
            mock_get_user.return_value = mock_user_context
            
            # Act
            response = client.get("/auth/test")
            
            # Assert
            assert response.status_code == 200
            data = response.json()
            assert data["message"] == "Firebase authentication successful"
            assert data["user"]["id"] == "auth-flow-test-uid"

    def test_authenticated_access_to_document_endpoints(self, mock_user_context):
        """Test that authenticated access to document endpoints is allowed"""
        # Arrange
        with patch('app.core.user_context.get_authenticated_user_context') as mock_get_user:
            mock_get_user.return_value = mock_user_context
            
            # Mock document listing
            with patch('app.services.document_service.DocumentService.get_user_documents') as mock_get_docs:
                mock_docs = []
                mock_get_docs.return_value = (mock_docs, 0)
                
                # Act
                response = client.get("/documents/")
                
                # Assert
                assert response.status_code == 200
                data = response.json()
                assert "documents" in data
                assert "total" in data

    def test_authenticated_access_to_bookmark_endpoints(self, mock_user_context):
        """Test that authenticated access to bookmark endpoints is allowed"""
        # Arrange
        with patch('app.core.user_context.get_authenticated_user_context') as mock_get_user:
            mock_get_user.return_value = mock_user_context
            
            # Mock bookmark listing
            with patch('app.services.bookmark_service.BookmarkService.get_user_bookmarks') as mock_get_bookmarks:
                mock_bookmarks = []
                mock_get_bookmarks.return_value = (mock_bookmarks, 0)
                
                # Act
                response = client.get("/bookmarks/")
                
                # Assert
                assert response.status_code == 200
                data = response.json()
                assert "bookmarks" in data
                assert "total" in data

    def test_invalid_token_format(self):
        """Test that invalid token formats are rejected"""
        # Act
        response = client.get("/auth/test", headers={"Authorization": "InvalidFormat token"})
        
        # Assert
        assert response.status_code == 401

    def test_malformed_bearer_token(self):
        """Test that malformed bearer tokens are rejected"""
        # Act
        response = client.get("/auth/test", headers={"Authorization": "Bearer"})
        
        # Assert
        assert response.status_code == 401

    def test_empty_authorization_header(self):
        """Test that empty authorization headers are rejected"""
        # Act
        response = client.get("/auth/test", headers={"Authorization": ""})
        
        # Assert
        assert response.status_code == 401

    def test_missing_authorization_header(self):
        """Test that missing authorization headers are rejected"""
        # Act
        response = client.get("/auth/test")
        
        # Assert
        assert response.status_code == 401

    def test_expired_token(self):
        """Test that expired tokens are rejected"""
        # Act
        response = client.get("/auth/test", headers={"Authorization": "Bearer expired_token"})
        
        # Assert
        assert response.status_code == 401

    def test_revoked_token(self):
        """Test that revoked tokens are rejected"""
        # Act
        response = client.get("/auth/test", headers={"Authorization": "Bearer revoked_token"})
        
        # Assert
        assert response.status_code == 401

    def test_user_isolation(self, mock_user_context):
        """Test that users can only access their own data"""
        # Arrange
        with patch('app.core.user_context.get_authenticated_user_context') as mock_get_user:
            mock_get_user.return_value = mock_user_context
            
            # Mock document service to return user's documents only
            with patch('app.services.document_service.DocumentService.get_user_documents') as mock_get_docs:
                mock_docs = [
                    Document(
                        id="user-doc-1",
                        title="User Document 1",
                        user_id="auth-flow-test-uid"
                    )
                ]
                mock_get_docs.return_value = (mock_docs, 1)
                
                # Act
                response = client.get("/documents/")
                
                # Assert
                assert response.status_code == 200
                data = response.json()
                assert all(doc["user_id"] == "auth-flow-test-uid" for doc in data["documents"])

    def test_cross_user_access_prevention(self, mock_user_context):
        """Test that users cannot access other users' data"""
        # Arrange
        with patch('app.core.user_context.get_authenticated_user_context') as mock_get_user:
            mock_get_user.return_value = mock_user_context
            
            # Mock document service to return 404 for other user's documents
            with patch('app.services.document_service.DocumentService.get_by_id') as mock_get_doc:
                mock_get_doc.return_value = None  # Document not found (belongs to another user)
                
                # Act
                response = client.get("/documents/other-user-doc")
                
                # Assert
                assert response.status_code == 404

    def test_authentication_middleware_integration(self, mock_user_context):
        """Test that authentication middleware properly integrates with endpoints"""
        # Arrange
        with patch('app.core.user_context.get_authenticated_user_context') as mock_get_user:
            mock_get_user.return_value = mock_user_context
            
            # Mock document creation
            with patch('app.services.document_service.DocumentService.create_document') as mock_create:
                mock_doc = Document(
                    id="auth-doc-123",
                    title="Authentication Document",
                    content="Authentication content",
                    user_id="auth-flow-test-uid"
                )
                mock_create.return_value = mock_doc
                
                # Act
                response = client.post("/documents/", json={
                    "title": "Authentication Document",
                    "content": "Authentication content",
                    "content_type": "text"
                })
                
                # Assert
                assert response.status_code == 201
                data = response.json()
                assert data["user_id"] == "auth-flow-test-uid"

    def test_authentication_context_preservation(self, mock_user_context):
        """Test that authentication context is preserved across multiple requests"""
        # Arrange
        with patch('app.core.user_context.get_authenticated_user_context') as mock_get_user:
            mock_get_user.return_value = mock_user_context
            
            # Mock document operations
            with patch('app.services.document_service.DocumentService.get_user_documents') as mock_get_docs:
                mock_docs = []
                mock_get_docs.return_value = (mock_docs, 0)
                
                # Act - Multiple requests
                response1 = client.get("/documents/")
                response2 = client.get("/documents/")
                response3 = client.get("/documents/")
                
                # Assert
                assert response1.status_code == 200
                assert response2.status_code == 200
                assert response3.status_code == 200
                
                # Verify that the authentication context was used for all requests
                assert mock_get_user.call_count == 3

    def test_authentication_error_handling(self):
        """Test that authentication errors are properly handled"""
        # Act
        response = client.get("/auth/test", headers={"Authorization": "Bearer invalid_token"})
        
        # Assert
        assert response.status_code == 401
        data = response.json()
        assert "detail" in data
        assert "Invalid authentication token" in data["detail"]

    def test_authentication_success_flow(self, mock_user_context):
        """Test the complete authentication success flow"""
        # Arrange
        with patch('app.core.user_context.get_authenticated_user_context') as mock_get_user:
            mock_get_user.return_value = mock_user_context
            
            # Mock document creation
            with patch('app.services.document_service.DocumentService.create_document') as mock_create:
                mock_doc = Document(
                    id="success-doc-123",
                    title="Success Document",
                    content="Success content",
                    user_id="auth-flow-test-uid"
                )
                mock_create.return_value = mock_doc
                
                # Act
                response = client.post("/documents/", json={
                    "title": "Success Document",
                    "content": "Success content",
                    "content_type": "text"
                })
                
                # Assert
                assert response.status_code == 201
                data = response.json()
                assert data["id"] == "success-doc-123"
                assert data["user_id"] == "auth-flow-test-uid"

    def test_authentication_failure_flow(self):
        """Test the complete authentication failure flow"""
        # Act
        response = client.post("/documents/", json={
            "title": "Failure Document",
            "content": "Failure content",
            "content_type": "text"
        })
        
        # Assert
        assert response.status_code == 401
        data = response.json()
        assert "Authentication required" in data["detail"]

    def test_authentication_with_different_endpoints(self, mock_user_context):
        """Test authentication across different endpoint types"""
        # Arrange
        with patch('app.core.user_context.get_authenticated_user_context') as mock_get_user:
            mock_get_user.return_value = mock_user_context
            
            # Mock services
            with patch('app.services.document_service.DocumentService.get_user_documents') as mock_get_docs, \
                 patch('app.services.bookmark_service.BookmarkService.get_user_bookmarks') as mock_get_bookmarks:
                
                mock_docs = []
                mock_bookmarks = []
                mock_get_docs.return_value = (mock_docs, 0)
                mock_get_bookmarks.return_value = (mock_bookmarks, 0)
                
                # Act
                doc_response = client.get("/documents/")
                bookmark_response = client.get("/bookmarks/")
                auth_response = client.get("/auth/test")
                
                # Assert
                assert doc_response.status_code == 200
                assert bookmark_response.status_code == 200
                assert auth_response.status_code == 200
                
                # Verify that the authentication context was used for all requests
                assert mock_get_user.call_count == 3
