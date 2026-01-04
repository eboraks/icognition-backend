"""
Test script to check URL fetch success rate for documents in the database.
Queries all documents, tests each URL, and reports success rate.
"""

import asyncio
import sys
from datetime import datetime
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

# Add the app directory to the path
sys.path.insert(0, '.')

from app.db.database import async_session, get_database_url
from app.models import Document
from app.services.web_fetcher import WebPageFetcher
from app.utils.logging import get_logger

logger = get_logger(__name__)


async def test_url_fetch():
    """
    Test URL fetching for all documents in the database.
    Reports success rate and detailed statistics.
    """
    results = {
        'total': 0,
        'success': 0,
        'failed': 0,
        'no_url': 0,
        'success_details': [],
        'failed_details': []
    }
    
    async with async_session() as session:
        try:
            # Query all documents with title and url
            logger.info("Querying document table for title and url...")
            query = select(Document.id, Document.title, Document.url).where(
                Document.url.isnot(None),
                Document.url != ''
            )
            
            result = await session.execute(query)
            documents = result.all()
            
            results['total'] = len(documents)
            logger.info(f"Found {results['total']} documents with URLs to test")
            
            if results['total'] == 0:
                logger.warning("No documents with URLs found in the database")
                return results
            
            # Test each URL
            for idx, (doc_id, title, url) in enumerate(documents, 1):
                logger.info(f"[{idx}/{results['total']}] Testing URL: {url}")
                logger.info(f"  Document ID: {doc_id}, Title: {title or 'N/A'}")
                
                # Skip if URL is None or empty
                if not url or not url.strip():
                    logger.warning(f"  Skipping - URL is empty")
                    results['no_url'] += 1
                    continue
                
                # Sleep for 1 second before each call
                if idx > 1:  # Don't sleep before the first call
                    await asyncio.sleep(1)
                
                # Test the URL
                try:
                    async with WebPageFetcher(timeout=30) as fetcher:
                        success, html_content, metadata = await fetcher.fetch_page(url)
                        
                        if success and html_content:
                            results['success'] += 1
                            content_length = len(html_content) if html_content else 0
                            
                            # Check content availability if available
                            content_status = "unknown"
                            if metadata and metadata.get('page_detection'):
                                content_avail = metadata['page_detection'].get('content_availability', {})
                                content_status = content_avail.get('status', 'unknown')
                            
                            results['success_details'].append({
                                'doc_id': doc_id,
                                'title': title,
                                'url': url,
                                'content_length': content_length,
                                'content_status': content_status,
                                'status_code': metadata.get('status_code') if metadata else None
                            })
                            
                            logger.info(f"  ✅ SUCCESS - Content length: {content_length}, Status: {content_status}")
                        else:
                            results['failed'] += 1
                            error_msg = metadata.get('error', 'Unknown error') if metadata else 'Unknown error'
                            status_code = metadata.get('status_code') if metadata else None
                            
                            results['failed_details'].append({
                                'doc_id': doc_id,
                                'title': title,
                                'url': url,
                                'error': error_msg,
                                'status_code': status_code
                            })
                            
                            logger.warning(f"  ❌ FAILED - Error: {error_msg}, Status: {status_code}")
                            
                except Exception as e:
                    results['failed'] += 1
                    error_msg = str(e)
                    
                    results['failed_details'].append({
                        'doc_id': doc_id,
                        'title': title,
                        'url': url,
                        'error': error_msg,
                        'status_code': None
                    })
                    
                    logger.error(f"  ❌ EXCEPTION - {error_msg}")
        
        except Exception as e:
            logger.error(f"Error querying database: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return results
    
    return results


async def print_report(results: dict):
    """Print a detailed report of the test results."""
    print("\n" + "="*80)
    print("URL FETCH TEST REPORT")
    print("="*80)
    print(f"Test Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    total = results['total']
    success = results['success']
    failed = results['failed']
    no_url = results['no_url']
    
    print(f"Total Documents Tested: {total}")
    print(f"  ✅ Successful: {success}")
    print(f"  ❌ Failed: {failed}")
    print(f"  ⚠️  No URL: {no_url}")
    print()
    
    if total > 0:
        success_rate = (success / total) * 100
        print(f"Success Rate: {success_rate:.2f}%")
        print()
    
    # Success details
    if results['success_details']:
        print("SUCCESSFUL FETCHES:")
        print("-" * 80)
        for detail in results['success_details'][:10]:  # Show first 10
            print(f"  ✅ [{detail['doc_id']}] {detail['title'] or 'N/A'}")
            print(f"     URL: {detail['url']}")
            print(f"     Content Length: {detail['content_length']:,} chars")
            print(f"     Content Status: {detail['content_status']}")
            print()
        
        if len(results['success_details']) > 10:
            print(f"  ... and {len(results['success_details']) - 10} more successful fetches")
            print()
    
    # Failed details
    if results['failed_details']:
        print("FAILED FETCHES:")
        print("-" * 80)
        for detail in results['failed_details'][:10]:  # Show first 10
            print(f"  ❌ [{detail['doc_id']}] {detail['title'] or 'N/A'}")
            print(f"     URL: {detail['url']}")
            print(f"     Error: {detail['error']}")
            if detail['status_code']:
                print(f"     HTTP Status: {detail['status_code']}")
            print()
        
        if len(results['failed_details']) > 10:
            print(f"  ... and {len(results['failed_details']) - 10} more failed fetches")
            print()
    
    # Error statistics
    if results['failed_details']:
        error_counts = {}
        for detail in results['failed_details']:
            error = detail['error']
            error_counts[error] = error_counts.get(error, 0) + 1
        
        print("ERROR BREAKDOWN:")
        print("-" * 80)
        for error, count in sorted(error_counts.items(), key=lambda x: x[1], reverse=True):
            print(f"  {error}: {count}")
        print()
    
    print("="*80)


async def main():
    """Main entry point for the test script."""
    try:
        logger.info("Starting URL fetch test...")
        logger.info(f"Database URL: {get_database_url()}")
        
        results = await test_url_fetch()
        
        await print_report(results)
        
        logger.info("URL fetch test completed")
        
    except KeyboardInterrupt:
        logger.info("Test interrupted by user")
    except Exception as e:
        logger.error(f"Test failed with error: {e}")
        import traceback
        logger.error(traceback.format_exc())
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())

