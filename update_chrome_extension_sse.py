#!/usr/bin/env python3
"""
Script to migrate Chrome extension from WebSocket to SSE
"""

import re
import sys

def update_background_js(file_path):
    with open(file_path, 'r') as f:
        content = f.read()
    
    # 1. Replace socket variable declaration
    content = re.sub(
        r'const socket = ref\(null\)',
        r'let eventSourceController = null; // AbortController for SSE',
        content
    )
    
    # 2. Replace heartbeatInterval variable
    content = re.sub(
        r'let heartbeatInterval = null;',
        r'// Removed heartbeatInterval - SSE handles this automatically',
        content
    )
    
    # 3. Replace registerWebSocketConnection function
    websocket_function = r'const registerWebSocketConnection = async \(\) => \{.*?\n\}'
    sse_function = '''const registerSSEConnection = async () => {
    // Prevent multiple simultaneous connection attempts
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
                    const lines = buffer.split('\\n');
                    buffer = lines.pop() || '';

                    for (const line of lines) {
                        if (line.startsWith('event: ')) {
                            const eventType = line.substring(7).trim();
                            continue;
                        }

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
        console.info('Store session user:', store.session_user);
        console.error('Error setting up SSE connection:', error);
        isConnecting = false;
        handleSSEDisconnect();
    }
}

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
}'''
    
    # Use a more specific pattern to match the entire function
    content = re.sub(
        r'const registerWebSocketConnection = async \(\) => \{[^}]*\n\s*\}',
        sse_function,
        content,
        flags=re.DOTALL
    )
    
    # 4. Replace cleanupWebSocket function
    cleanup_websocket = r'const cleanupWebSocket = \(\) => \{.*?\n\}'
    cleanup_sse = '''const cleanupSSE = () => {
    if (reconnectTimeout) {
        clearTimeout(reconnectTimeout);
        reconnectTimeout = null;
    }
    
    if (eventSourceController) {
        eventSourceController.abort();
        eventSourceController = null;
    }
    
    isConnecting = false;
}'''
    
    content = re.sub(
        cleanup_websocket,
        cleanup_sse,
        content,
        flags=re.DOTALL
    )
    
    # 5. Remove isWebSocketOpen function
    content = re.sub(
        r'//Check if socket is open\s+function isWebSocketOpen\(\) \{.*?return false\s+\}',
        r'// Removed isWebSocketOpen - not needed for SSE',
        content,
        flags=re.DOTALL
    )
    
    # 6. Replace all function calls
    content = content.replace('registerWebSocketConnection()', 'registerSSEConnection()')
    content = content.replace('cleanupWebSocket()', 'cleanupSSE()')
    
    # 7. Remove isWebSocketOpen check in postBookmark
    content = re.sub(
        r'\s+if \(isWebSocketOpen\(\) === false\) \{\s+console\.log\(\'postBookmark -> WebSocket is not open\'\)\s+registerSSEConnection\(\)\s+\}',
        r'// SSE connection is maintained automatically, no need to check',
        content
    )
    
    with open(file_path, 'w') as f:
        f.write(content)
    
    print(f"✅ Updated {file_path}")
    print("⚠️  Please review the changes and test the extension")

if __name__ == '__main__':
    file_path = '/Users/eboraks/Projects/icognition/chrome-extension/public/js/background.js'
    update_background_js(file_path)

