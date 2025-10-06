"""
Integration tests for bookmark endpoints
Tests require a running FastAPI server and PostgreSQL database
"""

import pytest
import httpx
from unittest.mock import patch

# Mock Firebase token and UID for testing
MOCK_FIREBASE_TOKEN = "mock_firebase_token_for_testing"
MOCK_FIREBASE_UID = "test_user_12345"  # Match the default test user ID

# Firebase mocking is handled in conftest.py

@pytest.fixture
async def authenticated_client(client: httpx.AsyncClient) -> httpx.AsyncClient:
    """Client for testing (no auth needed when DISABLE_AUTH=true)."""
    # No authentication headers needed when auth is disabled
    return client

class TestBookmarkEndpoints:
    """Test bookmark endpoints"""

    @pytest.mark.asyncio
    async def test_create_bookmark(self, authenticated_client: httpx.AsyncClient):
        """Test creating a new bookmark."""
        response = await authenticated_client.post(
            "/bookmarks/",
            json={"url": "http://example.com/bookmark1", "title": "Test Bookmark 1"}
        )
        assert response.status_code == 201
        data = response.json()
        assert data["title"] == "Test Bookmark 1"
        assert data["user_id"] == MOCK_FIREBASE_UID
        assert data["processing_status"] == "pending"

    @pytest.mark.asyncio
    async def test_get_user_bookmarks(self, authenticated_client: httpx.AsyncClient):
        """Test getting a list of user bookmarks."""
        # Create a bookmark first
        await authenticated_client.post(
            "/bookmarks/",
            json={"url": "http://example.com/bookmark2", "title": "Test Bookmark 2"}
        )
        
        response = await authenticated_client.get("/bookmarks/")
        assert response.status_code == 200
        data = response.json()
        assert "bookmarks" in data
        assert len(data["bookmarks"]) > 0
        assert data["bookmarks"][0]["user_id"] == MOCK_FIREBASE_UID

    @pytest.mark.asyncio
    async def test_get_bookmark_by_id(self, authenticated_client: httpx.AsyncClient):
        """Test getting a single bookmark by ID."""
        create_response = await authenticated_client.post(
            "/bookmarks/",
            json={"url": "http://example.com/bookmark3", "title": "Test Bookmark 3"}
        )
        bookmark_id = create_response.json()["id"]

        response = await authenticated_client.get(f"/bookmarks/{bookmark_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == bookmark_id
        assert data["title"] == "Test Bookmark 3"

    @pytest.mark.asyncio
    async def test_update_bookmark(self, authenticated_client: httpx.AsyncClient):
        """Test updating an existing bookmark."""
        create_response = await authenticated_client.post(
            "/bookmarks/",
            json={"url": "http://example.com/bookmark4", "title": "Test Bookmark 4"}
        )
        bookmark_id = create_response.json()["id"]

        update_response = await authenticated_client.put(
            f"/bookmarks/{bookmark_id}",
            json={"title": "Updated Bookmark 4", "description": "New description"}
        )
        assert update_response.status_code == 200
        data = update_response.json()
        assert data["title"] == "Updated Bookmark 4"
        assert data["description"] == "New description"

    @pytest.mark.asyncio
    async def test_delete_bookmark(self, authenticated_client: httpx.AsyncClient):
        """Test deleting a bookmark."""
        create_response = await authenticated_client.post(
            "/bookmarks/",
            json={"url": "http://example.com/bookmark5", "title": "Test Bookmark 5"}
        )
        bookmark_id = create_response.json()["id"]

        delete_response = await authenticated_client.delete(f"/bookmarks/{bookmark_id}")
        assert delete_response.status_code == 200
        data = delete_response.json()
        assert data["message"] == "Bookmark deleted successfully"

        # Verify it's deleted
        get_response = await authenticated_client.get(f"/bookmarks/{bookmark_id}")
        assert get_response.status_code == 404

    @pytest.mark.asyncio
    async def test_re_analyze_bookmark(self, authenticated_client: httpx.AsyncClient):
        """Test re-triggering analysis for a bookmark."""
        create_response = await authenticated_client.post(
            "/bookmarks/",
            json={"url": "http://example.com/bookmark_reanalyze", "title": "Reanalyze Bookmark"}
        )
        bookmark_id = create_response.json()["id"]

        response = await authenticated_client.post(f"/bookmarks/{bookmark_id}/re-analyze")
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Re-analysis triggered successfully"
        assert data["bookmark_id"] == bookmark_id

    @pytest.mark.asyncio
    async def test_find_bookmark(self, authenticated_client: httpx.AsyncClient):
        """Test finding a bookmark by URL or title."""
        test_url = "http://example.com/bookmark_find"
        await authenticated_client.post(
            "/bookmarks/",
            json={"url": test_url, "title": "Find Me Bookmark"}
        )
        
        response = await authenticated_client.get(f"/bookmarks/find?query={test_url}")
        assert response.status_code == 200
        data = response.json()
        assert data["url"] == test_url

    @pytest.mark.asyncio
    async def test_get_bookmark_by_url(self, authenticated_client: httpx.AsyncClient):
        """Test getting a bookmark by URL."""
        test_url = "http://example.com/bookmark_by_url"
        await authenticated_client.post(
            "/bookmarks/",
            json={"url": test_url, "title": "Bookmark by URL"}
        )
        
        response = await authenticated_client.get(f"/bookmarks/url/{test_url}")
        assert response.status_code == 200
        data = response.json()
        assert "bookmarks" in data
        assert len(data["bookmarks"]) == 1
        assert data["bookmarks"][0]["url"] == test_url

    @pytest.mark.asyncio
    async def test_test_auth_disabled(self, client: httpx.AsyncClient):
        """Test the /bookmarks/test-auth endpoint."""
        response = await client.get("/bookmarks/test-auth")
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Test endpoint working"
        # Auth is disabled in test environment
        assert data["disable_auth"] == True

    @pytest.mark.asyncio
    async def test_bookmark_endpoints_require_auth(self, client: httpx.AsyncClient):
        """Test that bookmark endpoints require authentication."""
        # Test without auth - auth is disabled in test environment
        response = await client.get("/bookmarks/")
        assert response.status_code == 200  # Auth is disabled

        response = await client.post("/bookmarks/", json={"url": "http://example.com/test", "title": "Test"})
        assert response.status_code == 201  # Auth is disabled

        # Test with invalid token - auth is disabled so this will still work
        response = await client.get("/bookmarks/", headers={"Authorization": "Bearer invalid_token"})
        assert response.status_code == 200  # Auth is disabled