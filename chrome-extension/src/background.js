import { ref, onMounted, watch } from 'vue'
import { cleanUrl, CommunicationEnum } from './composables/utils.js'
import { refreshFirebaseToken, isTokenExpired } from './firebase/config.js'

const user = ref(null)
let eventSourceController = null; // AbortController for SSE
let isSidePanelOpen = false; // Track side panel state


//Test adding comments 
let base_url = import.meta.env.VITE_BASE_URL || 'http://localhost:8000'

// Initialize base_url from storage
const initializeBaseUrl = async () => {
    try {
        const result = await chrome.storage.local.get(['backendEnvironment']);
        const environment = result.backendEnvironment || 'development';

        if (environment === 'development') {
            base_url = 'http://localhost:8000';
        } else {
            base_url = 'https://stg.api.icognition.ai';
        }
        console.log('Base URL initialized to:', base_url);
    } catch (error) {
        console.error('Error initializing base URL:', error);
    }
};

// Initialize on load
initializeBaseUrl().then(() => {
    // Also try to restore SSE connection on startup if user exists
    chrome.storage.session.get(["session_user"]).then((store) => {
        if (store.session_user && store.session_user.stsTokenManager && store.session_user.uid) {
            console.log('Background startup: Restoring SSE connection for UID:', store.session_user.uid);
            user.value = store.session_user;
            registerSSEConnection();
        } else {
            console.log('Background startup: No valid session found for SSE restoration');
        }
    });
});

const Endpoints = {
    ping: '/ping',
    bookmarks: '/bookmarks/',
    bookmark_find: '/bookmarks/find',
    bookmark_by_id: '/bookmarks/{ID}',
    document_by_id: '/documents/{ID}',
    delete_bookmark: '/bookmarks/{id}',
    chat_sessions: '/api/v1/chat/sessions',
    chat_messages: '/api/v1/chat/sessions/{sessionId}/messages',
    chat_stream: '/api/v1/chat/sessions/{sessionId}/stream',
    chat_suggest: '/api/v1/chat/sessions/{sessionId}/suggest',
}

// Listen to changes in storage and if session_user changes, refresh the bookmarks cache, or delete the cache if the user logs out
chrome.storage.onChanged.addListener((changes, namespace) => {
    for (let [key, { oldValue, newValue }] of Object.entries(changes)) {

        // Listen to update to session_user (login) to refresh the bookmarks cache
        if (key === 'session_user') {

            if (newValue === undefined) {
                console.log("Detected user logout: ", newValue)
                chrome.storage.local.remove('bookmarks')
            } else if (newValue !== undefined && oldValue === undefined) {
                // Validate that the new user has valid authentication data
                if (newValue.stsTokenManager && newValue.uid) {
                    console.log("Detected user login: ", newValue)
                    user.value = newValue
                    // Small delay to ensure Chrome storage has fully persisted the data
                    // before subsequent operations try to read it
                    setTimeout(() => {
                        refreshBookmarksCache(user.value.uid)
                        registerSSEConnection()
                    }, 100)
                } else {
                    console.log("Detected invalid user login data, clearing: ", newValue)
                    chrome.storage.session.remove('session_user')
                }
            }
        }
    }
});

// Add these variables to track connection state
let isConnecting = false;
let reconnectAttempts = 0;
let maxReconnectAttempts = 10;
let reconnectTimeout = null;
// Removed heartbeatInterval - SSE handles this automatically

// Global variable to store logged shortcuts
let recentShortcuts = [];
const MAX_SHORTCUTS = 20; // Maximum number of shortcuts to store

// Function to get Firebase ID token from stored user, with automatic refresh if needed
async function getFirebaseIdToken() {
    const store = await chrome.storage.session.get(["session_user"]);
    if (!store.session_user || !store.session_user.stsTokenManager) {
        console.log('getFirebaseIdToken -> No user or token manager found');
        return null;
    }

    const currentToken = store.session_user.stsTokenManager.accessToken;

    // Check if token is expired or about to expire
    if (isTokenExpired(currentToken)) {
        console.log('getFirebaseIdToken -> Token expired, refreshing...');
        try {
            const newToken = await refreshFirebaseToken();
            return newToken;
        } catch (error) {
            const errMsg = error?.message || error?.toString() || 'Unknown error';
            console.error('getFirebaseIdToken -> Failed to refresh token:', errMsg);
            return null;
        }
    }

    return currentToken;
}

// Helper function to make authenticated API calls with automatic token refresh
async function makeAuthenticatedRequest(url, options = {}) {
    const idToken = await getFirebaseIdToken();
    if (!idToken) {
        throw new Error('Authentication token not available');
    }

    // Add authorization header
    const headers = {
        'Authorization': `Bearer ${idToken}`,
        'Accept': 'application/json',
        'Content-Type': 'application/json',
        ...options.headers
    };

    const requestOptions = {
        ...options,
        headers
    };

    try {
        const response = await fetch(url, requestOptions);

        // If we get a 401, try to refresh the token and retry once
        if (response.status === 401) {
            console.log('makeAuthenticatedRequest -> Got 401, attempting token refresh...');
            try {
                const newToken = await refreshFirebaseToken();
                if (newToken) {
                    // Retry the request with the new token
                    const retryHeaders = {
                        ...headers,
                        'Authorization': `Bearer ${newToken}`
                    };
                    const retryOptions = {
                        ...requestOptions,
                        headers: retryHeaders
                    };

                    console.log('makeAuthenticatedRequest -> Retrying with refreshed token...');
                    return await fetch(url, retryOptions);
                }
            } catch (refreshError) {
                console.error('makeAuthenticatedRequest -> Token refresh failed:', refreshError);
            }
        }

        return response;
    } catch (error) {
        console.error('makeAuthenticatedRequest -> Request failed:', error);
        const errorMessage = error?.message || error?.toString() || 'Unknown error';

        // Check if it's a network/connection error
        if (errorMessage.includes('Failed to fetch') ||
            errorMessage.includes('NetworkError') ||
            errorMessage.includes('ERR_') ||
            error.name === 'TypeError') {
            // Send connection error message to popup
            chrome.runtime.sendMessage({
                name: 'connection-error',
                error: errorMessage,
                type: 'network_error'
            }).catch(() => {
                // Ignore if popup is not listening
            });
        }

        throw error;
    }
}

