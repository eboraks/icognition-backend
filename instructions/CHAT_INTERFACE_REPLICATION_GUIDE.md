# Chat Interface Replication Guide

This document provides a concise summary with absolute file paths to help replicate the chat interface from the web app to the iPhone app.

**Note**: This guide reflects the current SSE (Server-Sent Events) + REST Pull implementation. The chat system was migrated from WebSocket to SSE for better reliability in serverless environments. See `backend/SSE_MIGRATION.md` for migration details.

## Architecture Overview

The chat interface follows a **session-based, SSE (Server-Sent Events) streaming architecture** with the following key components:

1. **Frontend**: Vue 3 + Pinia stores managing chat sessions and SSE connections
2. **Backend**: FastAPI with REST endpoints for sending messages and SSE endpoints for streaming AI responses via LangGraph
3. **State Management**: Session isolation with per-session message histories
4. **Real-time Communication**: SSE streaming with structured message envelopes (no persistent WebSocket connection)

---

## Frontend Components

### Core Chat UI Component
**File**: `/Users/eboraks/Projects/icognition/frontend/src/components/knowledge_explorer/ChatPanel.vue`

- Main chat interface component using PrimeVue components
- Displays messages (user/system/filter types) with HTML rendering
- Handles input submission and action button clicks
- Watches `chat_store.activeSession?.messages` for real-time updates
- Manages contextual welcome messages based on entity/document filters
- Key features:
  - ScrollPanel for message container
  - InputText with send button
  - ProgressSpinner for pending messages
  - Action buttons and resources display
  - Auto-scroll to bottom on new messages

### Chat Store (State Management)
**File**: `/Users/eboraks/Projects/icognition/frontend/src/stores/chat_store.ts`

- Pinia store managing chat sessions and SSE connections
- Key functions:
  - `loadSessions()`: Fetch all user sessions
  - `createSession()`: Create new chat session
  - `sendMessage()`: Send message via REST API, then start SSE stream
  - `streamChatResponse()`: Establish SSE connection for streaming AI response
  - `switchActiveSession()`: Switch between chat sessions
- SSE message handling:
  - `stream_chunk`: Accumulates streaming content
  - `end_stream`: Finalizes message, removes pending flag
  - `error`: Displays error messages
