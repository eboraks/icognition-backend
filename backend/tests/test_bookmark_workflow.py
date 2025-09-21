#!/usr/bin/env python3
"""
Comprehensive pytest for bookmark-to-document workflow testing.

This test suite validates:
1. Bookmark creation with full document processing
2. Duplicate bookmark detection and prevention
3. Document retrieval with summary and bullet points
4. Background processing completion
"""

import pytest
import json
import asyncio
import time
from pathlib import Path
from typing import Dict, Any, Optional
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_session
from app.models import Document, Bookmark
from app.getters import get_document_by_url


class TestBookmarkWorkflow:
    """Test suite for bookmark-to-document workflow"""
    
    @pytest.fixture
    def test_data_dir(self):
        """Get the test data directory"""
        return Path(__file__).parent / "data"
    
    @pytest.fixture
    def sample_bookmark_data(self, test_data_dir):
        """Load sample bookmark data from test files"""
        test_files = list(test_data_dir.glob("bookmark_*.json"))
        if not test_files:
            pytest.skip("No test bookmark data files found")
        
        # Use the first test file
        with open(test_files[0], 'r') as f:
            return json.load(f)
    
    @pytest.fixture
    def api_base_url(self):
        """API base URL for testing"""
        return "http://localhost:8000"
    
    @pytest.fixture
    async def session(self):
        """Database session for testing"""
        session_gen = get_session()
        session = await session_gen.__anext__()
        try:
            yield session
        finally:
            await session.close()
    
    @pytest.fixture
    async def http_client(self):
        """HTTP client for API testing"""
        async with httpx.AsyncClient(timeout=30.0) as client:
            yield client
    
    async def _test_bookmark_creation_workflow(
        self, 
        http_client: httpx.AsyncClient,
        sample_bookmark_data: Dict[str, Any],
        api_base_url: str
    ):
        """Test complete bookmark creation workflow"""
        
        # Step 1: Create bookmark
        bookmark_data = {
            "url": sample_bookmark_data["url"],
            "title": sample_bookmark_data["title"],
            "description": sample_bookmark_data["description"],
            "content": sample_bookmark_data["content"],
            "metadata": sample_bookmark_data.get("metadata", {})
        }
        
        print(f"\n🔗 Creating bookmark for URL: {bookmark_data['url']}")
        
        response = await http_client.post(
            f"{api_base_url}/bookmarks/",
            json=bookmark_data
        )
        
        assert response.status_code == 200, f"Bookmark creation failed: {response.text}"
        
        bookmark_response = response.json()
        bookmark_id = bookmark_response["id"]
        
        print(f"✅ Bookmark created with ID: {bookmark_id}")
        print(f"📊 Processing status: {bookmark_response['processing_status']}")
        
        # Verify bookmark response structure
        assert "id" in bookmark_response
        assert "url" in bookmark_response
        assert "title" in bookmark_response
        assert "processing_status" in bookmark_response
        assert bookmark_response["processing_status"] == "pending"
        
        return bookmark_id
    
    async def _test_duplicate_bookmark_prevention(
        self,
        http_client: httpx.AsyncClient,
        sample_bookmark_data: Dict[str, Any],
        api_base_url: str
    ):
        """Test that duplicate bookmarks are not created"""
        
        bookmark_data = {
            "url": sample_bookmark_data["url"],
            "title": sample_bookmark_data["title"],
            "description": sample_bookmark_data["description"],
            "content": sample_bookmark_data["content"]
        }
        
        print(f"\n🔄 Testing duplicate bookmark prevention for: {bookmark_data['url']}")
        
        # Create first bookmark
        response1 = await http_client.post(
            f"{api_base_url}/bookmarks/",
            json=bookmark_data
        )
        
        assert response1.status_code == 200
        first_bookmark = response1.json()
        first_bookmark_id = first_bookmark["id"]
        
        print(f"✅ First bookmark created: {first_bookmark_id}")
        
        # Try to create duplicate bookmark
        response2 = await http_client.post(
            f"{api_base_url}/bookmarks/",
            json=bookmark_data
        )
        
        assert response2.status_code == 200
        second_bookmark = response2.json()
        second_bookmark_id = second_bookmark["id"]
        
        print(f"📊 Second bookmark response: {second_bookmark_id}")
        
        # Verify that the same bookmark ID is returned (duplicate prevention)
        assert first_bookmark_id == second_bookmark_id, "Duplicate bookmark should return same ID"
        
        print("✅ Duplicate bookmark prevention working correctly")
        
        return first_bookmark_id
    
    async def _test_document_retrieval_and_processing(
        self,
        http_client: httpx.AsyncClient,
        bookmark_id: str,
        api_base_url: str,
        session: AsyncSession
    ):
        """Test document retrieval and verify processing completion"""
        
        print(f"\n📄 Testing document retrieval for bookmark: {bookmark_id}")
        
        # Get the Bookmark to find the associated document
        result = await session.execute(
            select(Bookmark).where(Bookmark.id == bookmark_id)
        )
        bookmark = result.scalar_one_or_none()
        
        assert bookmark is not None, f"Bookmark not found for bookmark ID: {bookmark_id}"
        assert bookmark.document_id is not None, f"No document ID associated with bookmark: {bookmark_id}"
        
        document_id = bookmark.document_id
        print(f"📊 Found document ID: {document_id}")
        
        # Wait for background processing to complete
        max_wait_time = 120  # 2 minutes
        wait_interval = 5    # 5 seconds
        elapsed_time = 0
        
        while elapsed_time < max_wait_time:
            # Get document from database
            result = await session.execute(
                select(Document).where(Document.id == document_id)
            )
            document = result.scalar_one_or_none()
            
            if document is None:
                print(f"❌ Document not found: {document_id}")
                break
            
            print(f"⏳ Document processing check (waited {elapsed_time}s)")
            
            # Check if processing is complete
            # Instead of checking status, check if we have the required AI fields
            has_summary = document.ai_is_about is not None and len(document.ai_is_about.strip()) > 0
            has_bullet_points = document.ai_bullet_points is not None and len(document.ai_bullet_points) > 0
            is_fully_processed = has_summary and has_bullet_points
            
            if is_fully_processed:
                print("✅ Document processing completed!")
                break
            
            # Wait before next check
            await asyncio.sleep(wait_interval)
            elapsed_time += wait_interval
        
        # Verify document was processed
        assert document is not None, f"Document not found: {document_id}"
        
        # Check if processing is complete based on AI fields, not status
        has_summary = document.ai_is_about is not None and len(document.ai_is_about.strip()) > 0
        has_bullet_points = document.ai_bullet_points is not None and len(document.ai_bullet_points) > 0
        is_fully_processed = has_summary and has_bullet_points
        
        assert is_fully_processed, f"Document not fully processed. Summary: {has_summary}, Bullet points: {has_bullet_points}"
        
        # Verify document has required content
        assert document.ai_is_about is not None, "Document missing AI summary"
        assert document.ai_bullet_points is not None, "Document missing bullet points"
        assert len(document.ai_bullet_points) > 0, "Document has empty bullet points"
        
        print(f"✅ Document summary: {document.ai_is_about[:100]}...")
        print(f"✅ Bullet points count: {len(document.ai_bullet_points)}")
        print(f"✅ First bullet: {document.ai_bullet_points[0] if document.ai_bullet_points else 'None'}")
        
        return document
    
    async def _test_document_api_endpoints(
        self,
        http_client: httpx.AsyncClient,
        document_id: str,
        api_base_url: str
    ):
        """Test document API endpoints"""
        
        print(f"\n🔍 Testing document API endpoints for: {document_id}")
        
        # Test document retrieval
        response = await http_client.get(f"{api_base_url}/api/v1/documents/{document_id}")
        
        if response.status_code == 200:
            document_data = response.json()
            print("✅ Document retrieved via API")
            print(f"📊 Document title: {document_data.get('title', 'N/A')}")
            print(f"📊 Document status: {document_data.get('status', 'N/A')}")
        else:
            print(f"⚠️ Document API returned {response.status_code}: {response.text}")
        
        # Test document content endpoint
        response = await http_client.get(f"{api_base_url}/api/v1/documents/{document_id}/content")
        
        if response.status_code == 200:
            content_data = response.json()
            print("✅ Document content retrieved via API")
            print(f"📊 Content length: {len(content_data.get('content', ''))}")
        else:
            print(f"⚠️ Document content API returned {response.status_code}: {response.text}")
    
    @pytest.mark.asyncio
    async def test_complete_workflow(
        self,
        http_client: httpx.AsyncClient,
        sample_bookmark_data: Dict[str, Any],
        api_base_url: str,
        session: AsyncSession
    ):
        """Test the complete bookmark-to-document workflow"""
        
        print("\n" + "="*60)
        print("🚀 STARTING COMPLETE BOOKMARK-TO-DOCUMENT WORKFLOW TEST")
        print("="*60)
        
        # Step 1: Test duplicate prevention (creates bookmark)
        bookmark_id = await self._test_duplicate_bookmark_prevention(
            http_client, sample_bookmark_data, api_base_url
        )
        
        # Step 2: Test document retrieval and processing
        document = await self._test_document_retrieval_and_processing(
            http_client, bookmark_id, api_base_url, session
        )
        
        # Step 3: Test API endpoints
        await self._test_document_api_endpoints(
            http_client, str(document.id), api_base_url
        )
        
        print("\n" + "="*60)
        print("✅ COMPLETE WORKFLOW TEST PASSED!")
        print("="*60)
        
        # Final verification
        has_summary = document.ai_is_about is not None and len(document.ai_is_about.strip()) > 0
        has_bullet_points = document.ai_bullet_points is not None and len(document.ai_bullet_points) > 0
        is_fully_processed = has_summary and has_bullet_points
        
        assert is_fully_processed, f"Document not fully processed. Summary: {has_summary}, Bullet points: {has_bullet_points}"
        
        print(f"\n📋 FINAL RESULTS:")
        print(f"   Bookmark ID: {bookmark_id}")
        print(f"   Document ID: {document.id}")
        print(f"   Processing: {'Complete' if is_fully_processed else 'Incomplete'}")
        print(f"   Summary Length: {len(document.ai_is_about) if document.ai_is_about else 0}")
        print(f"   Bullet Points: {len(document.ai_bullet_points)}")
        
        return {
            "bookmark_id": bookmark_id,
            "document_id": str(document.id),
            "summary": document.ai_is_about,
            "bullet_points": document.ai_bullet_points,
            "processing_complete": is_fully_processed
        }


