"""
Test script for DSPy entity extraction service
Tests entity extraction only using Flash Lite model
"""

import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
from thefuzz import fuzz

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.models import Document
from app.services.dspy_entity_service import DspyEntityService, get_dspy_entity_service
from app.db.database import async_session
from app.utils.logging import get_logger

logger = get_logger(__name__)


class DSPyEntityServiceTest:
    """Test suite for DSPy entity extraction service"""
    
    def __init__(self):
        self.results: List[Dict[str, Any]] = []
        self.service: Optional[DspyEntityService] = None
        self.timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    
    async def setup(self):
        """Initialize the service"""
        try:
            self.service = get_dspy_entity_service()
            logger.info("DSPy entity service initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize DSPy entity service: {e}")
            raise
    
    async def load_documents(self, document_ids: List[int]) -> List[Document]:
        """Load documents by ID from database"""
        async with async_session() as session:
            try:
                # Query all documents at once
                result = await session.execute(
                    select(Document).where(Document.id.in_(document_ids))
                )
                documents = result.scalars().all()
                
                logger.info(f"Loaded {len(documents)} documents from database")
                return list(documents)
            except Exception as e:
                logger.error(f"Error loading documents: {e}")
                raise
    
    def validate_entities(
        self,
        entities: List[Dict[str, Any]],
        original_content: str
    ) -> Dict[str, Any]:
        """Validate entities match content using fuzzy matching"""
        count = len(entities)
        is_valid_count = 1 <= count <= 15
        
        # Check entity names appear in content
        validations = []
        for entity in entities:
            name = entity.get("name", "")
            # Use fuzzy matching to find similar mentions
            fuzzy_scores = [
                fuzz.partial_ratio(name.lower(), word.lower())
                for word in original_content.split()
                if len(word) > 2
            ]
            best_score = max(fuzzy_scores) if fuzzy_scores else 0
            
            # Entity is valid if fuzzy match is > 70
            is_valid = best_score > 70
            validations.append({
                "name": name,
                "type": entity.get("type", ""),
                "match_score": best_score,
                "is_valid": is_valid
            })
        
        all_valid = all(v["is_valid"] for v in validations)
        valid_count = sum(1 for v in validations if v["is_valid"])
        
        return {
            "count": count,
            "is_valid_count": is_valid_count,
            "entities_matching_content": valid_count,
            "match_rate": valid_count / count if count > 0 else 0,
            "details": validations,
            "pass": is_valid_count and (valid_count / count >= 0.7)  # At least 70% should match
        }
    
    async def test_document(
        self,
        document: Document
    ) -> Dict[str, Any]:
        """Test entity extraction on a single document"""
        start_time = datetime.now()
        
        try:
            # Extract entities
            entities = await self.service.extract_entities_from_content(
                content=document.content,
                document_id=document.id
            )
            
            # Measure time
            elapsed = (datetime.now() - start_time).total_seconds()
            
            # Validate extraction
            validations = self.validate_entities(entities, document.content)
            
            logger.info(f"Document {document.id} entity extraction completed in {elapsed:.2f}s")
            
            return {
                "document_id": document.id,
                "document_title": document.title,
                "success": True,
                "elapsed_seconds": elapsed,
                "entities": entities,
                "entity_count": len(entities),
                "validations": validations,
                "error": None
            }
            
        except Exception as e:
            logger.error(f"Error extracting entities from document {document.id}: {e}")
            return {
                "document_id": document.id,
                "document_title": document.title,
                "success": False,
                "elapsed_seconds": (datetime.now() - start_time).total_seconds(),
                "entities": [],
                "entity_count": 0,
                "validations": None,
                "error": str(e)
            }
    
    async def run_tests(self, document_ids: List[int]):
        """Run entity extraction tests on multiple documents"""
        logger.info(f"Starting DSPy entity service tests with {len(document_ids)} documents")
        
        # Load documents
        documents = await self.load_documents(document_ids)
        
        if not documents:
            logger.error("No documents found")
            return
        
        # Test each document
        for doc in documents:
            logger.info(f"Testing document {doc.id}: {doc.title}")
            result = await self.test_document(doc)
            self.results.append(result)
        
        # Generate summary
        self.generate_summary()
        
        # Save results
        self.save_results()
    
    def generate_summary(self):
        """Generate summary statistics"""
        successful = [r for r in self.results if r["success"]]
        failed = [r for r in self.results if not r["success"]]
        
        self.summary = {
            "timestamp": self.timestamp,
            "total_tests": len(self.results),
            "successful": len(successful),
            "failed": len(failed),
            "avg_time": sum(r["elapsed_seconds"] for r in successful) / len(successful) if successful else 0,
            "avg_entity_count": sum(r["entity_count"] for r in successful) / len(successful) if successful else 0,
            "avg_match_rate": sum(
                r["validations"]["match_rate"] for r in successful if r.get("validations")
            ) / len(successful) if successful else 0,
            "model": "gemini-2.5-flash-lite"
        }
    
    def save_results(self):
        """Save results to JSON file"""
        output_file = Path(__file__).parent / "data" / f"dspy_entity_results_{self.timestamp}.json"
        
        results = {
            "summary": self.summary,
            "detailed_results": self.results
        }
        
        with open(output_file, "w") as f:
            json.dump(results, f, indent=2, default=str)
        
        logger.info(f"Results saved to: {output_file}")
        print(f"\nResults saved to: {output_file}")
    
    def print_summary(self):
        """Print summary to console"""
        print("\n" + "="*60)
        print("DSPy Entity Service Test Results")
        print("="*60)
        
        print(f"\nTimestamp: {self.summary['timestamp']}")
        print(f"Model: {self.summary['model']}")
        print(f"Total Tests: {self.summary['total_tests']}")
        print(f"Successful: {self.summary['successful']}")
        print(f"Failed: {self.summary['failed']}")
        print(f"Avg Time: {self.summary['avg_time']:.2f}s")
        print(f"Avg Entities per Document: {self.summary['avg_entity_count']:.1f}")
        print(f"Avg Entity Match Rate: {self.summary['avg_match_rate']:.2%}")
        
        print("\n" + "="*60)


async def main(document_ids: List[int]):
    """Main test runner"""
    test = DSPyEntityServiceTest()
    
    try:
        await test.setup()
        await test.run_tests(document_ids)
        test.print_summary()
    except Exception as e:
        logger.error(f"Test failed: {e}")
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Test DSPy entity extraction service")
    parser.add_argument("--ids", type=str, required=True, help="Comma-separated document IDs")
    
    args = parser.parse_args()
    
    # Parse document IDs
    doc_ids = [int(id.strip()) for id in args.ids.split(",")]
    
    # Run tests
    asyncio.run(main(doc_ids))