- Messages stored per-session in `activeSession.value.messages`
- Uses `fetch` with `ReadableStream` for SSE (EventSource doesn't support custom headers)

### Knowledge Explorer Store
**File**: `/Users/eboraks/Projects/icognition/frontend/src/stores/knowledgeExplorerStore.ts`

- Manages chat tabs and entity/document selections
- Coordinates with `chat_store` to create sessions for each tab
- Tracks active entity/document filters for contextual chat
- Key functions:
  - `addChatTab()`: Creates new tab with backend session
  - `setActiveChatTab()`: Switches active tab
  - `ensureActiveChatTab()`: Ensures at least one tab exists

### Knowledge Explorer View
**File**: `/Users/eboraks/Projects/icognition/frontend/src/views/library/KnowledgeExplorer.vue`

- Main view component rendering ChatPanel
- Manages tab UI (buttons, add button)
- Passes session ID and filter selections to ChatPanel

### Service Layer

**Chat Service**: `/Users/eboraks/Projects/icognition/frontend/src/services/chatService.ts`
- REST API client for chat session management
- Endpoints:
  - `POST /api/v1/chat/sessions`: Create session
  - `GET /api/v1/chat/sessions`: List sessions
  - `GET /api/v1/chat/sessions/{id}/messages`: Get messages
  - `POST /api/v1/chat/sessions/{id}/messages`: Send message (returns saved message with ID)
  - `DELETE /api/v1/chat/sessions/{id}`: Delete session
  - `PUT /api/v1/chat/sessions/{id}/title`: Update title
  - `PUT /api/v1/chat/sessions/{id}/scope`: Update scope
- Auto-injects Firebase ID token via Axios interceptor

**Knowledge Service**: `/Users/eboraks/Projects/icognition/frontend/src/services/knowledgeService.ts`
- Handles contextual messages and action buttons
- Endpoints:
  - `POST /api/v1/knowledge/contextual-message`: Get welcome message
  - `POST /api/v1/knowledge/action`: Handle action button clicks

---

## Backend Components

### Chat API Router
**File**: `/Users/eboraks/Projects/icognition/backend/app/api/routes/chat.py`

- FastAPI router for chat endpoints
- REST endpoints:
  - `POST /api/v1/chat/sessions`: Create session
  - `GET /api/v1/chat/sessions`: List user sessions
  - `GET /api/v1/chat/sessions/{session_id}/messages`: Get messages
  - `POST /api/v1/chat/sessions/{session_id}/messages`: Send user message (returns saved message with ID)
  - `DELETE /api/v1/chat/sessions/{session_id}`: Delete session
  - `PUT /api/v1/chat/sessions/{session_id}/scope`: Update scope
  - `PUT /api/v1/chat/sessions/{session_id}/title`: Update title
- SSE endpoint:
  - `GET /api/v1/chat/sessions/{session_id}/stream?message_id={message_id}`: Stream AI response via Server-Sent Events
  - Validates session ownership and message existence
  - Streams assistant responses via `chat_agent_service.get_stream()`
  - Sends SSE events: `stream_chunk`, `end_stream`, `error`
  - Saves assistant response after streaming completes
- WebSocket endpoint (legacy, retained for backward compatibility):
  - `WS /api/v1/chat/ws/{session_id}/{user_id}`: Legacy WebSocket streaming (not used by frontend)

### Chat Session Service
**File**: `/Users/eboraks/Projects/icognition/backend/app/services/chat_session_service.py`

- Database service for chat sessions and messages
- Key methods:
  - `create_chat_session()`: Create new session
  - `get_user_sessions()`: List user's sessions
  - `get_session_messages()`: Get messages for session
  - `save_message()`: Save user/assistant message
  - `delete_session()`: Delete session and messages
  - `update_session_title()`: Update session title
- Auto-renames session on first user message
- Updates `updated_at` timestamp for ordering

### Chat Agent Service
**File**: `/Users/eboraks/Projects/icognition/backend/app/services/chat_agent_service.py`

- LangGraph ReAct agent for AI responses
- Uses PostgreSQL checkpointer for conversation memory
- Streams responses via `get_stream()` method
- Features:
  - Context-aware document retrieval tool
  - Scope-based filtering (all_library or specific entity/document)
  - HTML content cleaning
  - Error handling with retry logic
- System prompt emphasizes document retrieval and synthesis

### Chat Formatting Utility
**File**: `/Users/eboraks/Projects/icognition/backend/app/utils/chat_formatting.py`

- Converts plain text/markdown to sanitized HTML
- Features:
  - Paragraph preservation
  - Bullet list formatting (`*`, `-`, `•`)
  - Markdown-style emphasis (`**bold**`, `*italic*`)
  - URL linkification
  - HTML escaping for security

### SSE Implementation Details
**File**: `/Users/eboraks/Projects/icognition/backend/app/api/routes/chat.py`

- SSE streaming uses FastAPI's `StreamingResponse` with `text/event-stream` media type
- Headers include `Cache-Control: no-cache`, `Connection: keep-alive`, `X-Accel-Buffering: no`
- Generator function `generate_stream()` yields SSE-formatted events
- Events follow SSE format: `event: {type}\ndata: {json}\n\n`

### Data Models
**File**: `/Users/eboraks/Projects/icognition/backend/app/models.py`

**ChatSession** (lines 1015-1042):
- `id`: Primary key
- `user_id`: Firebase UID
- `title`: Session title
- `scope_type`: "all_library" or "collection"
- `scope_id`: Optional collection/entity/document ID
- `thread_id`: LangGraph checkpointer thread ID
- `created_at`, `updated_at`: Timestamps
- `messages`: Relationship to ChatMessage

**ChatMessage** (lines 1045-1065):
- `id`: Primary key
- `session_id`: Foreign key to ChatSession
- `role`: "user" or "assistant"
- `content`: HTML-formatted message content
- `message_metadata`: Optional JSONB for LangGraph metadata
- `created_at`: Timestamp

---

## Key Implementation Details

### REST + SSE Message Protocol

**Client → Server (REST POST)**:
```http
POST /api/v1/chat/sessions/{session_id}/messages
Content-Type: application/json
Authorization: Bearer {firebase_token}

{
  "content": "User message text"
}
```

**Server → Client (REST Response)**:
```json
{
  "id": 123,
  "session_id": 1,
  "role": "user",
  "content": "User message text",
  "created_at": "2024-01-01T12:00:00Z"
}
```

**Client → Server (SSE GET)**:
```http
GET /api/v1/chat/sessions/{session_id}/stream?message_id={message_id}
Accept: text/event-stream
Authorization: Bearer {firebase_token}
```

**Server → Client (SSE Events)**:
```
event: stream_chunk
data: {"type": "stream_chunk", "content": "<p>HTML formatted content</p>", "message_id": "uuid-string"}

event: end_stream
data: {"type": "end_stream", "content": "<p>Final HTML formatted content</p>", "message_id": "uuid-string"}

event: error
data: {"type": "error", "content": "Error message", "message_id": "uuid-string"}
```

### Frontend Message Flow

1. User types message → `ChatPanel.sendMessage()`
2. Calls `chatStore.sendMessage()` with session ID
3. Store adds user message to `activeSession.messages`
4. Store creates placeholder assistant message with `pending: true`
5. Store sends message via REST API (`POST /sessions/{id}/messages`)
6. Store receives saved message with `id` from REST response
7. Store starts SSE stream (`GET /sessions/{id}/stream?message_id={id}`)
8. Store receives `stream_chunk` SSE events → updates placeholder content
9. Store receives `end_stream` SSE event → finalizes message, sets `pending: false`
10. `ChatPanel` watcher syncs store messages to local `messages` array
11. UI re-renders with updated content

### Session Management

- Each chat tab has a unique backend session ID
- Sessions are isolated: messages stored per-session
- Switching tabs calls `chatStore.switchActiveSession()`
- SSE connections are per-message (no persistent connection needed)
- Session scope (entity/document filters) stored in `ChatSession.scope_type` and `scope_id`

### Authentication

- Frontend: Firebase Auth with ID token injection via Axios interceptors (REST) and fetch headers (SSE)
- Backend: `get_authenticated_user_context` dependency validates Firebase tokens
- All endpoints require authenticated user
- SSE endpoint validates session ownership and message existence before streaming

### Environment Variables

**Frontend**:
- `VITE_APP_API_BASE_URL`: Backend API base URL (SSE uses `http://` or `https://`)

**Backend**:
- `GOOGLE_API_KEY`: Gemini API key
- Database connection string (for LangGraph checkpointer)
- LangSmith tracing configuration (optional)

---

## Replication Checklist for iPhone App

### Frontend (iOS/Swift)

- [ ] Implement chat session store (similar to Pinia store)
- [ ] Create chat UI component with message list and input
- [ ] Implement SSE client for streaming (using `URLSession` with `URLSessionDataTask` or `EventSource` equivalent)
- [ ] Handle SSE event types: `stream_chunk`, `end_stream`, `error`
- [ ] Implement session management (create, switch, delete)
- [ ] Add Firebase Auth token injection for REST API calls and SSE headers
- [ ] Handle pending message states (loading spinner)
- [ ] Implement auto-scroll to bottom
- [ ] Format HTML content in messages (or use native text rendering)
- [ ] Implement REST API call to send messages before starting SSE stream

### Backend Integration

- [ ] Use existing REST endpoints for session management
- [ ] Send messages via REST: `POST {API_BASE}/api/v1/chat/sessions/{session_id}/messages`
- [ ] Extract `message_id` from REST response
- [ ] Connect to SSE endpoint: `GET {API_BASE}/api/v1/chat/sessions/{session_id}/stream?message_id={message_id}`
- [ ] Parse SSE event format (`event: {type}\ndata: {json}`)
- [ ] Handle streaming: accumulate chunks until `end_stream`
- [ ] Display errors from `error` event type
- [ ] Handle SSE connection lifecycle (no persistent connection needed - per message)

### Data Models

- [ ] `ChatSession`: id, title, scope_type, scope_id, timestamps
- [ ] `ChatMessage`: id, session_id, role, content, timestamp
- [ ] Map backend models to iOS models

### Key Files Reference

**Frontend**:
- `/Users/eboraks/Projects/icognition/frontend/src/components/knowledge_explorer/ChatPanel.vue`
- `/Users/eboraks/Projects/icognition/frontend/src/stores/chat_store.ts`
- `/Users/eboraks/Projects/icognition/frontend/src/stores/knowledgeExplorerStore.ts`
- `/Users/eboraks/Projects/icognition/frontend/src/services/chatService.ts`
- `/Users/eboraks/Projects/icognition/frontend/src/services/knowledgeService.ts`
- `/Users/eboraks/Projects/icognition/frontend/src/views/library/KnowledgeExplorer.vue`

**Backend**:
- `/Users/eboraks/Projects/icognition/backend/app/api/routes/chat.py` (REST + SSE endpoints)
- `/Users/eboraks/Projects/icognition/backend/app/services/chat_session_service.py`
- `/Users/eboraks/Projects/icognition/backend/app/services/chat_agent_service.py`
- `/Users/eboraks/Projects/icognition/backend/app/utils/chat_formatting.py`
- `/Users/eboraks/Projects/icognition/backend/app/models.py` (ChatSession, ChatMessage)
- `/Users/eboraks/Projects/icognition/backend/SSE_MIGRATION.md` (Migration documentation)

---

## Notes

- All message content is HTML-formatted on the backend. The iPhone app should either render HTML or strip HTML tags for plain text display.
- SSE connections are per-message, not per-session. Each message requires a separate SSE connection that closes after the response completes.
- Session scope (entity/document filters) affects which documents the AI can retrieve via the `retrieve_documents_tool`.
- The backend uses LangGraph's PostgreSQL checkpointer for conversation memory, so each session maintains context across messages.
- Error handling: If SSE stream fails, the frontend should show an error message and allow retry. The placeholder message should be updated with the error.
- **Two-step process**: First send message via REST (get `message_id`), then start SSE stream with that `message_id`.
- SSE uses standard HTTP with `Accept: text/event-stream` header and Firebase token in `Authorization` header.
- The WebSocket endpoint (`/ws/{session_id}/{user_id}`) is retained for backward compatibility but is not used by the frontend.