// Function to log commands from the commands API
function logCommand(command) {
    const shortcutInfo = {
        type: 'chrome.command',
        command: command,
        timestamp: new Date().toISOString()
    };

    console.log('Command Shortcut Detected:', shortcutInfo);

    // Add to recent shortcuts
    recentShortcuts.unshift(shortcutInfo);
    if (recentShortcuts.length > MAX_SHORTCUTS) {
        recentShortcuts.pop();
    }

    // Notify any open side panels
    try {
        chrome.runtime.sendMessage({
            name: 'shortcut-logged',
            shortcut: shortcutInfo
        }).catch(err => {
            // Ignore errors - side panel might not be open
        });
    } catch (e) {
        // Ignore errors - side panel might not be open
    }
}

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

            // Notify extension that SSE is connected
            chrome.runtime.sendMessage({
                name: 'sse-reconnected'
            }).catch(() => {
                console.log('Unable to notify extension of SSE reconnection (extension may be closed)');
            });

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
        }).then((response) => {
            console.log('render-document response: ', response);
        }).catch(error => {
            console.error('Error sending NEW_DOC message:', error);
        });
    }

    if (message.type === 'progress_percentage') {
        console.log('SSE progress percentage:', message.data);
        chrome.runtime.sendMessage({
            name: CommunicationEnum.PROGRESS_PERCENTAGE,
            data: message.data,
        }).then((response) => {
            console.log('progress_percentage response: ', response);
        }).catch(error => {
            console.error('Error sending PROGRESS_PERCENTAGE message:', error);
        });
    }

    if (message.type === 'error') {
        console.log('SSE error message:', message.data);
        chrome.runtime.sendMessage({
            name: CommunicationEnum.ERROR,
            data: message.data,
        }).then((response) => {
            console.log('error response: ', response);
        }).catch(error => {
            console.error('Error sending ERROR message:', error);
        });
    }
}

function handleSSEDisconnect() {
    cleanupSSE();

    // Notify extension that SSE is disconnected
    chrome.runtime.sendMessage({
        name: 'sse-disconnected'
    }).catch(() => {
        console.log('Unable to notify extension of SSE disconnection (extension may be closed)');
    });

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
        // Notify extension of final failure
        chrome.runtime.sendMessage({
            name: 'connection-error',
            error: 'SSE connection failed after maximum retry attempts',
            type: 'network_error'
        }).catch(() => {
            console.log('Unable to notify extension of connection error (extension may be closed)');
        });
    }
}


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



// Create a bookmark
async function postBookmark(tab) {

    let bookmark = null
    let bm_error = null
    let html = null


    const session_user = await chrome.storage.session.get(["session_user"])
    console.log('postBookmark -> user: ', session_user.session_user)


    //If no authproof or invalid auth data, return error
    if (!session_user.session_user || !session_user.session_user.stsTokenManager || !session_user.session_user.uid) {
        bm_error = 'User not authenticated or invalid auth data'
        console.log('postBookmark -> Invalid user data, clearing session')
        chrome.storage.session.remove('session_user')
        return { bookmark, error: bm_error }
    }


    function getBody() { return document.documentElement.innerHTML; }


    try {
        const injectionResults = await chrome.scripting.executeScript({
            target: { tabId: tab.id, allFrames: false },
            func: getBody,
        });

        if (injectionResults[0].result != null) {
            console.log('postBookmark -> HTML recieved from content script')
            html = injectionResults[0].result
        }
    } catch (error) {
        //If error, log error and continue without the html
        console.log('postBookmark error executing script: ', error)
    }


    try {
        // Clean the URL before sending to server
        const cleanedUrl = cleanUrl(tab.url);
        let response = await makeAuthenticatedRequest(`${base_url}${Endpoints.bookmarks}`, {
            method: 'POST',
            body: JSON.stringify({
                url: cleanedUrl,
                title: tab.title || "Untitled",
                content: html,
                description: null,
                metadata: {}
            }),
        })
        const _content = await response.json()
        return { status: response.status, content: _content }
    }
    catch (err) {
        console.error('postBookmark -> error:', err)
        return { status: 500, content: { detail: err.message || 'Failed to create bookmark' } }
    }
}

// Document regeneration removed - will be handled differently in future update

const sleep = (delay) => new Promise((resolve) => setTimeout(resolve, delay));

// Source: https://dev.to/ycmjason/javascript-fetch-retry-upon-failure-3p6g
async function fetch_retry(url, options, n) {
    try {
        const response = await fetch(url, options);
        console.log('fetch_retry -> attempts: ', n, ' url: ', url)
        if (response.status == 206 && n > 1) {
            await sleep(1500);
            console.log('fetch_retry -> retrying attempts: ', n, ' url: ', url)
            return fetch_retry(url, options, n - 1);
        } else if (response.status == 206 && n == 1) {
            throw new Error('Failed to fetch: ' + url);
        }
        else {
            return response.json();
        }
    } catch (error) {
        throw error;
    }
}

