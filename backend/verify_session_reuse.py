import asyncio
import httpx
import json
import os

BASE_URL = "http://localhost:8000"
# Try to get a real user ID or use a default one for No-Auth
USER_ID = "0HshSg66wJekH02YyOn7HPhh0r02" 

async def test_session_reuse():
    async with httpx.AsyncClient(headers={"X-User-ID": USER_ID}, timeout=10.0) as client:
        # Create/Get session for doc 999
        data = {
            "title": "Verification Chat",
            "scope_type": "document",
            "scope_id": 999
        }
        
        print("First request...")
        try:
            resp1 = await client.post(f"{BASE_URL}/api/v1/chat/sessions", json=data)
            if resp1.status_code != 200:
                print(f"Error 1: {resp1.status_code} - {resp1.text}")
                return
                
            session1 = resp1.json()
            id1 = session1['id']
            print(f"Session 1 ID: {id1}")

            print("Second request...")
            resp2 = await client.post(f"{BASE_URL}/api/v1/chat/sessions", json=data)
            if resp2.status_code != 200:
                print(f"Error 2: {resp2.status_code} - {resp2.text}")
                return
                
            session2 = resp2.json()
            id2 = session2['id']
            print(f"Session 2 ID: {id2}")

            if id1 == id2:
                print("SUCCESS: Session IDs match!")
                return True
            else:
                print("FAILURE: Session IDs do not match!")
                return False
        except Exception as e:
            print(f"Connection error: {e}")
            return False

if __name__ == "__main__":
    success = asyncio.run(test_session_reuse())
    if not success:
        exit(1)
