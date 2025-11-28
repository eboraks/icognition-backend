import { defineStore } from 'pinia';
import { ref, watch } from 'vue';
import { chatService } from '@/services/chatService.js';
import { useAuthStore } from './auth_store.js';

// Define the shape of a message and a session to match vue-advanced-chat
export interface ChatMessage {
  _id: string;
  content: string;
  senderId: string;
  timestamp: string;
  date: string;
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
  let socket: WebSocket | null = null;
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
        disconnectWebSocket();
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

    // Check if WebSocket is disconnected or not open, reconnect if needed
    if (!socket || socket.readyState !== WebSocket.OPEN) {
      console.log('WebSocket not connected, reconnecting...');
      try {
        await connectWebSocket();
        console.log('WebSocket reconnected successfully');
      } catch (error) {
        console.error('Failed to reconnect WebSocket:', error);
        throw error; // Re-throw so caller knows connection failed
      }
    }

    // const isFirstMessage = messages.value.length === 0; // No longer relevant for global messages

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

    // Now send the message
    if (socket && socket.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify({ content: messageContent }));
    } else {
      console.error('WebSocket still not connected after reconnection attempt');
    }

    // Backend now handles renaming the chat on the first user message.
    // if (isFirstMessage && activeSession.value) {
    //   const newTitle = (messageContent || '').trim().slice(0, 60);
    //   if (newTitle) {
    //     try {
    //       await chatService.updateSessionTitle(activeSession.value.id, newTitle);
    //       const session = sessions.value.find(s => s.id === activeSession.value!.id);
    //       if (session) session.title = newTitle;
    //     } catch (e) {
    //       console.warn('Failed to update session title', e);
    //     }
    //   }
    // }
  }

  function connectWebSocket(): Promise<void> {
    return new Promise((resolve, reject) => {
      if (!activeSession.value || !authStore.currentUser) {
        reject(new Error('No active session or user'));
        return;
      }
      
      // Close existing socket if any
      if (socket) {
        socket.close();
        socket = null;
      }
      
      const apiBase = import.meta.env.VITE_APP_API_BASE_URL as string;
      const wsBase = apiBase.replace(/^http/, 'ws');
      const wsUrl = `${wsBase}/api/v1/chat/ws/${activeSession.value.id}/${authStore.currentUser.uid}`;
      socket = new WebSocket(wsUrl);

      const timeout = setTimeout(() => {
        if (socket) {
          socket.close();
          socket = null;
        }
        reject(new Error('WebSocket connection timeout'));
      }, 5000); // 5 second timeout

      socket.onopen = () => {
        clearTimeout(timeout);
        console.log('WebSocket connected');
        resolve();
      };

      socket.onmessage = (event) => {
          const rawData = typeof event.data === 'string' ? event.data : String(event.data);
          if (!rawData) {
            return;
          }

          let messageData: { type: string; content?: string; message_id?: string };
          try {
            messageData = JSON.parse(rawData);
          } catch (e) {
            console.error('Failed to parse WebSocket message:', rawData, e);
            return; // Skip if message is not valid JSON
          }

          const { type, content, message_id } = messageData;
          const now = new Date();

          if (type === "stream_chunk") {
            if (!activeSession.value) return;

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

            streamingBuffer += content || '';
            activeMessage.pending = true;
            activeMessage.timestamp = now.toLocaleTimeString();
            activeMessage.date = now.toLocaleDateString();
          } else if (type === "end_stream") {
            const finalContent = (content && content.length > 0) ? content : streamingBuffer;
            if (activeSession.value && streamingMessageId) {
              const activeMessage = activeSession.value.messages.find(msg => msg._id === streamingMessageId);
              if (activeMessage) {
                activeMessage.content = finalContent || '';
                activeMessage.pending = false;
                activeMessage.timestamp = now.toLocaleTimeString();
                activeMessage.date = now.toLocaleDateString();
              }
            }
            streamingMessageId = null; // Reset for the next message
            streamingBuffer = '';
          } else if (type === "error") {
            console.error('Backend WebSocket error:', content);
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
      };

      socket.onerror = (error) => {
        clearTimeout(timeout);
        console.error('WebSocket error:', error);
        reject(error);
      };

      socket.onclose = (event) => {
        clearTimeout(timeout);
        console.log('WebSocket disconnected', event.code, event.reason);
        streamingMessageId = null;
        socket = null;
      };
    });
  }
  
  function disconnectWebSocket() {
    if (socket) {
      socket.close();
    }
    streamingMessageId = null;
  }

  async function switchActiveSession(sessionId: number) {
    console.log(`Attempting to switch to session ${sessionId}`);
    if (activeSession.value?.id === sessionId) {
      console.log(`Already on session ${sessionId}. No switch needed.`);
      return;
    }

    disconnectWebSocket();
    
    const newSession = sessions.value.find(s => s.id === sessionId);
    if (newSession) {
      activeSession.value = newSession;
      try {
        console.log(`Loading messages for session ${sessionId}`);
        await loadMessages(sessionId);
        console.log(`Connecting WebSocket for session ${sessionId}`);
        await connectWebSocket();
      } catch (error) {
        console.error(`Failed to switch to session ${sessionId}:`, error);
      }
    } else {
      console.warn(`Session ${sessionId} not found.`);
      activeSession.value = null;
      // messages.value = []; // Messages are now session-specific
    }
  }

  watch(activeSession, (newSession, oldSession) => {
    // This watcher is now only for cleanup when all sessions are gone.
    // The explicit switchActiveSession handles the main logic.
    if (!newSession && oldSession) {
      disconnectWebSocket();
    }
  });


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
  };
});
