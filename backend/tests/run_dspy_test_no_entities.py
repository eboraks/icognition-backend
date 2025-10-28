#!/usr/bin/env python3
"""
CLI script to run DSPy content extraction tests WITHOUT entity extraction
"""

import asyncio
import sys
from pathlib import Path
from typing import List

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent))

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models import Document
from app.db.database import async_session
from app.utils.logging import get_logger
from tests.test_dspy_extraction_no_entities import DSPyExtractionTestNoEntities

logger = get_logger(__name__)


async def validate_document_ids(document_ids: List[int]) -> bool:
    """Validate that document IDs exist in database"""
    async with async_session() as session:
        try:
            result = await session.execute(
                select(Document).where(Document.id.in_(document_ids))
            )
            documents = result.scalars().all()
            
            found_ids = {doc.id for doc in documents}
            requested_ids = set(document_ids)
            
            missing_ids = requested_ids - found_ids
            if missing_ids:
                logger.warning(f"Documents not found: {missing_ids}")
                print(f"Warning: Documents not found in database: {sorted(missing_ids)}")
                print(f"Found documents: {sorted(found_ids)}")
            
            return len(documents) > 0
            
        except Exception as e:
            logger.error(f"Error validating document IDs: {e}")
            return False


async def main():
    """Main CLI entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Test DSPy content extraction WITHOUT entity extraction on existing documents",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Test with document IDs 1, 5, and 10
  python run_dspy_test_no_entities.py --ids 1,5,10
  
  # Test with a single document
  python run_dspy_test_no_entities.py --ids 25
        """
    )
    
    parser.add_argument(
        "--ids",
        type=str,
        required=True,
        help="Comma-separated document IDs to test (e.g., 1,5,10)"
    )
    
    args = parser.parse_args()
    
    # Parse document IDs
    try:
        doc_ids = [int(id.strip()) for id in args.ids.split(",")]
    except ValueError:
        print("Error: Document IDs must be integers")
        sys.exit(1)
    
    if not doc_ids:
        print("Error: No document IDs provided")
        sys.exit(1)
    
    print(f"\n🔬 DSPy Content Extraction Test (NO ENTITIES)")
    print(f"Document IDs: {doc_ids}")
    print(f"Total tests to run: {len(doc_ids) * 2} (2 models per document)")
    print(f"Note: Entity extraction is disabled for faster processing\n")
    
    # Validate document IDs
    print("Validating document IDs...")
    if not await validate_document_ids(doc_ids):
        print("Error: No valid documents found in database")
        sys.exit(1)
    
    print("✓ Document IDs validated\n")
    
    # Run tests
    test = DSPyExtractionTestNoEntities()
    
    try:
        await test.setup()
        await test.run_tests(doc_ids)
        test.print_summary()
        
        print("\n✓ Tests completed successfully")
        print(f"\nDetailed results saved to: tests/data/dspy_extraction_results_no_entities_{test.timestamp}.json")
        
    except Exception as e:
        logger.error(f"Test failed: {e}")
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())

