# Chrome Extension SSE Migration Guide

## Overview

This guide explains how to migrate the Chrome extension from WebSocket to Server-Sent Events (SSE) for document processing notifications.

## Backend Changes (Completed)

1. **New SSE Endpoint Created** (`backend/app/api/routes/notifications.py`)
   - `GET /api/v1/notifications/stream`
   - Requires Firebase authentication
   - Streams notifications: `connected`, `heartbeat`, `document_ready`, `progress_percentage`, `error`

2. **Backend Updated to Use SSE** (`backend/app/api/routes/bookmarks.py`)
   - All `ws_manager.send_personal_message()` calls replaced with `notification_manager.send_notification()`
   - No more WebSocket channel management needed

## Chrome Extension Changes Required

### 1. Replace WebSocket with SSE

**File:** `chrome-extension/public/js/background.js` (or equivalent)

**Remove:**
- `registerWebSocketConnection()` function
- `cleanupWebSocket()` function
- `isWebSocketOpen()` function
- WebSocket-related variables: `socket`, `heartbeatInterval`

**Add:**
- `registerSSEConnection()` function
- `cleanupSSE()` function
- `handleSSEMessage()` function
- `handleSSEDisconnect()` function
- `eventSourceController` variable (AbortController)

### 2. SSE Connection Implementation

```javascript
// Variables
let isConnecting = false;
let reconnectAttempts = 0;
const maxReconnectAttempts = 5;
let reconnectTimeout = null;
let eventSourceController = null; // AbortController for SSE

// Register SSE connection
const registerSSEConnection = async () => {
    if (isConnecting) {
        console.log('Already attempting to connect, skipping');
        return;
    }
    
    isConnecting = true;
    
    const store = await chrome.storage.session.get(["session_user"]);
    if (!store.session_user || !store.session_user.stsTokenManager || !store.session_user.uid) {
        console.log('registerSSEConnection -> user is null or invalid auth data');
        isConnecting = false;
        return;
    }

    cleanupSSE();
    
    try {
        const token = await getFirebaseIdToken();
        if (!token) {
            console.error('Failed to get Firebase token');
            isConnecting = false;
            return;
        }

        const sse_url = `${base_url}/api/v1/notifications/stream`;
        console.log('SSE connection initiated:', sse_url);
        
        const controller = new AbortController();
        eventSourceController = controller;
        
        fetch(sse_url, {
            method: 'GET',
            headers: {
                'Authorization': `Bearer ${token}`,
                'Accept': 'text/event-stream',
            },
            signal: controller.signal,
        }).then(response => {
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const reader = response.body?.getReader();
            const decoder = new TextDecoder();
            let buffer = '';

            if (!reader) {
                throw new Error('Response body is not readable');
            }

            console.log('SSE connection opened successfully');
            isConnecting = false;
            reconnectAttempts = 0;

            function processChunk() {
                return reader.read().then(({ done, value }) => {
                    if (done) {
                        console.log('SSE stream ended');
                        handleSSEDisconnect();
                        return;
                    }

                    buffer += decoder.decode(value, { stream: true });
                    const lines = buffer.split('\n');
                    buffer = lines.pop() || '';

                    for (const line of lines) {
                        if (line.startsWith('data: ')) {
                            const data = line.substring(6).trim();
                            try {
                                const message = JSON.parse(data);
                                handleSSEMessage(message);
                            } catch (e) {
                                console.error('Failed to parse SSE data:', data, e);
                            }
                        }
                    }

                    return processChunk();
                }).catch(error => {
                    if (error.name === 'AbortError') {
                        console.log('SSE connection aborted');
                    } else {
                        console.error('Error reading SSE stream:', error);
                        handleSSEDisconnect();
                    }
                });
            }

            processChunk();
        }).catch(error => {
            if (error.name === 'AbortError') {
                console.log('SSE connection aborted');
            } else {
                console.error('Error opening SSE connection:', error);
                handleSSEDisconnect();
            }
        });
    } catch (error) {
        console.error('Error setting up SSE connection:', error);
        isConnecting = false;
        handleSSEDisconnect();
    }
}

// Handle SSE messages
function handleSSEMessage(message) {
    console.log('SSE message received:', message);
    
    if (message.type === 'connected') {
        console.log('SSE connected confirmation:', message.data);
        return;
    }
    
    if (message.type === 'heartbeat') {
        console.log('SSE heartbeat received');
        return;
    }
    
    if (message.type === 'document_ready') {
        console.log('SSE document ready:', message.data);
        chrome.runtime.sendMessage({
            name: CommunicationEnum.NEW_DOC,
            data: message.data,
        }).catch(error => {
            console.error('Error sending NEW_DOC message:', error);
        });
    }
    
    if (message.type === 'progress_percentage') {
        console.log('SSE progress percentage:', message.data);
        chrome.runtime.sendMessage({
            name: CommunicationEnum.PROGRESS_PERCENTAGE,
            data: message.data,
        }).catch(error => {
            console.error('Error sending PROGRESS_PERCENTAGE message:', error);
        });
    }
    
    if (message.type === 'error') {
        console.log('SSE error message:', message.data);
        chrome.runtime.sendMessage({
            name: CommunicationEnum.ERROR,
            data: message.data,
        }).catch(error => {
            console.error('Error sending ERROR message:', error);
        });
    }
}

// Handle SSE disconnection
function handleSSEDisconnect() {
    cleanupSSE();
    
    if (reconnectAttempts < maxReconnectAttempts) {
        const delay = Math.min(1000 * Math.pow(2, reconnectAttempts), 30000);
        console.log(`Scheduling reconnect attempt ${reconnectAttempts + 1} in ${delay}ms`);
        
        reconnectTimeout = setTimeout(() => {
            reconnectAttempts++;
            console.log(`Attempting to reconnect SSE (attempt ${reconnectAttempts})`);
            registerSSEConnection();
        }, delay);
    } else {
        console.log('Maximum reconnection attempts reached, giving up');
    }
}

// Cleanup SSE connection
const cleanupSSE = () => {
    if (reconnectTimeout) {
        clearTimeout(reconnectTimeout);
        reconnectTimeout = null;
    }
    
    if (eventSourceController) {
        eventSourceController.abort();
        eventSourceController = null;
    }
    
    isConnecting = false;
}
```

