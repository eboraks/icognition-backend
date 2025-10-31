import os
import asyncio
import json
import argparse
from typing import Optional

import httpx
import websockets


DEFAULT_API_URL = os.environ.get("API_URL", "http://localhost:8000")
DEFAULT_ID_TOKEN = os.environ.get("FIREBASE_ID_TOKEN", "")
DEFAULT_USER_ID = os.environ.get("USER_ID", "")


async def create_session(api_url: str, id_token: str, title: str = "Backend Chat Test", scope_type: str = "all_library", scope_id: Optional[int] = None) -> int:
    url = f"{api_url}/api/v1/chat/sessions"
    headers = {"Authorization": f"Bearer {id_token}", "Content-Type": "application/json"}
    payload = {"title": title, "scope_type": scope_type, "scope_id": scope_id}
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()
        return data["id"] if isinstance(data, dict) else data.get("id")


async def get_sessions(api_url: str, id_token: str):
    url = f"{api_url}/api/v1/chat/sessions"
    headers = {"Authorization": f"Bearer {id_token}"}
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(url, headers=headers)
        resp.raise_for_status()
        return resp.json()


async def get_messages(api_url: str, id_token: str, session_id: int):
    url = f"{api_url}/api/v1/chat/sessions/{session_id}/messages"
    headers = {"Authorization": f"Bearer {id_token}"}
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(url, headers=headers)
        resp.raise_for_status()
        return resp.json()


async def ws_chat(api_url: str, session_id: int, user_id: str, questions: list[str], wait_seconds: float = 5.0):
    # Convert http:// to ws:// and https:// to wss://
    ws_base = api_url.replace("http://", "ws://").replace("https://", "wss://")
    ws_url = f"{ws_base}/api/v1/chat/ws/{session_id}/{user_id}"

    async with websockets.connect(ws_url, ping_interval=None) as websocket:
        for q in questions:
            await websocket.send(json.dumps({"content": q}))
            # Read streamed chunks for a short period per question
            try:
                end_time = asyncio.get_event_loop().time() + wait_seconds
                while asyncio.get_event_loop().time() < end_time:
                    try:
                        msg = await asyncio.wait_for(websocket.recv(), timeout=1.0)
                        print(msg, flush=True)
                    except asyncio.TimeoutError:
                        # No chunk this second, continue until wait window elapses
                        pass
            except websockets.ConnectionClosed:
                break


async def main():
    parser = argparse.ArgumentParser(description="Run chat backend E2E test (REST + WebSocket)")
    parser.add_argument("--api-url", default=DEFAULT_API_URL, help="Base API URL, e.g., http://localhost:8000")
    parser.add_argument("--id-token", default=DEFAULT_ID_TOKEN, help="Firebase ID token (or set FIREBASE_ID_TOKEN env)")
    parser.add_argument("--user-id", default=DEFAULT_USER_ID, help="User ID for WebSocket path (or set USER_ID env)")
    parser.add_argument("--title", default="Backend Chat Test", help="Chat session title")
    parser.add_argument("--wait-seconds", type=float, default=6.0, help="Seconds to collect WS stream per question")
    args = parser.parse_args()

    if not args.id_token:
        raise SystemExit("FIREBASE_ID_TOKEN (or --id-token) is required")
    if not args.user_id:
        raise SystemExit("USER_ID (or --user-id) is required for WebSocket path")

    print(f"Using API: {args.api_url}")

    # Create session (POST)
    session_id = await create_session(args.api_url, args.id_token, title=args.title)
    print(f"Created session: {session_id}")

    # List sessions (GET)
    sessions = await get_sessions(args.api_url, args.id_token)
    print(f"Sessions count: {len(sessions) if isinstance(sessions, list) else 'unknown'}")

    # Get messages (GET)
    messages = await get_messages(args.api_url, args.id_token, session_id)
    print(f"Initial messages for session {session_id}: {len(messages) if isinstance(messages, list) else 'unknown'}")

    # WebSocket test
    questions = [
        "What can you do?",
        "Summarize the main topics from my library.",
    ]
    print("Opening WebSocket and sending questions...")
    await ws_chat(args.api_url, session_id, args.user_id, questions, wait_seconds=args.wait_seconds)

    # Fetch messages again to verify persistence
    final_messages = await get_messages(args.api_url, args.id_token, session_id)
    print(f"Final messages stored for session {session_id}: {len(final_messages) if isinstance(final_messages, list) else 'unknown'}")


if __name__ == "__main__":
    asyncio.run(main())