const searchBookmarksByUrl = async (user_id, url) => {
    // Only search if side panel is open
    if (!isSidePanelOpen) {
        console.log('Side panel is closed, skipping bookmark search');
        return { bookmark: undefined, error: null };
    }

    try {
        const cleanedUrl = cleanUrl(url);
        console.log('searchBookmarksByUrl -> url:', cleanedUrl);

        // First check local storage
        const value = await chrome.storage.local.get(["bookmarks"]);
        console.log('searchBookmarksByUrl -> local storage value:', value);

        if (value.bookmarks) {
            value.bookmarks = value.bookmarks.filter(bookmark => bookmark !== null && bookmark !== undefined);
            const found = value.bookmarks.find(bookmark => bookmark.url === cleanedUrl);
            if (found) {
                console.log('searchBookmarksByUrl -> found in local storage:', found);
                return { bookmark: found, error: null };
            }
        }


        // If not found locally, search server using new endpoint
        console.log('searchBookmarksByUrl -> not found in local storage, searching server');

        // Check if we have a token before making the request to avoid errors
        const token = await getFirebaseIdToken();
        if (!token) {
            console.log('searchBookmarksByUrl -> No auth token available, skipping server search');
            return { bookmark: undefined, error: null };
        }

        const searchUrl = `${base_url}${Endpoints.bookmark_find}?query=${encodeURIComponent(cleanedUrl)}`;
        let response = await makeAuthenticatedRequest(searchUrl, {
            method: 'GET',
        });

        if (response.status === 404) {
            const errorJson = await response.json();
            const errorMsg = (typeof errorJson.detail === 'string') ? errorJson.detail : JSON.stringify(errorJson.detail || errorJson);
            console.log('searchBookmarkByUrl -> 404: ', errorMsg);
            return { bookmark: undefined, error: errorMsg };
        }

        if (!response.ok) {
            const errorJson = await response.json();
            const errorMsg = (typeof errorJson.detail === 'string') ? errorJson.detail : JSON.stringify(errorJson.detail || errorJson);
            console.error('searchBookmarkByUrl -> error response: ', errorMsg);
            return { bookmark: undefined, error: errorMsg };
        }

        const data = await response.json();
        console.log('searchBookmarkByUrl -> server data: ', data);
        return { bookmark: data, error: null };
    } catch (err) {
        console.error('searchBookmarkByUrl -> error: ', err);
        const errorMessage = err?.message || err?.toString() || 'Unknown error';

        // Check if it's an auth or connection error
        if (errorMessage.includes('Authentication token not available') ||
            errorMessage.includes('Failed to fetch') ||
            errorMessage.includes('NetworkError')) {
            // Send error message to popup
            chrome.runtime.sendMessage({
                name: 'connection-error',
                error: errorMessage,
                type: 'auth_or_connection'
            }).catch(() => {
                // Ignore if popup is not listening
            });
        }

        return { bookmark: undefined, error: err };
    }
}




async function refreshBookmarksCache(user_uid) {
    try {

        // Fetch bookmarks from new endpoint (with pagination - get first 100)
        const url = `${base_url}${Endpoints.bookmarks}?page=1&page_size=100`;
        const response = await makeAuthenticatedRequest(url, {
            method: 'GET',
        });

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        const data = await response.json();
        const bookmarks = data.bookmarks || [];

        console.log('refreshBookmarksCache -> response: ', bookmarks);

        // Log size information
        const bookmarksSize = JSON.stringify(bookmarks).length;
        console.log('Bookmarks array size:', bookmarks.length, 'items');
        console.log('Total JSON string size:', bookmarksSize, 'bytes');
        if (bookmarks.length > 0) {
            console.log('Average size per bookmark:', Math.round(bookmarksSize / bookmarks.length), 'bytes');
        }

        // Log first few bookmarks to check their structure
        console.log('Sample bookmarks:', bookmarks.slice(0, 3));

        // First clear the bookmarks from storage
        await chrome.storage.local.remove('bookmarks');
        console.log('Bookmarks storage cleared successfully');

        // Then store the new bookmarks
        storeBookmarks(bookmarks);
    } catch (error) {
        const errMsg = error?.message || error?.toString() || 'Unknown error';
        console.error(`refreshBookmarksCache -> error from ${base_url}:`, errMsg);
    }
}




// Chat functions removed - will be re-implemented in future update


// Listen from popup to fetch document
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {

    if (request.name === 'create-chat-session') {
        handleCreateChatSession(request.data).then(sendResponse);
        return true;
    }

    if (request.name === 'get-chat-suggestion') {
        handleGetChatSuggestion(request.data).then(sendResponse);
        return true;
    }

    if (request.name === 'send-chat-message') {
        handleSendChatMessage(request.data).then(sendResponse);
        return true;
    }

    if (request.name === 'stream-chat-response') {
        handleStreamChatResponse(request.data);
        return false; // No response needed, events are sent via runtime.sendMessage
    }

    if (request.name === 'get-chat-messages') {
        handleGetChatMessages(request.data).then(sendResponse);
        return true;
    }

    // highlight-citation is handled by the message handler at line 881
    // Don't log unknown requests here - let other handlers process them
    // Return false so other listeners can handle the message
    return false;
})

