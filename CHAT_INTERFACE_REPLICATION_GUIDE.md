# Chat Interface Replication Guide

This document provides a concise summary with absolute file paths to help replicate the chat interface from the web app to the iPhone app.

## Architecture Overview

The chat interface follows a **session-based, WebSocket-streaming architecture** with the following key components:

1. **Frontend**: Vue 3 + Pinia stores managing chat sessions and WebSocket connections
2. **Backend**: FastAPI with WebSocket endpoints streaming AI responses via LangGraph
3. **State Management**: Session isolation with per-session message histories
4. **Real-time Communication**: WebSocket streaming with structured message envelopes

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

- Pinia store managing chat sessions and WebSocket connections
- Key functions:
  - `loadSessions()`: Fetch all user sessions
  - `createSession()`: Create new chat session
  - `sendMessage()`: Send message via WebSocket, handle streaming
  - `connectWebSocket()`: Establish WebSocket connection per session
  - `switchActiveSession()`: Switch between chat sessions
- WebSocket message handling:
  - `stream_chunk`: Accumulates streaming content
  - `end_stream`: Finalizes message, removes pending flag
  - `error`: Displays error messages
- Messages stored per-session in `activeSession.value.messages`

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
  - `DELETE /api/v1/chat/sessions/{session_id}`: Delete session
  - `PUT /api/v1/chat/sessions/{session_id}/scope`: Update scope
  - `PUT /api/v1/chat/sessions/{session_id}/title`: Update title
- WebSocket endpoint:
  - `WS /api/v1/chat/ws/{session_id}/{user_id}`: Real-time chat streaming
  - Validates session ownership
  - Saves user messages immediately
  - Streams assistant responses via `chat_agent_service.get_stream()`
  - Sends structured messages: `stream_chunk`, `end_stream`, `error`

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

### WebSocket Manager
**File**: `/Users/eboraks/Projects/icognition/backend/app/api/routes/websocket.py`

- `ConnectionManager` class for WebSocket connection management
- Tracks connections by user_id and channel
- Used by chat router for connection lifecycle

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

### WebSocket Message Protocol

**Client → Server**:
```json
{
  "content": "User message text"
}
```

**Server → Client**:
```json
{
  "type": "stream_chunk",
  "content": "<p>HTML formatted content</p>",
  "message_id": "uuid-string"
}
```

```json
{
  "type": "end_stream",
  "content": "<p>Final HTML formatted content</p>",
  "message_id": "uuid-string"
}
```

```json
{
  "type": "error",
  "content": "Error message",
  "message_id": "uuid-string"
}
```

### Frontend Message Flow

1. User types message → `ChatPanel.sendMessage()`
2. Calls `chatStore.sendMessage()` with session ID
3. Store adds user message to `activeSession.messages`
4. Store creates placeholder assistant message with `pending: true`
5. Store sends message via WebSocket
6. Store receives `stream_chunk` messages → updates placeholder content
7. Store receives `end_stream` → finalizes message, sets `pending: false`
8. `ChatPanel` watcher syncs store messages to local `messages` array
9. UI re-renders with updated content

### Session Management

- Each chat tab has a unique backend session ID
- Sessions are isolated: messages stored per-session
- Switching tabs calls `chatStore.switchActiveSession()`
- WebSocket reconnects when switching sessions
- Session scope (entity/document filters) stored in `ChatSession.scope_type` and `scope_id`

### Authentication

- Frontend: Firebase Auth with ID token injection via Axios interceptors
- Backend: `get_authenticated_user_context` dependency validates Firebase tokens
- All endpoints require authenticated user
- WebSocket validates session ownership before accepting connection

### Environment Variables

**Frontend**:
- `VITE_APP_API_BASE_URL`: Backend API base URL (WebSocket uses `ws://` or `wss://`)

**Backend**:
- `GOOGLE_API_KEY`: Gemini API key
- Database connection string (for LangGraph checkpointer)
- LangSmith tracing configuration (optional)

---

## Replication Checklist for iPhone App

### Frontend (iOS/Swift)

- [ ] Implement chat session store (similar to Pinia store)
- [ ] Create chat UI component with message list and input
- [ ] Implement WebSocket client for streaming
- [ ] Handle message types: `stream_chunk`, `end_stream`, `error`
- [ ] Implement session management (create, switch, delete)
- [ ] Add Firebase Auth token injection for API calls
- [ ] Handle pending message states (loading spinner)
- [ ] Implement auto-scroll to bottom
- [ ] Format HTML content in messages (or use native text rendering)

### Backend Integration

- [ ] Use existing REST endpoints for session management
- [ ] Connect to WebSocket endpoint: `ws://{API_BASE}/api/v1/chat/ws/{session_id}/{user_id}`
- [ ] Parse WebSocket message envelope (`type`, `content`, `message_id`)
- [ ] Handle streaming: accumulate chunks until `end_stream`
- [ ] Display errors from `error` message type
- [ ] Implement reconnection logic for WebSocket

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
- `/Users/eboraks/Projects/icognition/backend/app/api/routes/chat.py`
- `/Users/eboraks/Projects/icognition/backend/app/services/chat_session_service.py`
- `/Users/eboraks/Projects/icognition/backend/app/services/chat_agent_service.py`
- `/Users/eboraks/Projects/icognition/backend/app/utils/chat_formatting.py`
- `/Users/eboraks/Projects/icognition/backend/app/models.py` (ChatSession, ChatMessage)
- `/Users/eboraks/Projects/icognition/backend/app/api/routes/websocket.py`

---

## Notes

- All message content is HTML-formatted on the backend. The iPhone app should either render HTML or strip HTML tags for plain text display.
- The WebSocket connection is session-specific. Each chat tab/session requires its own WebSocket connection.
- Session scope (entity/document filters) affects which documents the AI can retrieve via the `retrieve_documents_tool`.
- The backend uses LangGraph's PostgreSQL checkpointer for conversation memory, so each session maintains context across messages.
- Error handling: If WebSocket fails, the frontend should show an error message and allow retry.

