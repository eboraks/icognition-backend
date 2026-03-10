<template>
  <div class="chat-layout flex h-full">
    <!-- Session sidebar -->
    <div class="session-sidebar flex flex-column" style="width: 260px; min-width: 200px; border-right: 1px solid #e2e8f0;">
      <ChatSessionList
        :sessions="chatStore.sessions"
        :active-session-id="chatStore.activeSession?.id ?? null"
        @select="handleSelectSession"
        @delete="handleDeleteSession"
        @create="handleCreateSession"
      />
    </div>

    <!-- Chat area -->
    <div class="flex-1 flex flex-column overflow-hidden">
      <ChatPanel
        v-if="chatStore.activeSession"
        :key="chatStore.activeSession.id"
        :chat-session-id="chatStore.activeSession.id"
      />
      <div v-else class="flex-1 flex align-items-center justify-content-center">
        <div class="text-center" style="color: #64748b;">
          <i class="pi pi-comments text-4xl mb-3 block"></i>
          <p class="text-lg mb-3" style="color: #334155;">No conversation selected</p>
          <Button label="Start a new chat" icon="pi pi-plus" @click="handleCreateSession" />
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import Button from 'primevue/button';
import { useChatStore } from '@/stores/chat_store.js';
import { useAuthStore } from '@/stores/auth_store.js';
import ChatSessionList from '@/components/chat/ChatSessionList.vue';
import ChatPanel from '@/components/knowledge_explorer/ChatPanel.vue';

const route = useRoute();
const router = useRouter();
const chatStore = useChatStore();
const authStore = useAuthStore();

onMounted(async () => {
  if (!authStore.currentUser) return;
  await chatStore.loadSessions();

  const idParam = Number(route.params.id);
  if (!isNaN(idParam) && idParam > 0) {
    // URL specifies a session ID → switch to it
    await chatStore.switchActiveSession(idParam);
  } else if (chatStore.sessions.length > 0 && chatStore.sessions[0]) {
    // No ID in URL → auto-select the most recent session and update URL
    const firstId = chatStore.sessions[0].id;
    await chatStore.switchActiveSession(firstId);
    router.replace({ name: 'chats', params: { id: firstId } });
  }
});

// Sync when user navigates directly to /chats/:id
watch(() => route.params.id, async (newId) => {
  const id = Number(newId);
  if (!isNaN(id) && id > 0 && chatStore.activeSession?.id !== id) {
    await chatStore.switchActiveSession(id);
  }
});

async function handleSelectSession(sessionId: number) {
  await chatStore.switchActiveSession(sessionId);
  router.push({ name: 'chats', params: { id: sessionId } });
}

async function handleDeleteSession(sessionId: number) {
  await chatStore.deleteSession(sessionId);
  if (!chatStore.activeSession && chatStore.sessions.length > 0 && chatStore.sessions[0]) {
    const firstId = chatStore.sessions[0].id;
    await chatStore.switchActiveSession(firstId);
    router.replace({ name: 'chats', params: { id: firstId } });
  } else if (chatStore.activeSession) {
    router.replace({ name: 'chats', params: { id: chatStore.activeSession.id } });
  } else {
    router.replace({ name: 'chats' });
  }
}

async function handleCreateSession() {
  const newSession = await chatStore.createSession('New Chat');
  if (newSession) {
    router.push({ name: 'chats', params: { id: newSession.id } });
  }
}
</script>

<style scoped>
.chat-layout {
  height: calc(100vh - 70px);
}
</style>
