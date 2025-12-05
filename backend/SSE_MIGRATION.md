# SSE Chat Migration

## Overview

The chat functionality has been migrated from WebSocket to Server-Sent Events (SSE) for better reliability, especially in serverless environments like Cloud Run.

## Changes Made

### Backend (`backend/app/api/routes/chat.py`)

1. **New REST Endpoint for Sending Messages**
   - `POST /api/v1/chat/sessions/{session_id}/messages`
   - Accepts: `{"content": "user message"}`
   - Returns: Saved `ChatMessage` object with `id`

2. **New SSE Endpoint for Streaming Responses**
   - `GET /api/v1/chat/sessions/{session_id}/stream?message_id={message_id}`
   - Streams AI response using Server-Sent Events
   - Events:
     - `stream_chunk`: Incremental text chunks
     - `end_stream`: Final complete response
     - `error`: Error occurred

3. **WebSocket Endpoint Retained**
   - The WebSocket endpoint (`/ws/{session_id}/{user_id}`) is still available for backward compatibility
   - Frontend now uses SSE instead

### Frontend (`frontend/src/stores/chat_store.ts`)

1. **Removed WebSocket Connection Logic**
   - Removed `connectWebSocket()` function
   - Removed WebSocket message handling

2. **Added SSE Streaming**
   - New `streamChatResponse()` function that uses `fetch` with `ReadableStream`
   - Handles SSE events: `stream_chunk`, `end_stream`, `error`
   - Uses Firebase ID token for authentication

3. **Updated `sendMessage()` Function**
   - Now sends message via REST API (`POST /sessions/{id}/messages`)
   - Then starts SSE stream for AI response
   - No longer requires persistent WebSocket connection

### Frontend Service (`frontend/src/services/chatService.ts`)

1. **Added `sendMessage()` Method**
   - `sendMessage(sessionId: number, content: string)`
   - Sends message to REST API and returns saved message

## Benefits

1. **Better Reliability**
   - SSE works better with Cloud Run load balancers
   - Automatic reconnection handled by browser
   - No connection state management needed

2. **Simpler Implementation**
   - No WebSocket connection management
   - No heartbeat/ping-pong logic
   - Standard HTTP with streaming

3. **Better for Serverless**
   - Works seamlessly with Cloud Run
   - No WebSocket timeout issues
   - Better connection handling

4. **Easier iOS Implementation**
   - Native `EventSource` support
   - No need for WebSocket libraries

## Testing

### Test Script

A test script is available at `backend/tests/test_sse_chat.py`:

```bash
# Basic usage
python backend/tests/test_sse_chat.py \
  --base-url http://localhost:8000 \
  --session-id 1 \
  --token YOUR_FIREBASE_TOKEN \
  --message "Hello! Can you tell me a joke?"

# Use existing message
python backend/tests/test_sse_chat.py \
  --base-url http://localhost:8000 \
  --session-id 1 \
  --token YOUR_FIREBASE_TOKEN \
  --skip-send \
  --message-id 123
```

### Manual Testing

1. **Send a message:**
   ```bash
   curl -X POST http://localhost:8000/api/v1/chat/sessions/1/messages \
     -H "Authorization: Bearer YOUR_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"content": "Hello!"}'
   ```

2. **Stream response:**
   ```bash
   curl -N http://localhost:8000/api/v1/chat/sessions/1/stream?message_id=123 \
     -H "Authorization: Bearer YOUR_TOKEN" \
     -H "Accept: text/event-stream"
   ```

## Chrome Extension

**Migration Status:** Backend is ready for SSE. See `CHROME_EXTENSION_SSE_MIGRATION.md` for detailed migration steps.

The Chrome extension currently uses WebSocket for document processing notifications (`/ws/{user_id}/extension`). The backend has been updated to support SSE notifications via `/api/v1/notifications/stream`. Once the extension is migrated to SSE, the WebSocket endpoint can be removed.

## Migration Notes

- The old WebSocket endpoint is still available but not used by the frontend
- Existing chat sessions will continue to work
- No database migrations required
- Frontend automatically uses SSE for new messages

## Future Improvements

1. Consider removing WebSocket endpoint after confirming SSE works in production
2. Add retry logic for SSE connection failures
3. Add connection status indicator in UI
4. Consider using EventSource polyfill for older browsers (if needed)

