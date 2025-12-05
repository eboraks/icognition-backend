import axios from 'axios';
import { getAuth } from 'firebase/auth';

const apiBaseUrl: string = import.meta.env.VITE_APP_API_BASE_URL || '';

const apiClient = axios.create({
  baseURL: apiBaseUrl,
  headers: {
    'Content-Type': 'application/json',
  },
});

apiClient.interceptors.request.use(async (config) => {
  const auth = getAuth();
  const user = auth.currentUser;
  if (user) {
    const token = await user.getIdToken();
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
}, (error) => {
  return Promise.reject(error);
});

export const chatService = {
  // === Session Management ===
  createSession(title: string, scopeType: string, scopeId: number | null) {
    return apiClient.post('/api/v1/chat/sessions', { title, scope_type: scopeType, scope_id: scopeId });
  },

  getSessions() {
    return apiClient.get('/api/v1/chat/sessions');
  },

  deleteSession(sessionId: number) {
    return apiClient.delete(`/api/v1/chat/sessions/${sessionId}`);
  },

  updateSessionScope(sessionId: number, scopeType: string, scopeId: number | null) {
    return apiClient.put(`/api/v1/chat/sessions/${sessionId}/scope`, { scope_type: scopeType, scope_id: scopeId });
  },

  updateSessionTitle(sessionId: number, title: string) {
    return apiClient.put(`/api/v1/chat/sessions/${sessionId}/title`, { title });
  },

  // === Message Management ===
  getSessionMessages(sessionId: number) {
    return apiClient.get(`/api/v1/chat/sessions/${sessionId}/messages`);
  },

  sendMessage(sessionId: number, content: string) {
    return apiClient.post(`/api/v1/chat/sessions/${sessionId}/messages`, { content });
  },
};
