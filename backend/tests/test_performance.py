"""
Performance tests for the API endpoints
"""

import pytest
import time
import asyncio
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from app.main import app
from app.models import User, Document, Bookmark
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

client = TestClient(app)


class TestPerformance:
    """Performance tests for API endpoints"""

    @pytest.fixture
    def mock_user(self):
        """Mock user for performance testing"""
        return User(
            id="perf-test-uid",
            email="perf@example.com",
            display_name="Performance Test User",
            is_active=True,
            is_verified=True
        )

    @pytest.fixture
    def mock_user_context(self, mock_user):
        """Mock user context for performance testing"""
        from app.core.user_context import UserContext
        return UserContext(user=mock_user)

    @patch('app.core.user_context.get_authenticated_user_context')
    def test_document_creation_performance(self, mock_get_user, mock_user_context):
        """Test that document creation performs within acceptable time limits"""
        # Arrange
        mock_get_user.return_value = mock_user_context
        
        # Mock document creation
        with patch('app.services.document_service.DocumentService.create_document') as mock_create:
            mock_doc = Document(
                id="perf-doc",
                title="Performance Test Document",
                content="Performance test content",
                user_id="perf-test-uid"
            )
            mock_create.return_value = mock_doc
            
            # Act
            start_time = time.time()
            response = client.post("/documents/", json={
                "title": "Performance Test Document",
                "content": "Performance test content",
                "content_type": "text"
            })
            end_time = time.time()
            
            # Assert
            assert response.status_code == 201
            assert (end_time - start_time) < 1.0  # Should complete within 1 second

    @patch('app.core.user_context.get_authenticated_user_context')
    def test_bookmark_creation_performance(self, mock_get_user, mock_user_context):
        """Test that bookmark creation performs within acceptable time limits"""
        # Arrange
        mock_get_user.return_value = mock_user_context
        
        # Mock bookmark creation
        with patch('app.services.bookmark_service.BookmarkService.create_bookmark') as mock_create:
            mock_bookmark = Bookmark(
                id="perf-bookmark",
                title="Performance Test Bookmark",
                url="https://example.com/perf",
                user_id="perf-test-uid"
            )
            mock_create.return_value = mock_bookmark
            
            # Act
            start_time = time.time()
            response = client.post("/bookmarks/", json={
                "title": "Performance Test Bookmark",
                "url": "https://example.com/perf"
            })
            end_time = time.time()
            
            # Assert
            assert response.status_code == 201
            assert (end_time - start_time) < 1.0  # Should complete within 1 second

    @patch('app.core.user_context.get_authenticated_user_context')
    def test_document_retrieval_performance(self, mock_get_user, mock_user_context):
        """Test that document retrieval performs within acceptable time limits"""
        # Arrange
        mock_get_user.return_value = mock_user_context
        
        # Mock document retrieval
        with patch('app.services.document_service.DocumentService.get_by_id') as mock_get:
            mock_doc = Document(
                id="perf-doc",
                title="Performance Test Document",
                content="Performance test content",
                user_id="perf-test-uid"
            )
            mock_get.return_value = mock_doc
            
            # Act
            start_time = time.time()
            response = client.get("/documents/perf-doc")
            end_time = time.time()
            
            # Assert
            assert response.status_code == 200
            assert (end_time - start_time) < 0.5  # Should complete within 0.5 seconds

    @patch('app.core.user_context.get_authenticated_user_context')
    def test_bookmark_retrieval_performance(self, mock_get_user, mock_user_context):
        """Test that bookmark retrieval performs within acceptable time limits"""
        # Arrange
        mock_get_user.return_value = mock_user_context
        
        # Mock bookmark retrieval
        with patch('app.services.bookmark_service.BookmarkService.get_by_id') as mock_get:
            mock_bookmark = Bookmark(
                id="perf-bookmark",
                title="Performance Test Bookmark",
                url="https://example.com/perf",
                user_id="perf-test-uid"
            )
            mock_get.return_value = mock_bookmark
            
            # Act
            start_time = time.time()
            response = client.get("/bookmarks/perf-bookmark")
            end_time = time.time()
            
            # Assert
            assert response.status_code == 200
            assert (end_time - start_time) < 0.5  # Should complete within 0.5 seconds

    @patch('app.core.user_context.get_authenticated_user_context')
    def test_document_list_performance(self, mock_get_user, mock_user_context):
        """Test that document listing performs within acceptable time limits"""
        # Arrange
        mock_get_user.return_value = mock_user_context
        
        # Mock document listing
        with patch('app.services.document_service.DocumentService.get_user_documents') as mock_get_docs:
            mock_docs = [
                Document(
                    id=f"perf-doc-{i}",
                    title=f"Performance Document {i}",
                    user_id="perf-test-uid"
                ) for i in range(100)
            ]
            mock_get_docs.return_value = (mock_docs, 100)
            
            # Act
            start_time = time.time()
            response = client.get("/documents/")
            end_time = time.time()
            
            # Assert
            assert response.status_code == 200
            assert (end_time - start_time) < 2.0  # Should complete within 2 seconds for 100 documents

    @patch('app.core.user_context.get_authenticated_user_context')
    def test_bookmark_list_performance(self, mock_get_user, mock_user_context):
        """Test that bookmark listing performs within acceptable time limits"""
        # Arrange
        mock_get_user.return_value = mock_user_context
        
        # Mock bookmark listing
        with patch('app.services.bookmark_service.BookmarkService.get_user_bookmarks') as mock_get_bookmarks:
            mock_bookmarks = [
                Bookmark(
                    id=f"perf-bookmark-{i}",
                    title=f"Performance Bookmark {i}",
                    url=f"https://example.com/perf{i}",
                    user_id="perf-test-uid"
                ) for i in range(100)
            ]
            mock_get_bookmarks.return_value = (mock_bookmarks, 100)
            
            # Act
            start_time = time.time()
            response = client.get("/bookmarks/")
            end_time = time.time()
            
            # Assert
            assert response.status_code == 200
            assert (end_time - start_time) < 2.0  # Should complete within 2 seconds for 100 bookmarks

    def test_system_endpoints_performance(self):
        """Test that system endpoints perform within acceptable time limits"""
        # Act
        start_time = time.time()
        root_response = client.get("/")
        ping_response = client.get("/ping")
        health_response = client.get("/health")
        end_time = time.time()
        
        # Assert
        assert root_response.status_code == 200
        assert ping_response.status_code == 200
        assert health_response.status_code == 200
        assert (end_time - start_time) < 0.1  # Should complete within 0.1 seconds

    @patch('app.core.user_context.get_authenticated_user_context')
    def test_concurrent_requests(self, mock_get_user, mock_user_context):
        """Test that the API can handle concurrent requests"""
        # Arrange
        mock_get_user.return_value = mock_user_context
        
        # Mock document creation
        with patch('app.services.document_service.DocumentService.create_document') as mock_create:
            mock_doc = Document(
                id="concurrent-doc",
                title="Concurrent Test Document",
                content="Concurrent test content",
                user_id="perf-test-uid"
            )
            mock_create.return_value = mock_doc
            
            # Act
            def make_request():
                return client.post("/documents/", json={
                    "title": "Concurrent Test Document",
                    "content": "Concurrent test content",
                    "content_type": "text"
                })
            
            # Make 10 concurrent requests
            with ThreadPoolExecutor(max_workers=10) as executor:
                start_time = time.time()
                futures = [executor.submit(make_request) for _ in range(10)]
                responses = [future.result() for future in futures]
                end_time = time.time()
            
            # Assert
            assert all(response.status_code == 201 for response in responses)
            assert (end_time - start_time) < 5.0  # Should complete within 5 seconds

    @patch('app.core.user_context.get_authenticated_user_context')
    def test_large_document_handling(self, mock_get_user, mock_user_context):
        """Test that the API can handle large documents efficiently"""
        # Arrange
        mock_get_user.return_value = mock_user_context
        
        # Mock document creation
        with patch('app.services.document_service.DocumentService.create_document') as mock_create:
            mock_doc = Document(
                id="large-doc",
                title="Large Document",
                content="x" * 100000,  # 100KB content
                user_id="perf-test-uid"
            )
            mock_create.return_value = mock_doc
            
            # Act
            start_time = time.time()
            response = client.post("/documents/", json={
                "title": "Large Document",
                "content": "x" * 100000,
                "content_type": "text"
            })
            end_time = time.time()
            
            # Assert
            assert response.status_code == 201
            assert (end_time - start_time) < 2.0  # Should complete within 2 seconds

    @patch('app.core.user_context.get_authenticated_user_context')
    def test_pagination_performance(self, mock_get_user, mock_user_context):
        """Test that pagination performs efficiently"""
        # Arrange
        mock_get_user.return_value = mock_user_context
        
        # Mock paginated documents
        with patch('app.services.document_service.DocumentService.get_user_documents') as mock_get_docs:
            mock_docs = [
                Document(
                    id=f"page-doc-{i}",
                    title=f"Page Document {i}",
                    user_id="perf-test-uid"
                ) for i in range(20)
            ]
            mock_get_docs.return_value = (mock_docs, 1000)
            
            # Act
            start_time = time.time()
            response = client.get("/documents/?page=1&page_size=20")
            end_time = time.time()
            
            # Assert
            assert response.status_code == 200
            assert (end_time - start_time) < 1.0  # Should complete within 1 second

    @patch('app.core.user_context.get_authenticated_user_context')
    def test_search_performance(self, mock_get_user, mock_user_context):
        """Test that search operations perform efficiently"""
        # Arrange
        mock_get_user.return_value = mock_user_context
        
        # Mock search results
        with patch('app.services.bookmark_service.BookmarkService.find_bookmark') as mock_find:
            mock_bookmark = Bookmark(
                id="search-bookmark",
                title="Search Test Bookmark",
                url="https://example.com/search",
                user_id="perf-test-uid"
            )
            mock_find.return_value = mock_bookmark
            
            # Act
            start_time = time.time()
            response = client.get("/bookmarks/find?query=test")
            end_time = time.time()
            
            # Assert
            assert response.status_code == 200
            assert (end_time - start_time) < 1.0  # Should complete within 1 second

    @patch('app.core.user_context.get_authenticated_user_context')
    def test_update_performance(self, mock_get_user, mock_user_context):
        """Test that update operations perform efficiently"""
        # Arrange
        mock_get_user.return_value = mock_user_context
        
        # Mock document update
        with patch('app.services.document_service.DocumentService.update_document') as mock_update:
            mock_doc = Document(
                id="update-doc",
                title="Updated Document",
                content="Updated content",
                user_id="perf-test-uid"
            )
            mock_update.return_value = mock_doc
            
            # Act
            start_time = time.time()
            response = client.put("/documents/update-doc", json={
                "title": "Updated Document",
                "content": "Updated content"
            })
            end_time = time.time()
            
            # Assert
            assert response.status_code == 200
            assert (end_time - start_time) < 1.0  # Should complete within 1 second

    @patch('app.core.user_context.get_authenticated_user_context')
    def test_delete_performance(self, mock_get_user, mock_user_context):
        """Test that delete operations perform efficiently"""
        # Arrange
        mock_get_user.return_value = mock_user_context
        
        # Mock document deletion
        with patch('app.services.document_service.DocumentService.delete_document') as mock_delete:
            mock_delete.return_value = True
            
            # Act
            start_time = time.time()
            response = client.delete("/documents/delete-doc")
            end_time = time.time()
            
            # Assert
            assert response.status_code == 204
            assert (end_time - start_time) < 1.0  # Should complete within 1 second
