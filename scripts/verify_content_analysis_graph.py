
import asyncio
import os
import sys
from unittest.mock import MagicMock, patch

# Add backend to path
sys.path.append(os.path.join(os.getcwd(), 'backend'))

# Check for .env and load if missing in env
from dotenv import load_dotenv
load_dotenv(os.path.join(os.getcwd(), 'backend', '.env'))

# Basic mock for settings if not present
if "DATABASE_URL" not in os.environ:
    os.environ["DATABASE_URL"] = "postgresql+asyncpg://user:pass@localhost/db"

try:
    from app.services.content_analysis_service import ContentAnalysisService
except ImportError as e:
    print(f"Import Error: {e}")
    sys.exit(1)

async def main():
    print("--- Starting Verification ---")
    
    try:
        service = ContentAnalysisService()
        print("✅ Service initialized.")
    except Exception as e:
        print(f"❌ Service initialization failed: {e}")
        return

    # Mock _get_db_prompt to return None (testing fallback)
    # We do this to avoid actual DB calls which might fail without a real DB
    original_get_db_prompt = service._get_db_prompt
    service._get_db_prompt = MagicMock()
    
    # Create a future for the return value since it's an async method
    f = asyncio.Future()
    f.set_result(None)
    service._get_db_prompt.return_value = f
    
    test_content = "The stock market hit a record high today as tech stocks rallied. Investors are optimistic about AI advancements."
    test_title = "Market Rally 2024"
    
    try:
        print(f"Testing analysis on: '{test_title}'...")
        result = await service.analyze_document_content(test_content, title=test_title)
        
        print("✅ Analysis completed.")
        print(f"Agent Name: {result.get('agent_name')}")
        print(f"Summary: {result.get('summary')}")
        print(f"Bullet Points: {len(result.get('bullet_points', []))} points found.")
        
        if result.get("summary") and result.get("bullet_points") is not None:
             print("✅ Structure looks correct.")
        else:
             print("❌ Output structure invalid.")

    except Exception as e:
        print(f"❌ Analysis failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