async function handleCreateChatSession(data) {
    try {
        console.log('handleCreateChatSession:', data);
        const url = `${base_url}${Endpoints.chat_sessions}`;

        const response = await makeAuthenticatedRequest(url, {
            method: 'POST',
            body: JSON.stringify({
                title: data.title,
                scope_type: data.scope_type || 'document',
                scope_id: data.scope_id
            })
        });

        if (!response.ok) {
            const errorText = await response.text();
            throw new Error(`Failed to create session: ${response.status} - ${errorText}`);
        }

        const session = await response.json();
        return { success: true, data: session };
    } catch (error) {
        const errMsg = error?.message || error?.toString() || 'Unknown error';
        console.error(`Error creating chat session at ${base_url}:`, errMsg);
        return { success: false, error: errMsg };
    }
}

async function handleSendChatMessage(data) {
    try {
        console.log('handleSendChatMessage:', data);
        const url = `${base_url}${Endpoints.chat_messages.replace('{sessionId}', data.sessionId)}`;

        const response = await makeAuthenticatedRequest(url, {
            method: 'POST',
            body: JSON.stringify({
                content: data.content
            })
        });

        if (!response.ok) {
            const errorText = await response.text();
            throw new Error(`Failed to send message: ${response.status} - ${errorText}`);
        }

        const message = await response.json();
        return { success: true, data: message };
    } catch (error) {
        const errMsg = error?.message || error?.toString() || 'Unknown error';
        console.error(`Error sending chat message to ${base_url}:`, errMsg);
        return { success: false, error: errMsg };
    }
}

async function handleStreamChatResponse(data) {
    const { sessionId, messageId } = data;
    console.log(`Starting SSE stream for session ${sessionId}, message ${messageId}`);

    try {
        const token = await getFirebaseIdToken();
        if (!token) {
            throw new Error('No authentication token available');
        }

        const streamUrl = `${base_url}${Endpoints.chat_stream.replace('{sessionId}', sessionId)}?message_id=${messageId}`;

        const response = await fetch(streamUrl, {
            method: 'GET',
            headers: {
                'Authorization': `Bearer ${token}`,
                'Accept': 'text/event-stream',
            },
        });

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
            const { done, value } = await reader.read();
            if (done) {
                console.log('Chat SSE stream ended');
                chrome.runtime.sendMessage({
                    name: 'chat-stream-end',
                    data: { sessionId, messageId }
                }).catch(() => { }); // Ignore if popup closed
                break;
            }

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop() || '';

            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    const dataStr = line.substring(6).trim();
                    try {
                        const messageData = JSON.parse(dataStr);
                        // Forward the SSE message to the popup
                        chrome.runtime.sendMessage({
                            name: 'chat-stream-chunk',
                            data: { ...messageData, sessionId }
                        }).catch(() => { }); // Ignore if popup closed
                    } catch (e) {
                        console.error('Failed to parse chat SSE data:', dataStr, e);
                    }
                } else if (line.startsWith('event: error')) {
                    // Handle error event if needed, usually data line follows or is part of it?
                    // Standard SSE format usually has event: type \n data: ...
                    // If we just forwarded the parsed JSON above, we might be good if the backend sends structured JSON.
                    // The frontend store handles: type="stream_chunk", "end_stream", "error".
                    // Let's assume the backend sends these types in the JSON body as seen in chat_store.ts
                }
            }
        }

    } catch (error) {
        console.error('Error in chat stream:', error);
        chrome.runtime.sendMessage({
            name: 'chat-stream-error',
            data: { sessionId, messageId, error: error.message }
        }).catch(() => { });
    }
}

async function handleGetChatSuggestion(data) {
    try {
        console.log('handleGetChatSuggestion:', data);
        const url = `${base_url}${Endpoints.chat_suggest.replace('{sessionId}', data.sessionId)}`;

        const response = await makeAuthenticatedRequest(url, {
            method: 'POST',
            body: JSON.stringify({
                text: data.text,
                session_id: data.sessionId,
                context: data.context
            })
        });

        if (!response.ok) {
            const errorText = await response.text();
            throw new Error(`Failed to get suggestion: ${response.status} - ${errorText}`);
        }

        const result = await response.json();
        return { success: true, data: result };
    } catch (error) {
        const errMsg = error?.message || error?.toString() || 'Unknown error';
        console.error(`Error getting chat suggestion from ${base_url}:`, errMsg);
        return { success: false, error: errMsg };
    }
}

async function handleGetChatMessages(data) {
    try {
        console.log('handleGetChatMessages:', data);
        const url = `${base_url}${Endpoints.chat_messages.replace('{sessionId}', data.sessionId)}`;

        const response = await makeAuthenticatedRequest(url, {
            method: 'GET'
        });

        if (!response.ok) {
            const errorText = await response.text();
            throw new Error(`Failed to get messages: ${response.status} - ${errorText}`);
        }

        const messages = await response.json();
        return { success: true, data: messages };
    } catch (error) {
        const errMsg = error?.message || error?.toString() || 'Unknown error';
        console.error(`Error getting chat messages from ${base_url}:`, errMsg);
        return { success: false, error: errMsg };
    }
}



async function sendDocumentToSidePanel(document) {

    // Send message to side panel to render bookmark
    try {
        let response = await chrome.runtime.sendMessage({
            name: 'render-document',
            data: document,
        })
        return response
    } catch (error) {
        console.log(`Render Bookmark, error sending message ${error}`)
    }
}


