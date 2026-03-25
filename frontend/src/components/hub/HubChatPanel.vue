<template>
  <div
    class="hub-chat-panel"
    :class="{ open: hubStore.chatPanelOpen }"
    :style="hubStore.chatPanelOpen ? { width: panelWidth + 'px', minWidth: panelWidth + 'px' } : {}"
  >
    <!-- Resize handle -->
    <div
      class="resize-handle"
      @mousedown.prevent="startResize"
    />
    <div class="chat-panel-inner" :style="{ width: panelWidth + 'px' }">
      <!-- Header -->
      <div class="chat-panel-header">
        <div class="header-title">
          <i class="pi pi-comments" />
          <span v-if="hubStore.selectedEntityName">
            {{ hubStore.selectedEntityName }}
          </span>
          <span v-else>AI Assistant</span>
        </div>
        <button class="close-btn" @click="hubStore.closeChatPanel()">
          <i class="pi pi-times" />
        </button>
      </div>

      <!-- Content -->
      <div class="chat-panel-content">
        <!-- Active chat session -->
        <template v-if="chatStore.activeSession">
          <ChatPanel
            :chat-session-id="chatStore.activeSession.id"
            :selected-entity-id="hubStore.selectedEntityId"
            :selected-document-id="hubStore.selectedDocumentId"
          />
        </template>

        <!-- Recent chats list (no active session) -->
        <template v-else>
          <div class="recent-chats">
            <h4 class="recent-title">Recent Chats</h4>
            <div v-if="chatStore.sessions.length === 0" class="no-chats">
              <i class="pi pi-inbox" style="font-size: 2rem; color: var(--p-text-muted-color);" />
              <p>No chat sessions yet.</p>
              <p class="hint">Click a node in the graph or search to start chatting.</p>
            </div>
            <div
              v-for="session in recentSessions"
              :key="session.id"
              class="session-item"
              @click="openSession(session.id)"
            >
              <i class="pi pi-comment" />
              <span class="session-title">{{ session.title }}</span>
            </div>
          </div>
        </template>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, onBeforeUnmount } from 'vue'
import ChatPanel from '@/components/knowledge_explorer/ChatPanel.vue'
import { useHubStore } from '@/stores/hubStore'
import { useChatStore } from '@/stores/chat_store'

const hubStore = useHubStore()
const chatStore = useChatStore()

// Resizable panel
const panelWidth = ref(380)
const MIN_WIDTH = 320
const MAX_WIDTH = 800

function startResize(e: MouseEvent) {
  const startX = e.clientX
  const startWidth = panelWidth.value

  function onMouseMove(ev: MouseEvent) {
    const delta = startX - ev.clientX // dragging left = wider
    panelWidth.value = Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, startWidth + delta))
  }

  function onMouseUp() {
    document.removeEventListener('mousemove', onMouseMove)
    document.removeEventListener('mouseup', onMouseUp)
    document.body.style.cursor = ''
    document.body.style.userSelect = ''
  }

  document.body.style.cursor = 'col-resize'
  document.body.style.userSelect = 'none'
  document.addEventListener('mousemove', onMouseMove)
  document.addEventListener('mouseup', onMouseUp)
}

const recentSessions = computed(() =>
  chatStore.sessions.slice(0, 10)
)

async function openSession(sessionId: number) {
  await chatStore.switchActiveSession(sessionId)
  hubStore.openChatPanel()
}

defineExpose({
  async sendChatMessage(message: string) {
    if (!chatStore.activeSession) {
      await chatStore.createSession(message.substring(0, 60), 'all_library')
    }
    hubStore.openChatPanel()
    await chatStore.sendMessage(message)
  }
})
</script>

<style scoped>
.hub-chat-panel {
  width: 0;
  min-width: 0;
  overflow: hidden;
  transition: width 0.3s ease, min-width 0.3s ease;
  border-left: 1px solid var(--p-content-border-color);
  background: var(--p-surface-card);
  flex-shrink: 0;
  position: relative;
}

.hub-chat-panel.open {
  /* width/min-width set via inline style for resizability */
  transition: none; /* disable transition while resizing */
}

.chat-panel-inner {
  height: 100%;
  display: flex;
  flex-direction: column;
}

/* Resize drag handle */
.resize-handle {
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 5px;
  cursor: col-resize;
  z-index: 10;
  background: transparent;
  transition: background 0.15s;
}

.resize-handle:hover,
.resize-handle:active {
  background: var(--p-primary-color);
  opacity: 0.4;
}

.chat-panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.75rem 1rem;
  border-bottom: 1px solid var(--p-content-border-color);
  flex-shrink: 0;
}

.header-title {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-weight: 600;
  font-size: 0.9rem;
  color: var(--p-text-color);
}

.header-title i {
  color: #64748b;
}

.close-btn {
  background: none;
  border: none;
  cursor: pointer;
  padding: 0.25rem;
  border-radius: 4px;
  color: var(--p-text-muted-color);
  transition: background-color 0.15s;
}

.close-btn:hover {
  background: var(--p-surface-hover);
  color: var(--p-text-color);
}

.chat-panel-content {
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

.chat-panel-content :deep(.chat-panel-container) {
  height: 100%;
}

/* Recent chats list styles */
.recent-chats {
  padding: 1rem;
}

.recent-title {
  font-size: 0.75rem;
  font-weight: 600;
  text-transform: uppercase;
  color: var(--p-text-muted-color);
  letter-spacing: 0.05em;
  margin-bottom: 0.75rem;
}

.no-chats {
  text-align: center;
  padding: 2rem 1rem;
  color: var(--p-text-muted-color);
}

.no-chats p {
  margin-top: 0.5rem;
  font-size: 0.85rem;
}

.no-chats .hint {
  font-size: 0.8rem;
  opacity: 0.7;
}

.session-item {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.6rem 0.75rem;
  border-radius: 6px;
  cursor: pointer;
  transition: background-color 0.15s;
  font-size: 0.85rem;
  color: var(--p-text-color);
}

.session-item:hover {
  background: var(--p-surface-hover);
}

.session-item i {
  color: var(--p-text-muted-color);
  font-size: 0.8rem;
  flex-shrink: 0;
}

.session-title {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

@media (max-width: 991px) {
  .hub-chat-panel.open {
    position: fixed;
    top: 4rem;
    right: 0;
    bottom: 0;
    width: 100% !important;
    min-width: 100% !important;
    z-index: 100;
  }

  .chat-panel-inner {
    width: 100% !important;
  }

  .resize-handle {
    display: none;
  }
}
</style>