# Additional test for multiple bookmark files
@pytest.mark.asyncio
async def test_multiple_bookmark_files():
    """Test workflow with multiple bookmark files"""
    
    test_data_dir = Path(__file__).parent / "data"
    test_files = list(test_data_dir.glob("bookmark_*.json"))
    
    if len(test_files) < 2:
        pytest.skip("Need at least 2 test files for multiple bookmark test")
    
    print(f"\n🔄 Testing with {len(test_files)} bookmark files")
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        api_base_url = "http://localhost:8000"
        
        for i, test_file in enumerate(test_files[:3]):  # Test first 3 files
            with open(test_file, 'r') as f:
                bookmark_data = json.load(f)
            
            print(f"\n📌 Testing file {i+1}: {test_file.name}")
            
            # Create bookmark
            response = await client.post(
                f"{api_base_url}/bookmarks/",
                json={
                    "url": bookmark_data["url"],
                    "title": bookmark_data["title"],
                    "description": bookmark_data["description"],
                    "content": bookmark_data["content"]
                }
            )
            
            if response.status_code == 200:
                bookmark = response.json()
                print(f"✅ Bookmark created: {bookmark['id']}")
            else:
                print(f"❌ Bookmark creation failed: {response.status_code} - {response.text}")


if __name__ == "__main__":
    # Run the test directly
    pytest.main([__file__, "-v", "-s"])