function storeBookmarks(new_bookmarks) {
    if (!Array.isArray(new_bookmarks)) new_bookmarks = [new_bookmarks]

    // Clean URLs and store bookmark data matching new schema
    new_bookmarks = new_bookmarks.map(bookmark => {
        if (bookmark && bookmark.url) {
            // Store fields matching BookmarkResponse model
            return {
                id: bookmark.id,  // UUID
                url: cleanUrl(bookmark.url),
                title: bookmark.title,
                description: bookmark.description,
                is_processed: bookmark.is_processed,
                processing_status: bookmark.processing_status,
                created_at: bookmark.created_at,
                updated_at: bookmark.updated_at,
                user_id: bookmark.user_id,
                document_id: bookmark.document_id
            };
        }
        return bookmark;
    });

    chrome.storage.local.get(["bookmarks"]).then((value) => {
        let bkmks = value.bookmarks || [];
        // Clean URLs in existing bookmarks if needed
        bkmks = bkmks.map(bookmark => {
            if (bookmark && bookmark.url) {
                return {
                    id: bookmark.id,
                    url: cleanUrl(bookmark.url),
                    title: bookmark.title,
                    description: bookmark.description,
                    is_processed: bookmark.is_processed,
                    processing_status: bookmark.processing_status,
                    created_at: bookmark.created_at,
                    updated_at: bookmark.updated_at,
                    user_id: bookmark.user_id,
                    document_id: bookmark.document_id
                };
            }
            return bookmark;
        });
        bkmks = Array.from(new Set([...bkmks, ...new_bookmarks]));
        chrome.storage.local.set({ bookmarks: bkmks }).then(() => {
            console.log("Bookmarks storage updated", bkmks);
        });
    });
}




const badgeOn = (tabId) => {
    chrome.action.setBadgeBackgroundColor(
        { color: 'rgba(22, 169, 32, 1)' },  // Also green
        () => { /* ... */ },
    );
    chrome.action.setBadgeText({ text: '✔', tabId: tabId });
}

const badgeOff = (tabId) => {
    console.log('badgeOff -> tabId: ', tabId)
    chrome.action.setBadgeText({ text: null, tabId: tabId });
}

const badgeToggle = async (tab) => {
    if (!tab || !tab.url) {
        console.log('badgeToggle -> skipped: tab or url is undefined');
        return;
    }
    console.log('badgeToggle -> url: ', tab.url)
    const result = await searchBookmarksByUrl(user.value?.uid, tab.url)
    if (result.bookmark != undefined) {
        console.log('badgeToggle -> bookmark found: ', result.bookmark)
        badgeOn(tab.id || tab.tabId)
    } else {
        console.log('badgeToggle -> bookmark not found')
        badgeOff(tab.id || tab.tabId)
    }
}


// Detect changes in active tab
chrome.tabs.onActivated.addListener(async (activeInfo) => {
    const tabId = activeInfo.tabId;
    console.log('tabs.onActivated', tabId)

    // Store the active tab ID in session storage
    await chrome.storage.session.set({ active_tab_id: tabId });
    console.log('Stored active tab ID in session storage:', tabId);

    chrome.tabs.get(tabId, async (tab) => {
        if (chrome.runtime.lastError) {
            console.log('tabs.onActivated -> get tab error (tab may be closed): ', chrome.runtime.lastError.message);
            return;
        }
        if (tab && tab.url) {
            console.log('tabs.onActivated -> get tab -> url: ', tab.url)
            badgeToggle(tab)
        }
    })
});


chrome.tabs.onUpdated.addListener(function (tabId, info) {
    if (info.status === 'complete') {
        // Store the active tab ID in session storage
        chrome.storage.session.set({ active_tab_id: tabId });
        console.log('Stored active tab ID in session storage (onUpdated):', tabId);

        chrome.tabs.get(tabId, async (tab) => {
            if (chrome.runtime.lastError) {
                console.log('tabs.onUpdated -> get tab error: ', chrome.runtime.lastError.message);
                return;
            }
            if (tab && tab.url) {
                console.log('tabs.onUpdated -> get tab -> url: ', tab.url)
                badgeToggle(tab)
            }
        })
    }
});



chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    if (request.name === 'server-is') {
        console.log('background.js got message. Server is')
        fetch_retry(`${base_url}/ping`, { method: 'GET', headers: { 'Accept': 'application/json', 'Content-Type': 'application/json', } }, 3)
            .then((response) => {
                registerSSEConnection()
                console.log('background.js got message. Server response: ', response)
                sendResponse({ status: 'up' })

            }).catch((error) => {
                console.log('background.js got message. Server error: ', error)
                sendResponse({ status: 'down' })
            })
        return true
    }
});

chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    if (request.name === 'check-for-bookmarks') {
        console.log('popup-opened -> query for active tab id:', request.tab.id, ' -> url: ', request.tab.url)
        searchBookmarksByUrl(user.value?.uid, request.tab.url).then((result) => {
            sendResponse(result)
        }).catch(err => {
            console.error('Error checking bookmarks:', err);
            sendResponse({ bookmark: undefined, error: err.message });
        });
        return true; // Keep channel open
    }
});

chrome.runtime.onMessage.addListener(
    (request, sender, sendResponse) => {

        // Handle message from side panel
        if (request.name === 'bookmark-page') {
            console.log('background.js got message. Bookmark Page for url: ', request.tab.url)

            postBookmark(request.tab).then((result) => {
                console.log('background.js postBookmark Results: ', result.status, ' -> ', result.content)
                sendResponse({ status: result.status, content: result.content })
            }).catch((error) => {
                console.error('background.js postBookmark Error: ', error)
                sendResponse({
                    status: 500,
                    content: { detail: error.message || 'Failed to create bookmark' }
                })
            })
            return true; // Keep the message channel open for async response
        }

        return false; // Let other handlers process other messages
    });