### 3. Update All References

**Replace:**
- `registerWebSocketConnection()` → `registerSSEConnection()`
- `cleanupWebSocket()` → `cleanupSSE()`
- `isWebSocketOpen()` → Remove (not needed for SSE)
- `socket.value` → Remove (not needed)

**In `postBookmark()` function:**
```javascript
// OLD:
if (isWebSocketOpen() === false) {
    registerWebSocketConnection()
}

// NEW:
// SSE connection is maintained automatically, no need to check
```

**In storage change listener:**
```javascript
// OLD:
registerWebSocketConnection()

// NEW:
registerSSEConnection()
```

**In `server-is` message handler:**
```javascript
// OLD:
registerWebSocketConnection()

// NEW:
registerSSEConnection()
```

**In extension startup/shutdown:**
```javascript
// OLD:
cleanupWebSocket()

// NEW:
cleanupSSE()
```

## Testing

1. **Build the extension:**
   ```bash
   cd chrome-extension
   npm run build
   ```

2. **Load extension in Chrome:**
   - Open `chrome://extensions/`
   - Enable "Developer mode"
   - Click "Load unpacked"
   - Select the `chrome-extension/dist` directory

3. **Test scenarios:**
   - Create a bookmark and verify progress updates appear
   - Verify document_ready notification is received
   - Test reconnection by disconnecting network briefly
   - Verify error notifications are received

## Benefits

1. **More Reliable:** SSE works better with Cloud Run load balancers
2. **Simpler:** No WebSocket connection state management
3. **Automatic Reconnection:** Browser handles SSE reconnection automatically
4. **Better for Serverless:** No WebSocket timeout issues

## After Migration

Once SSE is working and tested:
1. Remove WebSocket endpoint from backend (`backend/app/api/routes/websocket.py`)
2. Remove WebSocket router registration from `backend/app/main.py`
3. Remove `ConnectionManager` class if no longer needed
4. Update documentation

