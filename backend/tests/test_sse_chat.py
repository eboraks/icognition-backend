#!/usr/bin/env python3
"""
Test script for SSE (Server-Sent Events) chat functionality.

This script tests the chat API using SSE for streaming responses.
It simulates a user sending a message and receiving a streamed AI response.

Usage:
    python test_sse_chat.py [--base-url BASE_URL] [--session-id SESSION_ID] [--token TOKEN]

Example:
    python test_sse_chat.py --base-url http://localhost:8000 --session-id 1 --token YOUR_FIREBASE_TOKEN
"""

import argparse
import json
import sys
import time
from typing import Optional
import requests
from requests.auth import HTTPBasicAuth


def parse_sse_event(line: str) -> Optional[dict]:
    """Parse a single SSE event line."""
    if line.startswith("event: "):
        return {"type": "event", "value": line[7:].strip()}
    elif line.startswith("data: "):
        try:
            data = json.loads(line[6:].strip())
            return {"type": "data", "value": data}
        except json.JSONDecodeError:
            return {"type": "data", "value": line[6:].strip()}
    return None


def stream_sse_response(url: str, headers: dict):
    """Stream SSE response from the server."""
    print(f"🔗 Connecting to SSE endpoint: {url}")
    print("-" * 80)
    
    try:
        response = requests.get(url, headers=headers, stream=True, timeout=300)
        response.raise_for_status()
        
        print(f"✅ Connected! Status: {response.status_code}")
        print(f"📡 Content-Type: {response.headers.get('Content-Type', 'unknown')}")
        print("-" * 80)
        print()
        
        buffer = ""
        current_event = None
        chunk_count = 0
        
        for line in response.iter_lines(decode_unicode=True):
            if not line:
                # Empty line indicates end of event
                if current_event:
                    event_type = current_event.get("event_type", "message")
                    data = current_event.get("data", {})
                    
                    if event_type == "stream_chunk":
                        chunk_count += 1
                        content = data.get("content", "")
                        # Extract plain text from HTML for display
                        import re
                        plain_text = re.sub(r'<[^>]+>', '', content)
                        print(f"📦 Chunk #{chunk_count}: {len(plain_text)} chars")
                        if chunk_count <= 3 or chunk_count % 10 == 0:
                            # Show first 3 chunks and every 10th chunk
                            preview = plain_text[:100] + "..." if len(plain_text) > 100 else plain_text
                            print(f"   Preview: {preview}")
                    
                    elif event_type == "end_stream":
                        content = data.get("content", "")
                        import re
                        plain_text = re.sub(r'<[^>]+>', '', content)
                        print(f"\n✅ Stream completed!")
                        print(f"📊 Total chunks received: {chunk_count}")
                        print(f"📝 Final response length: {len(plain_text)} characters")
                        print(f"\n📄 Full response:")
                        print("-" * 80)
                        print(plain_text)
                        print("-" * 80)
                    
                    elif event_type == "error":
                        error_msg = data.get("content", "Unknown error")
                        print(f"\n❌ Error received: {error_msg}")
                    
                    current_event = None
                continue
            
            # Parse SSE format
            if line.startswith("event: "):
                if current_event is None:
                    current_event = {"event_type": line[7:].strip(), "data": {}}
                else:
                    current_event["event_type"] = line[7:].strip()
            
            elif line.startswith("data: "):
                data_str = line[6:].strip()
                try:
                    data = json.loads(data_str)
                    if current_event is None:
                        current_event = {"event_type": "message", "data": data}
                    else:
                        current_event["data"] = data
                except json.JSONDecodeError:
                    if current_event is None:
                        current_event = {"event_type": "message", "data": data_str}
                    else:
                        current_event["data"] = data_str
    
    except requests.exceptions.RequestException as e:
        print(f"❌ Error connecting to SSE endpoint: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"   Status: {e.response.status_code}")
            print(f"   Response: {e.response.text[:500]}")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n\n⚠️  Stream interrupted by user")
        sys.exit(0)


def send_message(base_url: str, session_id: int, content: str, token: Optional[str] = None) -> Optional[int]:
    """Send a message to the chat session and return the message ID."""
    url = f"{base_url}/api/v1/chat/sessions/{session_id}/messages"
    
    headers = {
        "Content-Type": "application/json",
    }
    
    if token:
        headers["Authorization"] = f"Bearer {token}"
    
    payload = {"content": content}
    
    print(f"📤 Sending message to: {url}")
    print(f"💬 Message: {content[:100]}{'...' if len(content) > 100 else ''}")
    print()
    
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=30)
        response.raise_for_status()
        
        message_data = response.json()
        message_id = message_data.get("id")
        
        print(f"✅ Message sent successfully!")
        print(f"📋 Message ID: {message_id}")
        print()
        
        return message_id
    
    except requests.exceptions.RequestException as e:
        print(f"❌ Error sending message: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"   Status: {e.response.status_code}")
            print(f"   Response: {e.response.text[:500]}")
        return None


def main():
    parser = argparse.ArgumentParser(description="Test SSE chat functionality")
    parser.add_argument(
        "--base-url",
        default="http://localhost:8000",
        help="Base URL of the API (default: http://localhost:8000)"
    )
    parser.add_argument(
        "--session-id",
        type=int,
        required=True,
        help="Chat session ID"
    )
    parser.add_argument(
        "--token",
        help="Firebase authentication token (Bearer token)"
    )
    parser.add_argument(
        "--message",
        default="Hello! Can you tell me a short joke?",
        help="Message to send (default: 'Hello! Can you tell me a short joke?')"
    )
    parser.add_argument(
        "--skip-send",
        action="store_true",
        help="Skip sending a new message, use existing message_id"
    )
    parser.add_argument(
        "--message-id",
        type=int,
        help="Use existing message ID (requires --skip-send)"
    )
    
    args = parser.parse_args()
    
    print("=" * 80)
    print("🧪 SSE Chat Test Script")
    print("=" * 80)
    print()
    
    base_url = args.base_url.rstrip('/')
    session_id = args.session_id
    token = args.token
    
    headers = {
        "Accept": "text/event-stream",
    }
    
    if token:
        headers["Authorization"] = f"Bearer {token}"
    
    # Step 1: Send message (unless skipped)
    message_id = None
    if not args.skip_send:
        message_id = send_message(base_url, session_id, args.message, token)
        if not message_id:
            print("❌ Failed to send message. Exiting.")
            sys.exit(1)
        
        # Small delay to ensure message is saved
        time.sleep(0.5)
    else:
        if not args.message_id:
            print("❌ --message-id required when using --skip-send")
            sys.exit(1)
        message_id = args.message_id
        print(f"📋 Using existing message ID: {message_id}")
        print()
    
    # Step 2: Stream response
    stream_url = f"{base_url}/api/v1/chat/sessions/{session_id}/stream?message_id={message_id}"
    stream_sse_response(stream_url, headers)
    
    print()
    print("=" * 80)
    print("✅ Test completed!")
    print("=" * 80)


if __name__ == "__main__":
    main()