// Add this to ensure the side panel is set as the default
chrome.runtime.onInstalled.addListener(() => {
    // Set the side panel as default for all URLs
    chrome.sidePanel.setOptions({
        path: 'index.html?sidepanel=true',
        enabled: true
    });

    // Initialize bookmark local storage
    chrome.storage.local.clear(function () {
        var error = chrome.runtime.lastError;
        if (error) {
            console.error(error);
        }
    });

    // Get the current active tab and store its ID
    chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
        if (tabs && tabs[0]) {
            chrome.storage.session.set({ active_tab_id: tabs[0].id });
            console.log('Initial active tab ID stored:', tabs[0].id);
        }
    });
});

// Track side panel state
chrome.runtime.onConnect.addListener((port) => {
    if (port.name === 'sidepanel') {
        console.log('Side panel opened');
        isSidePanelOpen = true;

        // When side panel is opened, check bookmarks for current tab
        chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
            if (tabs && tabs[0]) {
                badgeToggle(tabs[0]);
            }
        });

        port.onDisconnect.addListener(() => {
            console.log('Side panel closed');
            isSidePanelOpen = false;
        });
    }
});

// Handle opening the side panel when the extension icon is clicked
chrome.action.onClicked.addListener((tab) => {
    chrome.sidePanel.open({ tabId: tab.id });
});

// Message handler for various actions
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    console.log('Background received message:', message);

    // Handle highlight-citation message
    if (message.name === 'highlight-citation') {
        (async () => {
            try {
                const { active_tab_id } = await chrome.storage.session.get(['active_tab_id']);
                let targetTabId = active_tab_id;

                if (!targetTabId) {
                    console.warn('No active tab ID found in storage, trying query...');
                    const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
                    if (tabs && tabs.length > 0) {
                        targetTabId = tabs[0].id;
                        await chrome.storage.session.set({ active_tab_id: targetTabId });
                    }
                }

                if (!targetTabId) {
                    sendResponse({ success: false, error: 'No active tab found' });
                    return;
                }

                await handleHighlighting(targetTabId, message.verbatim, sendResponse);
            } catch (error) {
                console.error('Error in highlight-citation handler:', error);
                sendResponse({ success: false, error: error.message || 'Unknown error' });
            }
        })();
        return true; // Keep channel open
    }
    return false;
});

// Helper function to handle the highlighting process
async function handleHighlighting(tabId, verbatim, sendResponse) {
    try {
        // First check if the tab exists
        const tab = await chrome.tabs.get(tabId);
        if (!tab) {
            console.error('Tab not found');
            sendResponse({
                success: false,
                error: 'Tab not found'
            });
            return;
        }

        console.log('Injecting content script into tab:', tabId);

        // Try to inject the content script
        try {
            await chrome.scripting.executeScript({
                target: { tabId: tabId },
                files: ['/js/content-scripts/highlighter.js']
            });
            console.log('Content script injected successfully');
        } catch (injectionError) {
            console.error('Error injecting content script:', injectionError);
            // Continue anyway, as the script might already be there
        }

        // Add a small delay to ensure the script is loaded
        await new Promise(resolve => setTimeout(resolve, 100));

        console.log('Sending highlight request to tab:', tabId, 'with verbatim:', verbatim);

        // Send the message to the content script with a timeout
        const messagePromise = new Promise((resolve) => {
            chrome.tabs.sendMessage(
                tabId,
                { action: 'highlight', verbatim: verbatim },
                (response) => {
                    const lastError = chrome.runtime.lastError;
                    if (lastError) {
                        console.error('Error sending message to content script:', lastError);
                        resolve({ success: false, error: lastError.message });
                    } else {
                        console.log('Highlight response:', response);
                        resolve(response || { success: false, error: 'No response from content script' });
                    }
                }
            );
        });

        // Add a timeout to handle cases where the content script doesn't respond
        const timeoutPromise = new Promise((resolve) => {
            setTimeout(() => {
                resolve({ success: false, error: 'Content script did not respond in time' });
            }, 2000);
        });

        // Wait for either the message response or the timeout
        const result = await Promise.race([messagePromise, timeoutPromise]);
        sendResponse(result);
    } catch (error) {
        console.error('Error in handleHighlighting:', error);
        sendResponse({
            success: false,
            error: error.message || 'Unknown error in highlighting process'
        });
    }
}


// Add this to handle extension lifecycle
chrome.runtime.onSuspend.addListener(() => {
    console.log('Extension is being suspended, cleaning up SSE');
    cleanupSSE();
});

chrome.runtime.onStartup.addListener(() => {
    console.log('Extension starting up, initializing SSE');
    registerSSEConnection();
});

// Add deleteBookmark function
const deleteBookmark = async (bookmarkId) => {
    try {

        const url = `${base_url}${Endpoints.delete_bookmark.replace('{id}', bookmarkId)}`;
        const response = await makeAuthenticatedRequest(url, {
            method: 'DELETE',
        });

        if (response.ok) {
            console.log('Bookmark deleted successfully');
            return { success: true };
        } else {
            let errorDetail;
            try {
                const errorJson = await response.json();
                errorDetail = (typeof errorJson.detail === 'string') ? errorJson.detail : JSON.stringify(errorJson.detail || errorJson);
            } catch (e) {
                errorDetail = await response.text().catch(() => 'Unknown error/Not JSON');
            }
            console.error('Error deleting bookmark:', errorDetail);
            return { success: false, error: errorDetail };
        }
    } catch (err) {
        const errMsg = err?.message || err?.toString() || 'Unknown error';
        console.error('Error deleting bookmark:', errMsg);
        return { success: false, error: errMsg };
    }
}

