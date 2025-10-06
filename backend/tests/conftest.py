"""
Pytest configuration and fixtures for integration testing
Tests require a running FastAPI server and PostgreSQL database
"""

import pytest
import httpx
from typing import AsyncGenerator
from unittest.mock import patch, MagicMock
import os

# Mock Firebase before any imports that might use it
import sys
from unittest.mock import MagicMock

# Create a mock FirebaseAuth class
class MockFirebaseAuth:
    def __init__(self):
        self._app = None
    
    def _initialize_firebase(self):
        pass
    
    async def verify_id_token(self, token: str):
        if token == "mock_firebase_id_token" or token == "mock_firebase_token_for_testing":
            return {"uid": "test_user_12345", "email": "test@example.com", "name": "Test User", "email_verified": True}
        raise ValueError("Invalid token")

# Mock the firebase_auth module
sys.modules['app.core.firebase_auth'] = MagicMock()
sys.modules['app.core.firebase_auth'].firebase_auth = MockFirebaseAuth()

from app.models import User, Document, Bookmark


# Test configuration
BASE_URL = os.getenv("TEST_BASE_URL", "http://localhost:8000")
TEST_FIREBASE_TOKEN = os.getenv("TEST_FIREBASE_TOKEN", "mock_firebase_token_for_testing")
TEST_FIREBASE_UID = os.getenv("TEST_FIREBASE_UID", "test_user_12345")

@pytest.fixture
async def client() -> AsyncGenerator[httpx.AsyncClient, None]:
    """Create an HTTP client for testing against running FastAPI server."""
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
        yield client



@pytest.fixture
def auth_headers():
    """Create authentication headers for testing."""
    return {"Authorization": f"Bearer {TEST_FIREBASE_TOKEN}"}


@pytest.fixture
async def authenticated_client(client: httpx.AsyncClient, auth_headers: dict) -> httpx.AsyncClient:
    """Create an authenticated HTTP client for testing."""
    client.headers.update(auth_headers)
    return client


# Test data fixtures
@pytest.fixture
def sample_document_data():
    """Sample document creation data."""
    return {
        "url": "https://example.com/test",
        "title": "Test Document",
        "content_type": "url"
    }


@pytest.fixture
def sample_bookmark_data():
    """Sample bookmark creation data."""
    return {
        "url": "https://example.com/test",
        "title": "Test Bookmark",
        "description": "Test description"
    }


@pytest.fixture
def sample_html_content():
    """Sample HTML content for testing."""
    return {
        "content": "<html><body><h1>Test HTML</h1><p>This is test content</p></body></html>",
        "content_type": "html",
        "title": "HTML Document"
    }


@pytest.fixture
def sample_text_content():
    """Sample text content for testing."""
    return {
        "content": "This is plain text content for testing purposes.",
        "content_type": "text",
        "title": "Text Document"
    }


# Firebase is mocked at module level above

# Markers for different test types
def pytest_configure(config):
    """Configure pytest markers."""
    config.addinivalue_line("markers", "integration: Integration tests")
    config.addinivalue_line("markers", "auth: Authentication tests")
    config.addinivalue_line("markers", "slow: Slow running tests")
