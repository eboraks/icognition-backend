"""
Test script for DSPy content extraction service
Tests both Flash and Flash Lite models and validates results
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
from app.services.dspy_extraction_service import DspyExtractionService, get_dspy_service
from app.db.database import async_session
from app.utils.logging import get_logger

logger = get_logger(__name__)


class DSPyExtractionTest:
    """Test suite for DSPy content extraction"""
    
    def __init__(self):
        self.results: List[Dict[str, Any]] = []
        self.service: Optional[DspyExtractionService] = None
        self.timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    
    async def setup(self):
        """Initialize the service"""
        try:
            self.service = get_dspy_service()
            logger.info("DSPy service initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize DSPy service: {e}")
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
    
    def validate_summary(self, summary: str) -> Dict[str, Any]:
        """Validate summary quality"""
        length = len(summary)
        is_valid_length = 100 <= length <= 500
        
        return {
            "length": length,
            "is_valid": is_valid_length,
            "pass": is_valid_length
        }
    
    def validate_markdown_content(self, markdown_content: str) -> Dict[str, Any]:
        """Validate markdown content"""
        length = len(markdown_content)
        is_valid_length = length > 50
        
        return {
            "length": length,
            "is_valid_length": is_valid_length,
            "pass": is_valid_length
        }
    
    def validate_entities(
        self,
        entities: List[Dict[str, Any]],
        original_content: str
    ) -> Dict[str, Any]:
        """Validate entities match content using fuzzy matching"""
        count = len(entities)
        is_valid_count = 1 <= count <= 10
        
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
        
        return {
            "count": count,
            "is_valid_count": is_valid_count,
            "all_match_content": all_valid,
            "details": validations,
            "pass": is_valid_count and all_valid
        }
    
    def validate_analysis(self, analysis: Dict[str, Any]) -> Dict[str, Any]:
        """Validate analysis fields are populated"""
        has_objectivity = bool(analysis.get("objectivity"))
        has_tone = bool(analysis.get("tone"))
        has_intent = bool(analysis.get("intent"))
        
        all_present = has_objectivity and has_tone and has_intent
        
        return {
            "has_objectivity": has_objectivity,
            "has_tone": has_tone,
            "has_intent": has_intent,
            "pass": all_present
        }
    
    def validate_extraction(
        self,
        extracted_data: Any,
        original_content: str
    ) -> Dict[str, Any]:
        """Run all validation checks"""
        validations = {
            "summary": self.validate_summary(extracted_data.summary),
            "markdown_content": self.validate_markdown_content(extracted_data.markdown_content),
            "entities": self.validate_entities(
                [e.model_dump() for e in extracted_data.key_entities],
                original_content
            ),
            "analysis": self.validate_analysis(extracted_data.analysis.model_dump()),
            "has_title": bool(extracted_data.title),
            "has_source_type": bool(extracted_data.source_type),
            "fields_complete": all([
                bool(extracted_data.title),
                bool(extracted_data.source_type),
                bool(extracted_data.summary),
                bool(extracted_data.markdown_content),
            ])
        }
        
        # Calculate overall pass rate
        passes = sum(v.get("pass", False) for v in validations.values() if isinstance(v, dict) and "pass" in v)
        total_checks = sum(1 for v in validations.values() if isinstance(v, dict) and "pass" in v)
        
        validations["_summary"] = {
            "passes": passes,
            "total_checks": total_checks,
            "pass_rate": passes / total_checks if total_checks > 0 else 0
        }
        
        return validations
    
    async def test_document(
        self,
        document: Document,
        model_name: str
    ) -> Dict[str, Any]:
        """Test extraction on a single document"""
        start_time = datetime.now()
        
        try:
            # Extract content
            extracted = self.service.extract_content(
                text=document.content,
                model_name=model_name
            )
            
            # Measure time
            elapsed = (datetime.now() - start_time).total_seconds()
            
            # Validate extraction
            validations = self.validate_extraction(extracted, document.content)
            
            logger.info(f"Document {document.id} extraction completed in {elapsed:.2f}s")
            
            return {
                "document_id": document.id,
                "document_title": document.title,
                "model": model_name,
                "success": True,
                "elapsed_seconds": elapsed,
                "extracted_data": extracted.model_dump(),
                "validations": validations,
                "error": None
            }
            
        except Exception as e:
            logger.error(f"Error extracting document {document.id}: {e}")
            return {
                "document_id": document.id,
                "document_title": document.title,
                "model": model_name,
                "success": False,
                "elapsed_seconds": (datetime.now() - start_time).total_seconds(),
                "extracted_data": None,
                "validations": None,
                "error": str(e)
            }
    
    async def run_tests(self, document_ids: List[int]):
        """Run tests on multiple documents with both models"""
        logger.info(f"Starting DSPy extraction tests with {len(document_ids)} documents")
        
        # Load documents
        documents = await self.load_documents(document_ids)
        
        if not documents:
            logger.error("No documents found")
            return
        
        # Test each document with both models
        for doc in documents:
            logger.info(f"Testing document {doc.id}: {doc.title}")
            
            # Test with Flash
            result_flash = await self.test_document(doc, "flash")
            self.results.append(result_flash)
            
            # Test with Flash Lite
            result_flash_lite = await self.test_document(doc, "flash_lite")
            self.results.append(result_flash_lite)
        
        # Generate summary
        self.generate_summary()
        
        # Save results
        self.save_results()
    
    def generate_summary(self):
        """Generate summary statistics"""
        flash_results = [r for r in self.results if r["model"] == "flash"]
        flash_lite_results = [r for r in self.results if r["model"] == "flash_lite"]
        
        self.summary = {
            "timestamp": self.timestamp,
            "total_tests": len(self.results),
            "flash": {
                "total": len(flash_results),
                "successful": sum(1 for r in flash_results if r["success"]),
                "failed": sum(1 for r in flash_results if not r["success"]),
                "avg_time": sum(r["elapsed_seconds"] for r in flash_results) / len(flash_results) if flash_results else 0,
                "avg_pass_rate": sum(
                    r["validations"]["_summary"]["pass_rate"] for r in flash_results if r["success"]
                ) / len(flash_results) if flash_results and any(r["success"] for r in flash_results) else 0
            },
            "flash_lite": {
                "total": len(flash_lite_results),
                "successful": sum(1 for r in flash_lite_results if r["success"]),
                "failed": sum(1 for r in flash_lite_results if not r["success"]),
                "avg_time": sum(r["elapsed_seconds"] for r in flash_lite_results) / len(flash_lite_results) if flash_lite_results else 0,
                "avg_pass_rate": sum(
                    r["validations"]["_summary"]["pass_rate"] for r in flash_lite_results if r["success"]
                ) / len(flash_lite_results) if flash_lite_results and any(r["success"] for r in flash_lite_results) else 0
            }
        }
    
    def save_results(self):
        """Save results to JSON file"""
        output_file = Path(__file__).parent / "data" / f"dspy_extraction_results_{self.timestamp}.json"
        
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
        print("DSPy Content Extraction Test Results")
        print("="*60)
        
        print(f"\nTimestamp: {self.summary['timestamp']}")
        print(f"Total Tests: {self.summary['total_tests']}")
        
        print("\n--- Flash Model ---")
        flash = self.summary['flash']
        print(f"  Successful: {flash['successful']}/{flash['total']}")
        print(f"  Failed: {flash['failed']}")
        print(f"  Avg Time: {flash['avg_time']:.2f}s")
        print(f"  Avg Pass Rate: {flash['avg_pass_rate']:.2%}")
        
        print("\n--- Flash Lite Model ---")
        flash_lite = self.summary['flash_lite']
        print(f"  Successful: {flash_lite['successful']}/{flash_lite['total']}")
        print(f"  Failed: {flash_lite['failed']}")
        print(f"  Avg Time: {flash_lite['avg_time']:.2f}s")
        print(f"  Avg Pass Rate: {flash_lite['avg_pass_rate']:.2%}")
        
        print("\n" + "="*60)


async def main(document_ids: List[int]):
    """Main test runner"""
    test = DSPyExtractionTest()
    
    try:
        await test.setup()
        await test.run_tests(document_ids)
        test.print_summary()
    except Exception as e:
        logger.error(f"Test failed: {e}")
        print(f"\nError: {e}")
        sys.exit(1)


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Test DSPy content extraction")
    parser.add_argument("--ids", type=str, required=True, help="Comma-separated document IDs")
    
    args = parser.parse_args()
    
    # Parse document IDs
    doc_ids = [int(id.strip()) for id in args.ids.split(",")]
    #doc_ids = [20]
    
    # Run tests
    asyncio.run(main(doc_ids))