// Add fetchBookmarkDocument function
const fetchBookmarkDocument = async (bookmarkId) => {
    try {
        if (!bookmarkId || bookmarkId === 'undefined') {
            const msg = `Invalid bookmarkId: ${bookmarkId}. Cannot fetch document.`;
            console.error(msg);
            return { success: false, error: msg };
        }

        const url = `${base_url}${Endpoints.bookmark_by_id.replace('{ID}', bookmarkId)}`;
        console.log(`fetchBookmarkDocument -> bookmarkId: ${bookmarkId}, url: ${url}`);

        const response = await makeAuthenticatedRequest(url, {
            method: 'GET',
        });

        if (response.ok) {
            const bookmark = await response.json();
            console.log('Bookmark fetched successfully:', bookmark);

            // If bookmark has a document_id, fetch the document
            if (bookmark.document_id) {
                const docUrl = `${base_url}${Endpoints.document_by_id.replace('{ID}', bookmark.document_id)}`;
                const docResponse = await makeAuthenticatedRequest(docUrl, {
                    method: 'GET',
                });

                if (docResponse.ok) {
                    const document = await docResponse.json();
                    console.log('Document fetched successfully:', document);
                    return { success: true, bookmark, document };
                } else {
                    const docError = await docResponse.json().catch(() => ({ detail: 'Failed to fetch document' }));
                    console.error(`Error fetching document (${docResponse.status}):`, docError);
                    // Return bookmark even if document fetch failed
                    return { success: true, bookmark, document: null, docError: JSON.stringify(docError) };
                }
            }

            // Return bookmark even if no document
            return { success: true, bookmark, document: null };
        } else {
            let errorDetail;
            try {
                const errorJson = await response.json();
                errorDetail = (typeof errorJson.detail === 'string') ? errorJson.detail : JSON.stringify(errorJson.detail || errorJson);
            } catch (e) {
                errorDetail = await response.text().catch(() => 'Unknown error/Not JSON');
            }

            console.error(`Error fetching bookmark (${response.status}):`, errorDetail);

            // If bookmark not found on server, refresh local cache to stay in sync
            if (response.status === 404 || errorDetail === 'Bookmark not found') {
                console.log('Bookmark not found on server, triggering cache refresh');
                const store = await chrome.storage.session.get(["session_user"]);
                if (store.session_user && store.session_user.uid) {
                    refreshBookmarksCache(store.session_user.uid);
                }
            }

            return { success: false, error: errorDetail, status: response.status };
        }
    } catch (err) {
        const errMsg = err?.message || err?.toString() || 'Unknown error';
        console.error('Error in fetchBookmarkDocument:', errMsg);
        return { success: false, error: errMsg };
    }
}

// Add deleteDocument function
const deleteDocument = async (documentId) => {
    try {
        const url = `${base_url}${Endpoints.document_by_id.replace('{ID}', documentId)}`;
        const response = await makeAuthenticatedRequest(url, {
            method: 'DELETE',
        });

        if (response.ok || response.status === 204) {
            console.log('Document deleted successfully');
            return { success: true };
        } else {
            let errorDetail;
            try {
                const errorJson = await response.json();
                errorDetail = (typeof errorJson.detail === 'string') ? errorJson.detail : JSON.stringify(errorJson.detail || errorJson);
            } catch (e) {
                errorDetail = await response.text().catch(() => 'Unknown error/Not JSON');
            }
            console.error('Error deleting document:', errorDetail);
            return { success: false, error: errorDetail };
        }
    } catch (err) {
        const errMsg = err?.message || err?.toString() || 'Unknown error';
        console.error('Error deleting document:', errMsg);
        return { success: false, error: errMsg };
    }
}

// Add cancelProcessing function
const cancelProcessing = async (bookmarkId, documentId) => {
    console.log('Cancelling processing - bookmarkId:', bookmarkId, 'documentId:', documentId);

    // Close SSE connection if active and prevent reconnection
    if (eventSourceController) {
        console.log('Closing SSE connection...');
        eventSourceController.abort();
        eventSourceController = null;
    }

    // Clean up SSE and prevent reconnection attempts
    cleanupSSE();
    reconnectAttempts = maxReconnectAttempts; // Prevent automatic reconnection
    isConnecting = false;

    const results = {
        bookmarkDeleted: false,
        documentDeleted: false,
        errors: []
    };

    // Delete document if it exists
    if (documentId) {
        console.log('Deleting document:', documentId);
        const docResult = await deleteDocument(documentId);
        if (docResult.success) {
            results.documentDeleted = true;
            console.log('Document deleted successfully');
        } else {
            results.errors.push(`Document deletion failed: ${docResult.error?.detail || docResult.error}`);
            console.error('Failed to delete document:', docResult.error);
        }
    }

    // Delete bookmark if it exists
    if (bookmarkId) {
        console.log('Deleting bookmark:', bookmarkId);
        const bookmarkResult = await deleteBookmark(bookmarkId);
        if (bookmarkResult.success) {
            results.bookmarkDeleted = true;
            console.log('Bookmark deleted successfully');
        } else {
            results.errors.push(`Bookmark deletion failed: ${bookmarkResult.error?.detail || bookmarkResult.error}`);
            console.error('Failed to delete bookmark:', bookmarkResult.error);
        }
    }

    // Return success if at least one deletion succeeded or if nothing needed to be deleted
    const success = results.bookmarkDeleted || results.documentDeleted || (!bookmarkId && !documentId);

    return {
        success,
        ...results
    };
}

