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
  // Add other session properties as needed
}

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

  async function createSession(title: string, scopeType: string = 'all_library', scopeId: number | null = null) {
    if (!authStore.currentUser) return;
    isLoading.value = true;
    error.value = null;
    try {
      const response = await chatService.createSession(title, scopeType, scopeId);
      sessions.value.push(response.data);
      activeSession.value = response.data;
    } catch (err: any) {
      error.value = err.message || 'Failed to create session';
    } finally {
      isLoading.value = false;
    }
  }

  async function loadMessages(sessionId: number) {
    isLoading.value = true;
    error.value = null;
    try {
      const response = await chatService.getSessionMessages(sessionId);
      messages.value = response.data.map((msg: any) => ({
        _id: msg.id,
        content: msg.content,
        senderId: msg.role === 'user' ? authStore.currentUser?.uid : 'agent',
        timestamp: new Date(msg.created_at).toLocaleTimeString(),
        date: new Date(msg.created_at).toLocaleDateString(),
      }));
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
        messages.value = [];
        disconnectWebSocket();
      }
    } catch (err: any) {
      error.value = err.message || 'Failed to delete session';
    } finally {
      isLoading.value = false;
    }
  }

  function addMessage(message: ChatMessage) {
    messages.value.push(message);
  }

  async function sendMessage(messageContent: string) {
    if (!activeSession.value || !authStore.currentUser) {
      console.error('No active session or user not authenticated.');
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

    const isFirstMessage = messages.value.length === 0;

    const now = new Date();
    const message = {
        _id: Date.now().toString(),
        content: messageContent,
        senderId: authStore.currentUser.uid,
        timestamp: now.toLocaleTimeString(),
        date: now.toLocaleDateString(),
    };
    messages.value.push(message);

    // Reset streaming state so the next agent response starts a fresh message
    streamingMessageId = null;

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
          const chunk = typeof event.data === 'string' ? event.data : String(event.data);
          if (!chunk) {
            return;
          }

          const now = new Date();

          if (!streamingMessageId) {
            streamingMessageId = `agent-${Date.now()}`;
            messages.value.push({
              _id: streamingMessageId,
              content: chunk,
              senderId: 'agent',
              timestamp: now.toLocaleTimeString(),
              date: now.toLocaleDateString(),
            });
            return;
          }

          const activeMessage = messages.value.find(msg => msg._id === streamingMessageId);

          if (activeMessage) {
            if (chunk.startsWith(activeMessage.content)) {
              activeMessage.content = chunk;
            } else {
              activeMessage.content += chunk;
            }
            activeMessage.timestamp = now.toLocaleTimeString();
            activeMessage.date = now.toLocaleDateString();
          } else {
            // Fallback: create a new message if we lost track of the streaming one
            streamingMessageId = `agent-${Date.now()}`;
            messages.value.push({
              _id: streamingMessageId,
              content: chunk,
              senderId: 'agent',
              timestamp: now.toLocaleTimeString(),
              date: now.toLocaleDateString(),
            });
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
      messages.value = [];
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
    messages,
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
