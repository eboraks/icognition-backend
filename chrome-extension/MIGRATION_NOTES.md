# Chrome Extension Backend Migration Notes

## Overview
This document tracks the migration of the Chrome extension from the old backend to the new FastAPI backend with WebSocket support.

## Completed Changes

### Backend Changes ✅
1. **WebSocket Implementation** (`backend/app/api/routes/websocket.py`)
   - Created ConnectionManager class for managing WebSocket connections
   - Implemented `/ws/{user_id}/extension` endpoint
   - Added heartbeat mechanism and automatic reconnection support
   - Handles message types: `connected`, `document_ready`, `progress_percentage`, `error`, `ping/pong`

2. **Background Task Updates** (`backend/app/api/routes/bookmarks.py`)
   - Modified `_process_document_content` to send WebSocket updates
   - Sends progress updates at 10%, 30%, 80%, and 100%
   - Sends `document_ready` message with summary and bullet points
   - Sends error notifications via WebSocket

3. **Main App Registration** (`backend/app/main.py`)
   - Registered WebSocket router

### Extension Changes ✅
1. **API Endpoints Updated** (`chrome-extension/public/js/background.js`)
   - Changed to use `/bookmarks/` endpoints
   - Updated `POST /bookmarks/` for creating bookmarks
   - Updated `GET /bookmarks/find?query=<url>` for searching
   - Updated `DELETE /bookmarks/{id}` for deleting
   - Removed chat-related endpoints

2. **Firebase Authentication** (`chrome-extension/public/js/background.js`)
   - Added `getFirebaseIdToken()` function
   - Updated all fetch calls to include `Authorization: Bearer <token>` header
   - Added token validation in requests

3. **WebSocket Connection** (`chrome-extension/public/js/background.js`)
   - Updated message handlers for new backend format
   - Handles: `connected`, `heartbeat`, `pong`, `document_ready`, `progress_percentage`, `error`
   - Removed chat-related message handling

4. **Bookmark Functions** (`chrome-extension/public/js/background.js`)
   - Updated `postBookmark` to use new request format (BookmarkCreateRequest)
   - Updated `searchBookmarksByUrl` to use new endpoint
   - Updated `deleteBookmark` to include auth token
   - Updated `refreshBookmarksCache` to use new paginated endpoint
   - Updated `storeBookmarks` to use new schema

5. **Removed Chat Features** (`chrome-extension/public/js/background.js`)
   - Removed `fetchChat`, `fetchAskQuestion`, `delteChatMessage` functions
   - Removed chat message handlers
   - Removed `renderDocument` function (now via WebSocket)

6. **Popup Component** (`chrome-extension/src/components/Popup.vue`)
   - Changed from `chat_messages` to `document_summary` ref
   - Changed from `chatsByUrl` to `summariesByUrl` storage
   - Updated `NEW_DOC` handler to extract summary and bullet points
   - Removed chat message handlers (`CHAT_READY`, `CHAT_MESSAGE`, `ASK_ANSWER`, `SUGGESTED_QUESTIONS`)
   - Updated template to show summary and bullet points instead of chat interface
   - Removed question input and autocomplete functionality
   - Updated error handling

## Remaining Work

### Backend
- [ ] Test WebSocket connections with actual extension
- [ ] Verify progress updates are sent correctly
- [ ] Test error handling and reconnection logic

### Extension
- [ ] Remove remaining chat-related functions from Popup.vue:
  - `handleKeydownInTextarea`
  - `handleKeyDown`
  - `handleTextareaInput`
  - `handleTextareaFocus`
  - `handleTextareaBlur`
  - `selectSuggestedQuestion`
  - `scrollChatToBottom`
  - `handleAsk`
  - All keyboard/autocomplete handlers
- [ ] Remove unused refs: `suggestedQuestions`, `selectedQuestion`, `filteredQuestions`, `showAutocomplete`, `activeIndex`, `allowBlurToHide`, `questionTextarea`
- [ ] Add CSS styles for document summary display
- [ ] Test with actual backend

### Environment Configuration
Note: `.env` files are gitignored. Create these manually:

**`.env.development`:**
```
VITE_BASE_URL=http://localhost:8000
VITE_WS_URL=ws://localhost:8000
VITE_ICOGNITION_APP_URL=http://localhost:5173
```

**`.env.production`:**
```
VITE_BASE_URL=https://icognition-api-scv-mheo5yycwa-uc.a.run.app
VITE_WS_URL=wss://icognition-api-scv-mheo5yycwa-uc.a.run.app
VITE_ICOGNITION_APP_URL=https://app.icognition.ai
```

## Testing Checklist

### Backend Tests
- [ ] Start backend server
- [ ] Verify WebSocket endpoint is accessible
- [ ] Test WebSocket connection with a test client
- [ ] Create a bookmark and verify progress updates
- [ ] Verify document_ready message contains correct data

### Extension Tests
- [ ] Build extension: `npm run build:dev`
- [ ] Load extension in Chrome
- [ ] Test authentication flow
- [ ] Test bookmark creation
- [ ] Verify WebSocket connection establishes
- [ ] Verify progress updates display
- [ ] Verify document summary displays correctly
- [ ] Test delete bookmark functionality
- [ ] Test tab switching preserves state
- [ ] Test error handling

## Migration Notes

### Breaking Changes
1. Chrome storage schema has changed - users will need to re-bookmark pages
2. Chat history is not preserved (temporary until chat re-implementation)
3. Users need to re-authenticate to get new Firebase ID tokens

### Data Format Changes

**Old Bookmark Format:**
```javascript
{
    id: string,
    url: string,
    title: string,
    update_at: datetime,
    user_id: string,
    filename: string,
    document_id: string
}
```

**New Bookmark Format:**
```javascript
{
    id: UUID,
    url: string,
    title: string,
    description: string | null,
    is_processed: boolean,
    processing_status: string | null,
    created_at: datetime,
    updated_at: datetime,
    user_id: string,
    document_id: UUID | null
}
```

### WebSocket Message Format

**From Backend to Extension:**

1. Connection Confirmation:
```json
{
    "type": "connected",
    "data": {
        "user_id": "...",
        "timestamp": "...",
        "message": "..."
    }
}
```

2. Progress Update:
```json
{
    "type": "progress_percentage",
    "data": 30
}
```

3. Document Ready:
```json
{
    "type": "document_ready",
    "data": {
        "id": "...",
        "title": "...",
        "url": "...",
        "ai_is_about": "...",
        "ai_bullet_points": ["..."],
        "created_at": "...",
        "updated_at": "..."
    }
}
```

4. Error:
```json
{
    "type": "error",
    "data": "error message"
}
```

**From Extension to Backend:**

1. Ping:
```json
{
    "type": "ping"
}
```

## Future Enhancements (Post-Migration)

1. Re-implement chat functionality with new backend
2. Add suggested questions feature
3. Implement citation highlighting
4. Add document regeneration endpoint
5. Optimize WebSocket connection for battery life
6. Add offline support