// Add message handler for delete bookmark
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    if (request.name === 'delete-bookmark') {
        console.log('Deleting bookmark:', request.bookmarkId);
        deleteBookmark(request.bookmarkId).then((result) => {
            sendResponse(result);
        });
        return true;
    }
    else if (request.name === 'cancel-processing') {
        console.log('Cancelling processing:', request);
        cancelProcessing(request.bookmarkId, request.documentId).then((result) => {
            sendResponse(result);
        });
        return true;
    }
    else if (request.name === 'update-badge') {
        console.log('Updating badge for tab:', request.tabId, 'hasBookmark:', request.hasBookmark);
        if (request.hasBookmark) {
            badgeOn(request.tabId);
        } else {
            badgeOff(request.tabId);
        }
        return true;
    }
    else if (request.name === 'fetch-bookmark-document') {
        console.log('Fetching document for bookmark:', request.bookmarkId);
        fetchBookmarkDocument(request.bookmarkId).then((result) => {
            sendResponse(result);
        }).catch((error) => {
            const errMsg = error?.message || error?.toString() || 'Unknown error';
            console.error('Error in fetch-bookmark-document handler:', errMsg);
            sendResponse({ success: false, error: errMsg });
        });
        return true;
    }
    // ... rest of existing message handlers ...
});

// Enhance the existing commands listener or add it if not present
chrome.commands.onCommand.addListener((command) => {
    console.log('Command received:', command);

    // Log the command first
    logCommand(command);

    // Then handle specific commands as before
    if (command === 'toggle-side-panel') {
        // ... existing code ...
    }
    else if (command === 'focus-input') {
        console.log('Focus input command received');
        let needsToOpenPanel = false;

        // First check if the panel is already open
        try {
            // Try to send a message to check if panel is open
            chrome.runtime.sendMessage({
                name: 'panel-status-check'
            }).then(response => {
                console.log('Panel is already open, focusing directly');
                sendFocusMessage();
            }).catch(error => {
                console.log('Panel not open yet, opening first: ', error);
                openPanelThenFocus();
            });
        } catch (error) {
            console.log('Error checking panel status, assuming not open: ', error);
            openPanelThenFocus();
        }
    }
    // ... any other command handlers ...
});

// Helper function to send the focus message with "fresh-open" context
function sendFocusMessage() {
    chrome.runtime.sendMessage({
        name: 'focus-input',
        data: {
            action: 'focus-input',
            context: 'auto',
            freshOpen: false  // Panel was already open
        }
    }).catch(err => {
        console.log('Error sending focus message: ', err);
    });
}

// Helper function to open the panel then focus
function openPanelThenFocus() {
    chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
        if (chrome.runtime.lastError) {
            console.error('Error querying tabs:', chrome.runtime.lastError.message);
            return;
        }

        if (tabs && tabs[0] && tabs[0].id) {
            console.log('Opening side panel first');

            // Open the side panel with a parameter indicating it was opened via shortcut
            chrome.sidePanel.open({
                tabId: tabs[0].id,
                // Add a parameter to indicate this was opened via keyboard shortcut
                path: 'index.html?from_shortcut=true&sidepanel=true'
            }).then(() => {
                console.log('Side panel opened with from_shortcut param, waiting before focusing');

                // Use a longer delay to ensure panel is fully rendered
                setTimeout(() => {
                    chrome.runtime.sendMessage({
                        name: 'focus-input',
                        data: {
                            action: 'focus-input',
                            context: 'auto',
                            freshOpen: true  // Panel was just opened
                        }
                    }).catch(err => {
                        console.log('Error sending focus message after panel open: ', err);

                        // Try once more with an even longer delay
                        setTimeout(() => {
                            chrome.runtime.sendMessage({
                                name: 'focus-input',
                                data: {
                                    action: 'focus-input',
                                    context: 'auto',
                                    freshOpen: true,
                                    finalAttempt: true
                                }
                            }).catch(finalErr => {
                                console.log('Final focus attempt failed: ', finalErr);
                            });
                        }, 1000);
                    });
                }, 800); // Increased from 500ms to 800ms for better reliability
            }).catch(err => {
                console.log('Error opening side panel: ', err);
            });
        }
    });
}

// Add a function to get all available commands with their shortcuts
function getAllCommands() {
    chrome.commands.getAll(commands => {
        console.log('All registered commands:', commands);

        // Format and log each command
        commands.forEach(cmd => {
            console.log(`Command: ${cmd.name}, Shortcut: ${cmd.shortcut || 'none'}, Description: ${cmd.description}`);
        });
    });
}

// Call this when the background script starts
getAllCommands();

// Add message handler for fetching recent shortcuts
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    // ... existing message handlers ...

    // Add handler for fetching recent shortcuts
    if (message.name === 'get-recent-shortcuts') {
        sendResponse({ shortcuts: recentShortcuts });
        return true;
    }

    // Add handler for clearing shortcuts
    if (message.name === 'clear-shortcuts') {
        console.log('Clearing shortcuts history');
        recentShortcuts = [];
        sendResponse({ success: true });
        return true;
    }

    // Add handler for updating environment
    if (message.name === 'update-environment') {
        console.log('Updating environment to:', message.environment);
        const newUrl = message.environment === 'development'
            ? 'http://localhost:8000'
            : 'https://stg.api.icognition.ai';
        base_url = newUrl;
        console.log('Base URL updated to:', base_url);

        // Reconnect SSE with new URL
        if (eventSourceController) {
            eventSourceController.abort();
            eventSourceController = null;
        }
        registerSSEConnection();

        sendResponse({ success: true, baseUrl: base_url });
        return true;
    }

    // ... rest of existing message handlers ...
});