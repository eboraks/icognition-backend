import { defineStore } from 'pinia';
import { ref, watch } from 'vue';
import { chatService } from '@/services/chatService';
import { useAuthStore } from './auth_store';

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

    const message = {
        _id: Date.now().toString(),
        content: messageContent,
        senderId: authStore.currentUser.uid,
        timestamp: new Date().toLocaleTimeString(),
        date: new Date().toLocaleDateString(),
    };
    messages.value.push(message);

    // Now send the message
    if (socket && socket.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify({ content: messageContent }));
    } else {
      console.error('WebSocket still not connected after reconnection attempt');
    }

    // Rename chat on first user message
    if (isFirstMessage && activeSession.value) {
      const newTitle = (messageContent || '').trim().slice(0, 60);
      if (newTitle) {
        try {
          await chatService.updateSessionTitle(activeSession.value.id, newTitle);
          const session = sessions.value.find(s => s.id === activeSession.value!.id);
          if (session) session.title = newTitle;
        } catch (e) {
          console.warn('Failed to update session title', e);
        }
      }
    }
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
          const agentMessage = {
              _id: Date.now().toString(),
              content: event.data,
              senderId: 'agent',
              timestamp: new Date().toLocaleTimeString(),
              date: new Date().toLocaleDateString(),
          };
          
          // This is a simple implementation. A more robust solution would handle streaming chunks.
          const lastMessage = messages.value[messages.value.length - 1];
          if (lastMessage && lastMessage.senderId === 'agent') {
              lastMessage.content += event.data;
          } else {
              messages.value.push(agentMessage);
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
        socket = null;
      };
    });
  }
  
  function disconnectWebSocket() {
    if (socket) {
      socket.close();
    }
  }

  watch(activeSession, async (newSession, oldSession) => {
    if (oldSession) {
      disconnectWebSocket();
    }
    if (newSession) {
      await loadMessages(newSession.id);
      try {
        await connectWebSocket();
      } catch (error) {
        console.error('Failed to connect WebSocket on session change:', error);
      }
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
  };
});
