import { defineStore } from 'pinia';
import { ref, watch } from 'vue';
import { getAuth } from 'firebase/auth';
import { chatService } from '@/services/chatService.js';
import { useAuthStore } from './auth_store.js';

// Define the shape of a message and a session to match vue-advanced-chat
export interface ChatMessage {
  _id: string;
  content: string;
  senderId: string;
  timestamp: string;
  date: string;
  pending?: boolean;
  statusText?: string;
}

export interface ChatSession {
  id: number;
  title: string;
  scope_type?: string;
  scope_id?: number | null;
  // Add other session properties as needed
  messages: ChatMessage[]; // Added for direct message storage
}

const escapeHtml = (unsafe: string) =>
  unsafe
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');

const toParagraphHtml = (content: string) => `<p>${escapeHtml(content)}</p>`;

export const useChatStore = defineStore('chat', () => {
  // State
  const sessions = ref<ChatSession[]>([]);
  const activeSession = ref<ChatSession | null>(null);
  const messages = ref<ChatMessage[]>([]);
  const isLoading = ref(false);
  const error = ref<string | null>(null);
  const authStore = useAuthStore();
  let eventSource: EventSource | null = null;
  let streamingMessageId: string | null = null;
  let streamingBuffer = "";

  // Actions
  async function loadSessions() {
    if (!authStore.currentUser) return;
    isLoading.value = true;
    error.value = null;
    try {
      const response = await chatService.getSessions();
      sessions.value = response.data;
    } catch (err: any) {
      error.value = err.message || 'Failed to load sessions';
    } finally {
      isLoading.value = false;
    }
  }

  async function createSession(title: string, scopeType: string = 'all_library', scopeId: number | null = null): Promise<ChatSession | null> {
    if (!authStore.currentUser) return null;
    isLoading.value = true;
    error.value = null;
    try {
      const response = await chatService.createSession(title, scopeType, scopeId);
      const newSession = { ...response.data, messages: [] }; // Initialize messages array
      sessions.value.push(newSession);
      activeSession.value = newSession;
      return newSession;
    } catch (err: any) {
      error.value = err.message || 'Failed to create session';
      return null;
    } finally {
      isLoading.value = false;
    }
  }

  async function loadMessages(sessionId: number) {
    isLoading.value = true;
    error.value = null;
    try {
      const response = await chatService.getSessionMessages(sessionId);
      const session = sessions.value.find(s => s.id === sessionId);
      if (session) {
        session.messages = response.data.map((msg: any) => ({
          _id: msg.id,
          content: msg.content,
          senderId: msg.role === 'user' ? authStore.currentUser?.uid : 'agent',
          timestamp: new Date(msg.created_at).toLocaleTimeString(),
          date: new Date(msg.created_at).toLocaleDateString(),
        }));
      } else {
        console.warn(`Attempted to load messages for non-existent session ${sessionId}`);
      }
      streamingMessageId = null;
    } catch (err: any) {
      error.value = err.message || 'Failed to load messages';
    } finally {
      isLoading.value = false;
    }
  }

  async function deleteSession(sessionId: number) {
    if (!authStore.currentUser) return;
    isLoading.value = true;
    error.value = null;
    try {
      await chatService.deleteSession(sessionId);
      sessions.value = sessions.value.filter(s => s.id !== sessionId);
      if (activeSession.value?.id === sessionId) {
        activeSession.value = null;
        // messages.value = []; // Messages are now session-specific
        disconnectSSE();
      }
    } catch (err: any) {
      error.value = err.message || 'Failed to delete session';
    } finally {
      isLoading.value = false;
    }
  }

  function addMessage(message: ChatMessage) {
    if (activeSession.value) {
      activeSession.value.messages.push(message);
    } else {
      console.warn('Attempted to add message without an active session.');
    }
  }

  async function sendMessage(messageContent: string, sessionId?: number) {
    if (!authStore.currentUser) {
      console.error('No active user.');
      return;
    }

    // If a sessionId is provided, ensure we are on that active session
    if (sessionId && activeSession.value?.id !== sessionId) {
      await switchActiveSession(sessionId);
    }

    if (!activeSession.value) {
      console.error('No active session after attempt to switch.');
      return;
    }

    const now = new Date();
    const formattedContent = toParagraphHtml(messageContent);
    const message: ChatMessage = {
      _id: Date.now().toString(),
      content: formattedContent,
      senderId: authStore.currentUser.uid,
      timestamp: now.toLocaleTimeString(),
      date: now.toLocaleDateString(),
    };
    activeSession.value.messages.push(message);

    const placeholderId = `assistant-${Date.now()}`;
    const placeholderMessage: ChatMessage = {
      _id: placeholderId,
      content: '',
      senderId: 'agent',
      timestamp: now.toLocaleTimeString(),
      date: now.toLocaleDateString(),
      pending: true,
    };
    activeSession.value.messages.push(placeholderMessage);
    streamingMessageId = placeholderId;
    streamingBuffer = '';

    try {
      // Send message via REST API
      const savedMessage = await chatService.sendMessage(activeSession.value.id, messageContent);

      // Debug: Log the response structure
      console.log('Saved message response:', savedMessage);
      console.log('Saved message data:', savedMessage.data);
      console.log('Message ID:', savedMessage.data?.id);

      // Extract message ID - handle different possible response structures
      const messageId = savedMessage.data?.id || (savedMessage.data as any)?.data?.id;

      if (!messageId) {
        console.error('Message ID is missing from response. Full response:', savedMessage);
        console.error('Response data:', savedMessage.data);
        throw new Error('Failed to get message ID from server response');
      }

      // Start SSE stream for AI response
      await streamChatResponse(activeSession.value.id, messageId);
    } catch (error) {
      console.error('Failed to send message:', error);
      // Update placeholder with error
      if (activeSession.value) {
        const placeholder = activeSession.value.messages.find(msg => msg._id === placeholderId);
        if (placeholder) {
          placeholder.content = 'Failed to send message. Please try again.';
          placeholder.pending = false;
          placeholder.senderId = 'system';
        }
      }
      streamingMessageId = null;
      streamingBuffer = '';
    }
  }

  async function streamChatResponse(sessionId: number, messageId: number) {
    const startTime = Date.now();
    const log = (msg: string) => console.log(`[${new Date().toISOString()}] [Chat SSE] ${msg}`);

    log(`Starting SSE stream for session ${sessionId}, message ${messageId}`);

    // Close existing EventSource if any
    if (eventSource) {
      eventSource.close();
      eventSource = null;
    }

    return new Promise<void>(async (resolve, reject) => {
      if (!activeSession.value || !authStore.currentUser) {
        log('ERROR: No active session or user');
        reject(new Error('No active session or user'));
        return;
      }

      const apiBase = import.meta.env.VITE_APP_API_BASE_URL as string;
      log(`API Base URL: ${apiBase}`);

      // Get Firebase ID token
      const auth = getAuth();
      const user = auth.currentUser;
      if (!user) {
        log('ERROR: No authenticated Firebase user');
        reject(new Error('No authenticated user'));
        return;
      }

      let token: string;
      try {
        log('Getting Firebase ID token...');
        token = await user.getIdToken();
        log('Firebase ID token obtained successfully');
      } catch (error) {
        log(`ERROR: Failed to get Firebase token: ${error}`);
        reject(new Error('Failed to get authentication token'));
        return;
      }

      // Create SSE connection with authentication
      const streamUrl = `${apiBase}/api/v1/chat/sessions/${sessionId}/stream?message_id=${messageId}`;
      log(`Fetching SSE stream from: ${streamUrl}`);

      // Use fetch with ReadableStream for SSE (EventSource doesn't support custom headers)
      fetch(streamUrl, {
        method: 'GET',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Accept': 'text/event-stream',
        },
      }).then(response => {
        log(`SSE response received, status: ${response.status}, ok: ${response.ok}`);
        if (!response.ok) {
          log(`ERROR: SSE response not ok, status: ${response.status}`);
          throw new Error(`HTTP error! status: ${response.status}`);
        }

        const reader = response.body?.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        let chunkNumber = 0;

        if (!reader) {
          log('ERROR: Response body is not readable');
          throw new Error('Response body is not readable');
        }

        log('SSE reader obtained, starting to process chunks...');

        function processChunk(): Promise<void> {
          return reader!.read().then(({ done, value }) => {
            if (done) {
              const duration = Date.now() - startTime;
              log(`SSE stream completed in ${duration}ms, total chunks processed: ${chunkNumber}`);
              resolve();
              return;
            }

            chunkNumber++;
            const bytesReceived = value?.length || 0;
            log(`SSE chunk #${chunkNumber} received: ${bytesReceived} bytes`);

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop() || ''; // Keep incomplete line in buffer

            for (const line of lines) {
              if (line.startsWith('event: ')) {
                const eventType = line.substring(7).trim();
                log(`SSE event type: ${eventType}`);
                continue;
              }

              if (line.startsWith('data: ')) {
                const data = line.substring(6).trim();
                log(`SSE data received (${data.length} chars): ${data.substring(0, 100)}...`);
                try {
                  const messageData = JSON.parse(data);
                  log(`Parsed SSE message: type=${messageData.type}, content_length=${messageData.content?.length || 0}`);
                  handleSSEMessage(messageData);
                } catch (e) {
                  console.error(`[${new Date().toISOString()}] [Chat SSE] ERROR: Failed to parse SSE data:`, data, e);
                }
              }
            }

            return processChunk();
          });
        }

        processChunk().catch(err => {
          log(`ERROR in SSE processChunk: ${err.message}`);
          reject(err);
        });
      }).catch(err => {
        log(`ERROR in SSE fetch: ${err.message}`);
        reject(err);
      });
    });
  }

  function handleSSEMessage(messageData: { type: string; content?: string; message_id?: string }) {
    const log = (msg: string) => console.log(`[${new Date().toISOString()}] [SSE Handler] ${msg}`);
    const { type, content, message_id } = messageData;
    const now = new Date();

    log(`Handling message type: ${type}, content_length: ${content?.length || 0}, message_id: ${message_id}`);

    if (type === "stream_chunk") {
      if (!activeSession.value) {
        log('WARNING: No active session, cannot handle stream_chunk');
        return;
      }
      log('Processing stream_chunk...');

      if (!streamingMessageId) {
        streamingMessageId = message_id || `agent-${Date.now()}`;
        activeSession.value.messages.push({
          _id: streamingMessageId,
          content: '',
          senderId: 'agent',
          timestamp: now.toLocaleTimeString(),
          date: now.toLocaleDateString(),
          pending: true,
        });
      }

      if (message_id && streamingMessageId !== message_id) {
        const placeholder = activeSession.value.messages.find(msg => msg._id === streamingMessageId);
        if (placeholder) {
          placeholder._id = message_id;
        }
        streamingMessageId = message_id;
      }

      let activeMessage = activeSession.value.messages.find(msg => msg._id === streamingMessageId);
      if (!activeMessage) {
        activeMessage = {
          _id: streamingMessageId!,
          content: '',
          senderId: 'agent',
          timestamp: now.toLocaleTimeString(),
          date: now.toLocaleDateString(),
          pending: true,
        };
        activeSession.value.messages.push(activeMessage);
      }

      if (activeMessage) {
        streamingBuffer = content || '';
        activeMessage.content = streamingBuffer;
        activeMessage.pending = true;
        activeMessage.timestamp = now.toLocaleTimeString();
        activeMessage.date = now.toLocaleDateString();
        log(`stream_chunk processed: ${streamingBuffer.length} chars total`);
      }
    } else if (type === "end_stream") {
      log('Processing end_stream...');
      const finalContent = (content && content.length > 0) ? content : streamingBuffer;
      if (activeSession.value && streamingMessageId) {
        log(`Finalizing message: ${finalContent.length} chars`);
        const activeMessage = activeSession.value.messages.find(msg => msg._id === streamingMessageId);
        if (activeMessage) {
          activeMessage.content = finalContent || '';
          activeMessage.pending = false;
          activeMessage.timestamp = now.toLocaleTimeString();
          activeMessage.date = now.toLocaleDateString();
        }
      }
      streamingMessageId = null;
      streamingBuffer = '';
      log('end_stream processed successfully');
    } else if (type === "agent_status") {
      log(`STATUS event received: ${content}`);
      if (activeSession.value && streamingMessageId) {
        const activeMessage = activeSession.value.messages.find(msg => msg._id === streamingMessageId);
        if (activeMessage) {
          activeMessage.statusText = content;
        }
      }
    } else if (type === "error") {
      log(`ERROR event received: ${content}`);
      console.error(`[${new Date().toISOString()}] [SSE Handler] Backend SSE error:`, content);
      if (activeSession.value) {
        if (streamingMessageId) {
          const pendingMessage = activeSession.value.messages.find(msg => msg._id === streamingMessageId);
          if (pendingMessage) {
            pendingMessage.content = content || 'An unknown error occurred.';
            pendingMessage.pending = false;
            pendingMessage.senderId = 'system';
            pendingMessage.timestamp = now.toLocaleTimeString();
            pendingMessage.date = now.toLocaleDateString();
          }
        } else {
          activeSession.value.messages.push({
            _id: `error-${Date.now()}`,
            content: content || 'An unknown error occurred.',
            senderId: 'system',
            timestamp: now.toLocaleTimeString(),
            date: now.toLocaleDateString(),
          });
        }
      }
      streamingMessageId = null;
      streamingBuffer = '';
    }
  }

  function disconnectSSE() {
    if (eventSource) {
      eventSource.close();
      eventSource = null;
    }
    streamingMessageId = null;
  }

  async function switchActiveSession(sessionId: number) {
    console.log(`Attempting to switch to session ${sessionId}`);
    if (activeSession.value?.id === sessionId) {
      console.log(`Already on session ${sessionId}. No switch needed.`);
      return;
    }

    disconnectSSE();

    const newSession = sessions.value.find(s => s.id === sessionId);
    if (newSession) {
      activeSession.value = newSession;
      try {
        console.log(`Loading messages for session ${sessionId}`);
        await loadMessages(sessionId);
        // No need to connect SSE here - it's done per message
      } catch (error) {
        console.error(`Failed to switch to session ${sessionId}:`, error);
      }
    } else {
      console.warn(`Session ${sessionId} not found.`);
      activeSession.value = null;
    }
  }

  watch(activeSession, (newSession, oldSession) => {
    // Cleanup when session changes
    if (!newSession && oldSession) {
      disconnectSSE();
    }
  });


  async function updateSessionScope(sessionId: number, scopeType: string, scopeId: number | null) {
    try {
      const response = await chatService.updateSessionScope(sessionId, scopeType, scopeId);
      const session = sessions.value.find(s => s.id === sessionId);
      if (session) {
        session.scope_type = response.data.scope_type;
        session.scope_id = response.data.scope_id;
      }
      return response.data;
    } catch (err: any) {
      error.value = err.message || 'Failed to update session scope';
      return null;
    }
  }

  return {
    sessions,
    activeSession,
    // messages, // No longer needed as messages are session-specific
    isLoading,
    error,
    loadSessions,
    createSession,
    loadMessages,
    addMessage,
    sendMessage,
    deleteSession,
    switchActiveSession,
    updateSessionScope,
  };
});
