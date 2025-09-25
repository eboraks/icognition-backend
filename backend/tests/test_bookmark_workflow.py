"""
Test suite for bookmark-to-document workflow
"""

import json
import asyncio
from pathlib import Path
from typing import Dict, Any, List

import pytest
import httpx


class TestBookmarkWorkflow:
    
    @pytest.mark.asyncio
    async def test_all_json_bookmarks(self, http_client: httpx.AsyncClient, api_base_url: str):
        """Simple test: Iterate through all JSON files, create bookmarks, and check AI processing via API"""
        print("\n" + "="*60)
        print("🚀 TESTING ALL JSON BOOKMARKS VIA API")
        print("="*60)
        
        # Load all JSON files from data directory
        test_data_dir = Path(__file__).parent / "data"
        json_files = list(test_data_dir.glob("*.json"))
        
        if not json_files:
            pytest.skip("No test data files found in tests/data directory")
        
        print(f"📁 Found {len(json_files)} JSON files to test")
        
        for i, test_file in enumerate(json_files, 1):
            print(f"\n--- Testing file {i}/{len(json_files)}: {test_file.name} ---")
            
            # Load bookmark data
            with open(test_file, 'r') as f:
                bookmark_data = json.load(f)
            
            # Create bookmark via API
            print(f"📝 Creating bookmark for: {bookmark_data['url']}")
            create_response = await http_client.post(f"{api_base_url}/bookmarks/", json=bookmark_data)
            assert create_response.status_code == 200, f"Failed to create bookmark: {create_response.text}"
            
            bookmark_response = create_response.json()
            bookmark_id = bookmark_response["id"]
            document_id = bookmark_response["document_id"]
            print(f"✅ Bookmark created: {bookmark_id}")
            print(f"📄 Document ID: {document_id}")
            
            # Wait for background processing
            print("⏳ Waiting 2 seconds for background processing...")
            await asyncio.sleep(2)
            
            if document_id is None:
                print(f"❌ No document ID found in bookmark response")
                continue
                
            # Get document content via API
            doc_response = await http_client.get(f"{api_base_url}/documents/{document_id}")
            if doc_response.status_code != 200:
                print(f"❌ Failed to get document {document_id}: {doc_response.text}")
                continue
                
            document_data = doc_response.json()
            
            # Check AI processing via API response
            has_summary = document_data.get("ai_is_about") is not None and len(str(document_data.get("ai_is_about", "")).strip()) > 0
            has_bullets = document_data.get("ai_bullet_points") is not None and len(document_data.get("ai_bullet_points", [])) > 0
            
            print(f"📊 Summary: {'✅' if has_summary else '❌'}")
            print(f"📊 Bullets: {'✅' if has_bullets else '❌'}")
            
            if not has_summary or not has_bullets:
                print(f"⚠️  Document {document_id} not fully processed!")
                print(f"   ai_is_about: {document_data.get('ai_is_about')}")
                print(f"   ai_bullet_points: {document_data.get('ai_bullet_points')}")
            else:
                print(f"✅ Document {document_id} fully processed!")
        
        print(f"\n🏁 Completed testing {len(json_files)} JSON files")
    
    @pytest.mark.asyncio
    async def test_bookmark_exists(self, http_client: httpx.AsyncClient, api_base_url: str):
        """Test if bookmarks already exist for URLs in JSON files"""
        print("\n" + "="*60)
        print("🔍 TESTING BOOKMARK EXISTENCE FOR JSON FILES")
        print("="*60)
        
        # Load all JSON files from data directory
        test_data_dir = Path(__file__).parent / "data"
        json_files = list(test_data_dir.glob("*.json"))
        
        if not json_files:
            pytest.skip("No test data files found in tests/data directory")
        
        print(f"📁 Found {len(json_files)} JSON files to check")
        
        for i, test_file in enumerate(json_files, 1):
            print(f"\n--- Checking file {i}/{len(json_files)}: {test_file.name} ---")
            
            # Load bookmark data
            with open(test_file, 'r') as f:
                bookmark_data = json.load(f)
            
            url = bookmark_data['url']
            print(f"🔍 Checking if bookmark exists for: {url}")
            
            # Check if bookmark exists via API
            find_response = await http_client.get(f"{api_base_url}/bookmarks/find", params={"url": url})
            
            if find_response.status_code == 200:
                bookmark_response = find_response.json()
                bookmark_id = bookmark_response["id"]
                document_id = bookmark_response.get("document_id")
                print(f"✅ Bookmark exists: {bookmark_id}")
                if document_id:
                    print(f"📄 Document ID: {document_id}")
                else:
                    print(f"❌ No document linked to bookmark")
            elif find_response.status_code == 404:
                print(f"❌ No bookmark found for this URL")
            else:
                print(f"⚠️  Unexpected response: {find_response.status_code} - {find_response.text}")
        
        print(f"\n🏁 Completed checking {len(json_files)} JSON files")
    
    @pytest.fixture
    def api_base_url(self):
        """API base URL for testing"""
        return "http://localhost:8000"
    
    @pytest.fixture
    async def http_client(self):
        """HTTP client for API testing"""
        async with httpx.AsyncClient(timeout=30.0) as client:
            yield client