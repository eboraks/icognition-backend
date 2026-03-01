#!/usr/bin/env python3
"""
Quick test script to validate DSPy migration for content and entity extraction
Tests on document ID 20 to verify the new services work
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from sqlalchemy import select
from app.models import Document, Entity, EntityDocument
from app.db.database import async_session
from app.services.dspy_content_service import get_dspy_content_service
from app.services.dspy_entity_service import get_dspy_entity_service
from app.services.dspy_entity_adapter import DspyEntityAdapter
from app.utils.logging import get_logger

logger = get_logger(__name__)


async def test_content_extraction(document_id: int):
    """Test DSPy content extraction on a document"""
    async with async_session() as session:
        # Load document
        result = await session.execute(
            select(Document).where(Document.id == document_id)
        )
        document = result.scalar_one_or_none()
        
        if not document:
            print(f"Document {document_id} not found")
            return
        
        print(f"\n{'='*60}")
        print(f"Testing Content Extraction on Document {document_id}")
        print(f"Title: {document.title}")
        print(f"{'='*60}\n")
        
        # Test DSPy content service
        dspy_service = get_dspy_content_service()
        
        try:
            result = await dspy_service.analyze_document_content(
                content=document.content,
                title=document.title,
                url=document.url
            )
            
            print("✓ Content extraction successful")
            print(f"\nSummary (ai_is_about): {result['summary'][:200]}...")
            print(f"\nMarkdown Content length: {len(result['markdown_content'])}")
            print(f"  Preview: {result['markdown_content'][:100]}...")
            
            print(f"\nExtracted Content Fields:")
            ec = result['extracted_content']
            print(f"  - Source Type: {ec['source_type']}")
            print(f"  - Objectivity: {ec['analysis']['objectivity']}")
            print(f"  - Tone: {ec['analysis']['tone']}")
            print(f"  - Intent: {ec['analysis']['intent']}")
            
        except Exception as e:
            print(f"✗ Content extraction failed: {e}")
            import traceback
            traceback.print_exc()


async def test_entity_extraction(document_id: int, user_id: str = "test_user"):
    """Test DSPy entity extraction on a document"""
    async with async_session() as session:
        # Load document
        result = await session.execute(
            select(Document).where(Document.id == document_id)
        )
        document = result.scalar_one_or_none()
        
        if not document:
            print(f"Document {document_id} not found")
            return
        
        print(f"\n{'='*60}")
        print(f"Testing Entity Extraction on Document {document_id}")
        print(f"{'='*60}\n")
        
        # Test DSPy entity service
        dspy_entity_service = get_dspy_entity_service()
        
        try:
            entities = await dspy_entity_service.extract_entities_from_content(
                content=document.content,
                document_id=document_id
            )
            
            print(f"✓ Entity extraction successful")
            print(f"\nExtracted {len(entities)} entities:")
            for i, entity in enumerate(entities[:10], 1):
                print(f"  {i}. {entity['name']} ({entity['type']})")
                print(f"     Description: {entity['description']}")
            
            # Test adapter (without committing)
            print(f"\n{'='*60}")
            print(f"Testing Entity Adapter (dry run)")
            print(f"{'='*60}\n")
            
            adapter = DspyEntityAdapter(session)
            result = await adapter.process_document_entities(
                firebase_uid=user_id,
                document_id=document_id,
                entities=entities
            )
            
            # Don't commit - this is a test
            await session.rollback()
            
            print(f"✓ Entity adapter processed: {result['entities_processed']}/{result['entities_extracted']} entities")
            print(f"  Status: {result['status']}")
            print(f"  Message: {result['message']}")
            
        except Exception as e:
            print(f"✗ Entity extraction failed: {e}")
            import traceback
            traceback.print_exc()


async def main():
    """Run migration tests"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Test DSPy migration")
    parser.add_argument("--id", type=int, default=20, help="Document ID to test")
    parser.add_argument("--user", type=str, default="test_user", help="User ID for entity extraction")
    
    args = parser.parse_args()
    
    print(f"\n🧪 Testing DSPy Migration")
    print(f"Document ID: {args.id}")
    print(f"User ID: {args.user}\n")
    
    # Test content extraction
    await test_content_extraction(args.id)
    
    # Test entity extraction
    await test_entity_extraction(args.id, args.user)
    
    print(f"\n{'='*60}")
    print("✓ Migration tests completed")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    asyncio.run(main())

