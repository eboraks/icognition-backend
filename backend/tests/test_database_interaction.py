"""
Database interaction tests for the API endpoints
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from app.main import app
from app.models import User, Document, Bookmark
from datetime import datetime
from sqlmodel import SQLModel, create_engine, Session
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.ext.asyncio import AsyncEngine

client = TestClient(app)


class TestDatabaseInteraction:
    """Database interaction tests for API endpoints"""

    @pytest.fixture
    def mock_user(self):
        """Mock user for database testing"""
        return User(
            id="db-test-uid",
            email="db@example.com",
            display_name="Database Test User",
            is_active=True,
            is_verified=True
        )

    @pytest.fixture
    def mock_user_context(self, mock_user):
        """Mock user context for database testing"""
        from app.core.user_context import UserContext
        return UserContext(user=mock_user)

    @patch('app.core.user_context.get_authenticated_user_context')
    @patch('app.db.database.get_session')
    def test_document_database_creation(self, mock_get_session, mock_get_user, mock_user_context):
        """Test document creation with database interaction"""
        # Arrange
        mock_get_user.return_value = mock_user_context
        
        # Mock database session
        mock_session = MagicMock()
        mock_get_session.return_value = mock_session
        
        # Mock document creation
        with patch('app.services.document_service.DocumentService.create_document') as mock_create:
            mock_doc = Document(
                id="db-doc-123",
                title="Database Document",
                content="Database content",
                user_id="db-test-uid"
            )
            mock_create.return_value = mock_doc
            
            # Act
            response = client.post("/documents/", json={
                "title": "Database Document",
                "content": "Database content",
                "content_type": "text"
            })
            
            # Assert
            assert response.status_code == 201
            data = response.json()
            assert data["id"] == "db-doc-123"
            assert data["title"] == "Database Document"
            mock_create.assert_called_once()

    @patch('app.core.user_context.get_authenticated_user_context')
    @patch('app.db.database.get_session')
    def test_bookmark_database_creation(self, mock_get_session, mock_get_user, mock_user_context):
        """Test bookmark creation with database interaction"""
        # Arrange
        mock_get_user.return_value = mock_user_context
        
        # Mock database session
        mock_session = MagicMock()
        mock_get_session.return_value = mock_session
        
        # Mock bookmark creation
        with patch('app.services.bookmark_service.BookmarkService.create_bookmark') as mock_create:
            mock_bookmark = Bookmark(
                id="db-bookmark-123",
                title="Database Bookmark",
                url="https://example.com/db",
                user_id="db-test-uid"
            )
            mock_create.return_value = mock_bookmark
            
            # Act
            response = client.post("/bookmarks/", json={
                "title": "Database Bookmark",
                "url": "https://example.com/db"
            })
            
            # Assert
            assert response.status_code == 201
            data = response.json()
            assert data["id"] == "db-bookmark-123"
            assert data["title"] == "Database Bookmark"
            mock_create.assert_called_once()

    @patch('app.core.user_context.get_authenticated_user_context')
    @patch('app.db.database.get_session')
    def test_document_database_retrieval(self, mock_get_session, mock_get_user, mock_user_context):
        """Test document retrieval with database interaction"""
        # Arrange
        mock_get_user.return_value = mock_user_context
        
        # Mock database session
        mock_session = MagicMock()
        mock_get_session.return_value = mock_session
        
        # Mock document retrieval
        with patch('app.services.document_service.DocumentService.get_by_id') as mock_get:
            mock_doc = Document(
                id="db-doc-123",
                title="Database Document",
                content="Database content",
                user_id="db-test-uid"
            )
            mock_get.return_value = mock_doc
            
            # Act
            response = client.get("/documents/db-doc-123")
            
            # Assert
            assert response.status_code == 200
            data = response.json()
            assert data["id"] == "db-doc-123"
            assert data["title"] == "Database Document"
            mock_get.assert_called_once_with("db-doc-123")

    @patch('app.core.user_context.get_authenticated_user_context')
    @patch('app.db.database.get_session')
    def test_bookmark_database_retrieval(self, mock_get_session, mock_get_user, mock_user_context):
        """Test bookmark retrieval with database interaction"""
        # Arrange
        mock_get_user.return_value = mock_user_context
        
        # Mock database session
        mock_session = MagicMock()
        mock_get_session.return_value = mock_session
        
        # Mock bookmark retrieval
        with patch('app.services.bookmark_service.BookmarkService.get_by_id') as mock_get:
            mock_bookmark = Bookmark(
                id="db-bookmark-123",
                title="Database Bookmark",
                url="https://example.com/db",
                user_id="db-test-uid"
            )
            mock_get.return_value = mock_bookmark
            
            # Act
            response = client.get("/bookmarks/db-bookmark-123")
            
            # Assert
            assert response.status_code == 200
            data = response.json()
            assert data["id"] == "db-bookmark-123"
            assert data["title"] == "Database Bookmark"
            mock_get.assert_called_once_with("db-bookmark-123")

    @patch('app.core.user_context.get_authenticated_user_context')
    @patch('app.db.database.get_session')
    def test_document_database_update(self, mock_get_session, mock_get_user, mock_user_context):
        """Test document update with database interaction"""
        # Arrange
        mock_get_user.return_value = mock_user_context
        
        # Mock database session
        mock_session = MagicMock()
        mock_get_session.return_value = mock_session
        
        # Mock document update
        with patch('app.services.document_service.DocumentService.update_document') as mock_update:
            updated_doc = Document(
                id="db-doc-123",
                title="Updated Database Document",
                content="Updated database content",
                user_id="db-test-uid"
            )
            mock_update.return_value = updated_doc
            
            # Act
            response = client.put("/documents/db-doc-123", json={
                "title": "Updated Database Document",
                "content": "Updated database content"
            })
            
            # Assert
            assert response.status_code == 200
            data = response.json()
            assert data["title"] == "Updated Database Document"
            mock_update.assert_called_once()

    @patch('app.core.user_context.get_authenticated_user_context')
    @patch('app.db.database.get_session')
    def test_bookmark_database_update(self, mock_get_session, mock_get_user, mock_user_context):
        """Test bookmark update with database interaction"""
        # Arrange
        mock_get_user.return_value = mock_user_context
        
        # Mock database session
        mock_session = MagicMock()
        mock_get_session.return_value = mock_session
        
        # Mock bookmark update
        with patch('app.services.bookmark_service.BookmarkService.update_bookmark') as mock_update:
            updated_bookmark = Bookmark(
                id="db-bookmark-123",
                title="Updated Database Bookmark",
                url="https://example.com/updated",
                user_id="db-test-uid"
            )
            mock_update.return_value = updated_bookmark
            
            # Act
            response = client.put("/bookmarks/db-bookmark-123", json={
                "title": "Updated Database Bookmark",
                "url": "https://example.com/updated"
            })
            
            # Assert
            assert response.status_code == 200
            data = response.json()
            assert data["title"] == "Updated Database Bookmark"
            mock_update.assert_called_once()

    @patch('app.core.user_context.get_authenticated_user_context')
    @patch('app.db.database.get_session')
    def test_document_database_deletion(self, mock_get_session, mock_get_user, mock_user_context):
        """Test document deletion with database interaction"""
        # Arrange
        mock_get_user.return_value = mock_user_context
        
        # Mock database session
        mock_session = MagicMock()
        mock_get_session.return_value = mock_session
        
        # Mock document deletion
        with patch('app.services.document_service.DocumentService.delete_document') as mock_delete:
            mock_delete.return_value = True
            
            # Act
            response = client.delete("/documents/db-doc-123")
            
            # Assert
            assert response.status_code == 204
            mock_delete.assert_called_once_with("db-doc-123")

    @patch('app.core.user_context.get_authenticated_user_context')
    @patch('app.db.database.get_session')
    def test_bookmark_database_deletion(self, mock_get_session, mock_get_user, mock_user_context):
        """Test bookmark deletion with database interaction"""
        # Arrange
        mock_get_user.return_value = mock_user_context
        
        # Mock database session
        mock_session = MagicMock()
        mock_get_session.return_value = mock_session
        
        # Mock bookmark deletion
        with patch('app.services.bookmark_service.BookmarkService.delete_bookmark') as mock_delete:
            mock_delete.return_value = True
            
            # Act
            response = client.delete("/bookmarks/db-bookmark-123")
            
            # Assert
            assert response.status_code == 204
            mock_delete.assert_called_once_with("db-bookmark-123")

    @patch('app.core.user_context.get_authenticated_user_context')
    @patch('app.db.database.get_session')
    def test_document_database_listing(self, mock_get_session, mock_get_user, mock_user_context):
        """Test document listing with database interaction"""
        # Arrange
        mock_get_user.return_value = mock_user_context
        
        # Mock database session
        mock_session = MagicMock()
        mock_get_session.return_value = mock_session
        
        # Mock document listing
        with patch('app.services.document_service.DocumentService.get_user_documents') as mock_get_docs:
            mock_docs = [
                Document(
                    id=f"db-doc-{i}",
                    title=f"Database Document {i}",
                    user_id="db-test-uid"
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
    @patch('app.db.database.get_session')
    def test_bookmark_database_listing(self, mock_get_session, mock_get_user, mock_user_context):
        """Test bookmark listing with database interaction"""
        # Arrange
        mock_get_user.return_value = mock_user_context
        
        # Mock database session
        mock_session = MagicMock()
        mock_get_session.return_value = mock_session
        
        # Mock bookmark listing
        with patch('app.services.bookmark_service.BookmarkService.get_user_bookmarks') as mock_get_bookmarks:
            mock_bookmarks = [
                Bookmark(
                    id=f"db-bookmark-{i}",
                    title=f"Database Bookmark {i}",
                    url=f"https://example.com/db{i}",
                    user_id="db-test-uid"
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
    @patch('app.db.database.get_session')
    def test_document_database_filtering(self, mock_get_session, mock_get_user, mock_user_context):
        """Test document filtering with database interaction"""
        # Arrange
        mock_get_user.return_value = mock_user_context
        
        # Mock database session
        mock_session = MagicMock()
        mock_get_session.return_value = mock_session
        
        # Mock document filtering
        with patch('app.services.document_service.DocumentService.get_by_status') as mock_get_by_status:
            mock_docs = [
                Document(
                    id="db-doc-123",
                    title="Database Document",
                    status="processed",
                    user_id="db-test-uid"
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
    @patch('app.db.database.get_session')
    def test_bookmark_database_search(self, mock_get_session, mock_get_user, mock_user_context):
        """Test bookmark search with database interaction"""
        # Arrange
        mock_get_user.return_value = mock_user_context
        
        # Mock database session
        mock_session = MagicMock()
        mock_get_session.return_value = mock_session
        
        # Mock bookmark search
        with patch('app.services.bookmark_service.BookmarkService.find_bookmark') as mock_find:
            mock_bookmark = Bookmark(
                id="db-bookmark-123",
                title="Database Bookmark",
                url="https://example.com/db",
                user_id="db-test-uid"
            )
            mock_find.return_value = mock_bookmark
            
            # Act
            response = client.get("/bookmarks/find?query=database")
            
            # Assert
            assert response.status_code == 200
            data = response.json()
            assert data["id"] == "db-bookmark-123"
            assert data["title"] == "Database Bookmark"
            mock_find.assert_called_once_with("database")

    @patch('app.core.user_context.get_authenticated_user_context')
    @patch('app.db.database.get_session')
    def test_document_database_content_retrieval(self, mock_get_session, mock_get_user, mock_user_context):
        """Test document content retrieval with database interaction"""
        # Arrange
        mock_get_user.return_value = mock_user_context
        
        # Mock database session
        mock_session = MagicMock()
        mock_get_session.return_value = mock_session
        
        # Mock content retrieval
        with patch('app.services.document_service.DocumentService.get_content') as mock_get_content:
            mock_content = {
                "document_id": "db-doc-123",
                "content": "Database document content"
            }
            mock_get_content.return_value = mock_content
            
            # Act
            response = client.get("/documents/db-doc-123/content")
            
            # Assert
            assert response.status_code == 200
            data = response.json()
            assert data["document_id"] == "db-doc-123"
            assert data["content"] == "Database document content"
            mock_get_content.assert_called_once_with("db-doc-123")

    @patch('app.core.user_context.get_authenticated_user_context')
    @patch('app.db.database.get_session')
    def test_bookmark_database_reanalysis(self, mock_get_session, mock_get_user, mock_user_context):
        """Test bookmark reanalysis with database interaction"""
        # Arrange
        mock_get_user.return_value = mock_user_context
        
        # Mock database session
        mock_session = MagicMock()
        mock_get_session.return_value = mock_session
        
        # Mock reanalysis
        with patch('app.services.bookmark_service.BookmarkService.reanalyze_bookmark') as mock_reanalyze:
            mock_reanalyze.return_value = True
            
            # Act
            response = client.post("/bookmarks/db-bookmark-123/re-analyze")
            
            # Assert
            assert response.status_code == 200
            data = response.json()
            assert data["message"] == "Analysis re-triggered for bookmark"
            assert data["bookmark_id"] == "db-bookmark-123"
            mock_reanalyze.assert_called_once_with("db-bookmark-123")

    @patch('app.core.user_context.get_authenticated_user_context')
    @patch('app.db.database.get_session')
    def test_document_database_status_patch(self, mock_get_session, mock_get_user, mock_user_context):
        """Test document status patching with database interaction"""
        # Arrange
        mock_get_user.return_value = mock_user_context
        
        # Mock database session
        mock_session = MagicMock()
        mock_get_session.return_value = mock_session
        
        # Mock status patching
        with patch('app.services.document_service.DocumentService.patch_status') as mock_patch_status:
            mock_status = {
                "document_id": "db-doc-123",
                "status": "updated"
            }
            mock_patch_status.return_value = mock_status
            
            # Act
            response = client.patch("/documents/db-doc-123/status", json={
                "status": "updated"
            })
            
            # Assert
            assert response.status_code == 200
            data = response.json()
            assert data["document_id"] == "db-doc-123"
            assert data["status"] == "updated"
            mock_patch_status.assert_called_once()

    @patch('app.core.user_context.get_authenticated_user_context')
    @patch('app.db.database.get_session')
    def test_document_database_fetch(self, mock_get_session, mock_get_user, mock_user_context):
        """Test document content fetching with database interaction"""
        # Arrange
        mock_get_user.return_value = mock_user_context
        
        # Mock database session
        mock_session = MagicMock()
        mock_get_session.return_value = mock_session
        
        # Mock content fetching
        with patch('app.services.document_service.DocumentService.fetch_content') as mock_fetch:
            fetched_doc = Document(
                id="db-doc-123",
                title="Database Document",
                status="fetching",
                user_id="db-test-uid"
            )
            mock_fetch.return_value = fetched_doc
            
            # Act
            response = client.post("/documents/db-doc-123/fetch")
            
            # Assert
            assert response.status_code == 200
            data = response.json()
            assert data["id"] == "db-doc-123"
            assert data["status"] == "fetching"
            mock_fetch.assert_called_once_with("db-doc-123")

    @patch('app.core.user_context.get_authenticated_user_context')
    @patch('app.db.database.get_session')
    def test_document_database_embedding(self, mock_get_session, mock_get_user, mock_user_context):
        """Test document embedding generation with database interaction"""
        # Arrange
        mock_get_user.return_value = mock_user_context
        
        # Mock database session
        mock_session = MagicMock()
        mock_get_session.return_value = mock_session
        
        # Mock embedding generation
        with patch('app.services.document_service.DocumentService.generate_embedding') as mock_embed:
            embedded_doc = Document(
                id="db-doc-123",
                title="Database Document",
                status="embedding",
                user_id="db-test-uid"
            )
            mock_embed.return_value = embedded_doc
            
            # Act
            response = client.post("/documents/db-doc-123/embed")
            
            # Assert
            assert response.status_code == 200
            data = response.json()
            assert data["id"] == "db-doc-123"
            assert data["status"] == "embedding"
            mock_embed.assert_called_once_with("db-doc-123")
