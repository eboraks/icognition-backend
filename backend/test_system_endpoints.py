#!/usr/bin/env python3
"""
Test script for the system endpoints
This script can be used to test the data population endpoints
"""

import requests
import json
from typing import Dict, Any

class SystemEndpointTester:
    def __init__(self, base_url: str = "http://localhost:8889", auth_token: str = None):
        self.base_url = base_url.rstrip('/')
        self.auth_token = auth_token
        self.headers = {
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        if auth_token:
            self.headers["Authorization"] = f"Bearer {auth_token}"
    
    def test_health_check(self) -> Dict[str, Any]:
        """Test the system health check endpoint"""
        try:
            response = requests.get(f"{self.base_url}/system/health", headers=self.headers)
            response.raise_for_status()
            return {
                "status": "success",
                "data": response.json(),
                "status_code": response.status_code
            }
        except requests.exceptions.RequestException as e:
            return {
                "status": "error",
                "error": str(e),
                "status_code": getattr(e.response, 'status_code', None)
            }
    
    def test_document_stats(self) -> Dict[str, Any]:
        """Test the document processing stats endpoint"""
        try:
            response = requests.get(f"{self.base_url}/system/documents/stats", headers=self.headers)
            response.raise_for_status()
            return {
                "status": "success",
                "data": response.json(),
                "status_code": response.status_code
            }
        except requests.exceptions.RequestException as e:
            return {
                "status": "error",
                "error": str(e),
                "status_code": getattr(e.response, 'status_code', None)
            }
    
    def test_missing_processing(self, missing_entities: bool = True, missing_embeddings: bool = True, limit: int = 10) -> Dict[str, Any]:
        """Test the documents missing processing endpoint"""
        try:
            params = {
                "missing_entities": missing_entities,
                "missing_embeddings": missing_embeddings,
                "limit": limit
            }
            response = requests.get(f"{self.base_url}/system/documents/missing-processing", headers=self.headers, params=params)
            response.raise_for_status()
            return {
                "status": "success",
                "data": response.json(),
                "status_code": response.status_code
            }
        except requests.exceptions.RequestException as e:
            return {
                "status": "error",
                "error": str(e),
                "status_code": getattr(e.response, 'status_code', None)
            }
    
    def test_process_documents(self, document_ids: list = None, process_entities: bool = True, process_embeddings: bool = True, process_content: bool = True) -> Dict[str, Any]:
        """Test the document processing endpoint"""
        try:
            data = {
                "document_ids": document_ids,
                "process_entities": process_entities,
                "process_embeddings": process_embeddings,
                "process_content": process_content
            }
            response = requests.post(f"{self.base_url}/system/documents/process", headers=self.headers, json=data)
            response.raise_for_status()
            return {
                "status": "success",
                "data": response.json(),
                "status_code": response.status_code
            }
        except requests.exceptions.RequestException as e:
            return {
                "status": "error",
                "error": str(e),
                "status_code": getattr(e.response, 'status_code', None)
            }
    
    def test_process_all_missing(self) -> Dict[str, Any]:
        """Test the process all missing data endpoint"""
        try:
            response = requests.post(f"{self.base_url}/system/documents/process-all-missing", headers=self.headers)
            response.raise_for_status()
            return {
                "status": "success",
                "data": response.json(),
                "status_code": response.status_code
            }
        except requests.exceptions.RequestException as e:
            return {
                "status": "error",
                "error": str(e),
                "status_code": getattr(e.response, 'status_code', None)
            }
    
    def run_all_tests(self) -> Dict[str, Any]:
        """Run all tests and return comprehensive results"""
        results = {}
        
        print("Testing system endpoints...")
        print("=" * 50)
        
        # Test 1: Health check
        print("1. Testing health check...")
        results["health_check"] = self.test_health_check()
        print(f"   Result: {results['health_check']['status']}")
        if results['health_check']['status'] == 'success':
            print(f"   Data: {results['health_check']['data']}")
        else:
            print(f"   Error: {results['health_check']['error']}")
        
        # Test 2: Document stats
        print("\n2. Testing document stats...")
        results["document_stats"] = self.test_document_stats()
        print(f"   Result: {results['document_stats']['status']}")
        if results['document_stats']['status'] == 'success':
            stats = results['document_stats']['data']
            print(f"   Total documents: {stats['total_documents']}")
            print(f"   Missing entities: {stats['documents_without_entities']}")
            print(f"   Missing embeddings: {stats['documents_without_embeddings']}")
            print(f"   Missing both: {stats['documents_without_both']}")
        else:
            print(f"   Error: {results['document_stats']['error']}")
        
        # Test 3: Missing processing
        print("\n3. Testing missing processing query...")
        results["missing_processing"] = self.test_missing_processing(limit=5)
        print(f"   Result: {results['missing_processing']['status']}")
        if results['missing_processing']['status'] == 'success':
            missing_data = results['missing_processing']['data']
            print(f"   Documents found: {missing_data['total_found']}")
            if missing_data['documents']:
                print("   Sample documents:")
                for doc in missing_data['documents'][:3]:  # Show first 3
                    print(f"     - {doc['title']} (missing: {', '.join(doc['missing'])})")
        else:
            print(f"   Error: {results['missing_processing']['error']}")
        
        # Test 4: Process specific documents (if any found)
        if results.get('missing_processing', {}).get('status') == 'success':
            missing_data = results['missing_processing']['data']
            if missing_data['documents']:
                print("\n4. Testing document processing for specific documents...")
                doc_ids = [doc['id'] for doc in missing_data['documents'][:2]]  # Process first 2
                results["process_specific"] = self.test_process_documents(document_ids=doc_ids)
                print(f"   Result: {results['process_specific']['status']}")
                if results['process_specific']['status'] == 'success':
                    process_data = results['process_specific']['data']
                    print(f"   Documents processed: {process_data['documents_processed']}")
                    print(f"   Tasks triggered: {process_data['tasks_triggered']}")
                else:
                    print(f"   Error: {results['process_specific']['error']}")
            else:
                print("\n4. Skipping specific document processing (no documents found)")
                results["process_specific"] = {"status": "skipped", "reason": "no documents found"}
        else:
            print("\n4. Skipping specific document processing (missing processing test failed)")
            results["process_specific"] = {"status": "skipped", "reason": "missing processing test failed"}
        
        print("\n" + "=" * 50)
        print("Test Summary:")
        for test_name, result in results.items():
            status = result.get('status', 'unknown')
            print(f"  {test_name}: {status}")
        
        return results


def main():
    """Main function to run the tests"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Test system endpoints for data population")
    parser.add_argument("--base-url", default="http://localhost:8889", help="Base URL of the API")
    parser.add_argument("--auth-token", help="Firebase auth token for authentication")
    parser.add_argument("--test", choices=["health", "stats", "missing", "process", "all"], default="all", help="Which test to run")
    
    args = parser.parse_args()
    
    tester = SystemEndpointTester(args.base_url, args.auth_token)
    
    if args.test == "health":
        result = tester.test_health_check()
        print(json.dumps(result, indent=2))
    elif args.test == "stats":
        result = tester.test_document_stats()
        print(json.dumps(result, indent=2))
    elif args.test == "missing":
        result = tester.test_missing_processing()
        print(json.dumps(result, indent=2))
    elif args.test == "process":
        result = tester.test_process_all_missing()
        print(json.dumps(result, indent=2))
    else:  # all
        results = tester.run_all_tests()
        print(f"\nFinal Results: {json.dumps(results, indent=2)}")


if __name__ == "__main__":
    main()
