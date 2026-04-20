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
      <!-- Header with tabs -->
      <div class="panel-header">
        <div class="tab-bar">
          <button
            class="tab-btn"
            :class="{ active: activeTab === 'details' }"
            @click="activeTab = 'details'"
          >
            <i class="pi pi-info-circle" />
            <span>Details</span>
            <span v-if="hasSelection" class="tab-dot" />
          </button>
          <button
            class="tab-btn"
            :class="{ active: activeTab === 'chat' }"
            @click="activeTab = 'chat'"
          >
            <i class="pi pi-comments" />
            <span>Chat</span>
          </button>
        </div>
        <button class="close-btn" @click="hubStore.closeChatPanel()">
          <i class="pi pi-times" />
        </button>
      </div>

      <!-- Tab content -->
      <div class="panel-content">
        <!-- DETAILS TAB -->
        <div v-show="activeTab === 'details'" class="tab-pane details-pane">
          <!-- Entity details -->
          <template v-if="graphStore.selectedType === 'entity' && entityDetail">
            <div class="detail-header">
              <span class="detail-type-badge">{{ entityDetail.type }}</span>
              <h3 class="detail-title">{{ entityDetail.name }}</h3>
            </div>
            <div
              v-if="entityDetail.description"
              class="detail-description markdown-body"
              v-html="renderedEntityDescription"
            />
            <button
              v-if="isEntityDescriptionLong"
              class="expand-toggle"
              @click="entityDescriptionExpanded = !entityDescriptionExpanded"
            >
              {{ entityDescriptionExpanded ? 'Show less' : 'Show more' }}
            </button>

            <!-- Related documents -->
            <div v-if="relatedBookmarks.length" class="detail-section">
              <h4 class="section-title">Appears in {{ relatedBookmarks.length }} document{{ relatedBookmarks.length > 1 ? 's' : '' }}</h4>
              <div
                v-for="doc in relatedBookmarks"
                :key="doc.id"
                class="doc-item"
                @click="hubStore.selectDocument(doc.id)"
              >
                <i class="pi pi-file" />
                <span>{{ doc.title }}</span>
              </div>
            </div>
          </template>

          <!-- Document details -->
          <template v-else-if="graphStore.selectedType === 'document' && documentDetail">
            <div class="detail-header">
              <span class="detail-type-badge">Document</span>
              <h3 class="detail-title">
                <a v-if="documentDetail.url" :href="documentDetail.url" target="_blank" rel="noopener">
                  {{ documentDetail.title }}
                </a>
                <template v-else>{{ documentDetail.title }}</template>
              </h3>
            </div>
            <div
              v-if="documentDetail.ai_markdown_content"
              class="detail-description markdown-body"
              v-html="renderedDocumentContent"
            />
            <button
              v-if="isDocumentContentLong"
              class="expand-toggle"
              @click="documentContentExpanded = !documentContentExpanded"
            >
              {{ documentContentExpanded ? 'Show less' : 'Show more' }}
            </button>
            <div v-if="documentDetail.entities?.length" class="detail-section">
              <h4 class="section-title">Entities mentioned</h4>
              <div
                v-for="entity in documentDetail.entities"
                :key="entity.id"
                class="doc-item"
                @click="hubStore.selectEntity(entity.id)"
              >
                <i class="pi pi-circle-fill" :style="{ fontSize: '0.5rem' }" />
                <span>{{ entity.name }}</span>
              </div>
            </div>
          </template>

          <!-- Research result details -->
          <template v-else-if="hubStore.selectedResearchDetail?.final_response">
            <div class="detail-header">
              <span class="detail-type-badge">Research</span>
              <h3 class="detail-title">{{ hubStore.selectedResearchDetail.brief }}</h3>
              <div class="research-meta">
                {{ new Date(hubStore.selectedResearchDetail.created_at).toLocaleDateString() }}
                <span v-if="hubStore.selectedResearchDetail.documents?.length">
                  &middot; {{ hubStore.selectedResearchDetail.documents.length }} sources
                </span>
              </div>
            </div>
            <div class="detail-description markdown-body message-text"
                 v-html="renderMarkdown(hubStore.selectedResearchDetail.final_response)"
            />
            <div v-if="hubStore.selectedResearchDetail.documents?.length" class="detail-section">
              <h4 class="section-title">Saved Sources</h4>
              <div
                v-for="doc in hubStore.selectedResearchDetail.documents"
                :key="doc.id"
                class="doc-item"
              >
                <i class="pi pi-file" />
                <a v-if="doc.url" :href="doc.url" target="_blank" rel="noopener" class="doc-link">{{ doc.title }}</a>
                <span v-else>{{ doc.title }}</span>
              </div>
            </div>
          </template>

          <!-- No selection -->
          <template v-else>
            <div class="no-selection">
              <i class="pi pi-hand-point-up" style="font-size: 2rem; color: var(--p-text-muted-color);" />
              <p>Select a node in the graph to see its details.</p>
            </div>
          </template>
        </div>

        <!-- CHAT TAB -->
        <div v-show="activeTab === 'chat'" class="tab-pane chat-pane">
          <template v-if="chatStore.activeSession">
            <!-- Active chat header with title + history toggle -->
            <div class="chat-session-header">
              <div class="chat-title-row">
                <template v-if="editingTitle">
                  <input
                    ref="titleInput"
                    v-model="editTitleValue"
                    class="title-input"
                    @keydown.enter="saveTitle"
                    @keydown.escape="editingTitle = false"
                    @blur="saveTitle"
                  />
                </template>
                <template v-else>
                  <span class="chat-session-title" @click="startEditTitle">
                    {{ chatStore.activeSession.title }}
                  </span>
                  <button class="icon-btn" @click="startEditTitle" title="Rename chat">
                    <i class="pi pi-pencil" />
                  </button>
                </template>
              </div>
              <div class="chat-header-actions">
                <button class="icon-btn" @click="showHistory = !showHistory" title="Chat history">
                  <i class="pi pi-history" />
                </button>
                <button class="icon-btn" @click="startNewChat" title="New chat">
                  <i class="pi pi-plus" />
                </button>
              </div>
            </div>

            <!-- History dropdown -->
            <div v-if="showHistory" class="history-dropdown">
              <div
                v-for="session in recentSessions"
                :key="session.id"
                class="session-item"
                :class="{ active: session.id === chatStore.activeSession?.id }"
                @click="openSession(session.id); showHistory = false"
              >
                <i class="pi pi-comment" />
                <span class="session-title">{{ session.title }}</span>
                <button
                  class="delete-btn"
                  @click.stop="chatStore.deleteSession(session.id)"
                  title="Delete chat"
                >
                  <i class="pi pi-trash" />
                </button>
              </div>
            </div>

            <ChatPanel
              :chat-session-id="chatStore.activeSession.id"
              :selected-entity-id="hubStore.selectedEntityId"
              :selected-document-id="hubStore.selectedDocumentId"
            />
          </template>

          <template v-else>
            <div class="recent-chats">
              <div class="recent-header">
                <h4 class="recent-title">Recent Chats</h4>
                <button class="icon-btn" @click="startNewChat" title="New chat">
                  <i class="pi pi-plus" />
                </button>
              </div>
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
                <button
                  class="delete-btn"
                  @click.stop="chatStore.deleteSession(session.id)"
                  title="Delete chat"
                >
                  <i class="pi pi-trash" />
                </button>
              </div>
            </div>
          </template>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch, nextTick } from 'vue'
import { marked } from 'marked'
import ChatPanel from '@/components/knowledge_explorer/ChatPanel.vue'
import { useHubStore } from '@/stores/hubStore'
import { useChatStore } from '@/stores/chat_store'
import { useGraphStore } from '@/stores/graphStore'
import type { EntityRead, DocumentRead } from '@/types/graph'

const hubStore = useHubStore()
const chatStore = useChatStore()
const graphStore = useGraphStore()

const activeTab = ref<'details' | 'chat'>('details')

function renderMarkdown(text: string): string {
  if (!text) return ''
  // Strip <p> wrapper tags that the backend adds — they prevent marked from
  // parsing markdown inside them.
  let cleaned = text
    .replace(/<p>/gi, '')
    .replace(/<\/p>/gi, '\n\n')
    .trim()
  return marked.parse(cleaned, { async: false }) as string
}

// Auto-switch to Details tab when a node is selected
const hasSelection = computed(() => hubStore.selectedEntityId !== null || hubStore.selectedDocumentId !== null)

watch(hasSelection, (val) => {
  if (val) activeTab.value = 'details'
})

// Auto-switch to Chat tab when requested
watch(() => hubStore.requestChatTab, (val) => {
  if (val) {
    activeTab.value = 'chat'
    hubStore.requestChatTab = false
  }
})

// Auto-switch to Details tab when requested (e.g. research session clicked)
watch(() => hubStore.requestDetailsTab, (val) => {
  if (val) {
    activeTab.value = 'details'
    hubStore.requestDetailsTab = false
  }
})

// Detail data
const entityDetail = computed(() => {
  if (graphStore.selectedType !== 'entity') return null
  return graphStore.selectedElement as EntityRead | null
})

const documentDetail = computed(() => {
  if (graphStore.selectedType !== 'document') return null
  return graphStore.selectedElement as DocumentRead | null
})

const relatedBookmarks = computed(() => hubStore.relatedBookmarks || [])

// Markdown rendering for entity description and document content
const DESCRIPTION_PREVIEW_LIMIT = 400
const entityDescriptionExpanded = ref(false)
const documentContentExpanded = ref(false)

// Reset expanded state when selection changes
watch(
  () => [hubStore.selectedEntityId, hubStore.selectedDocumentId],
  () => {
    entityDescriptionExpanded.value = false
    documentContentExpanded.value = false
  }
)

const isEntityDescriptionLong = computed(() => {
  const desc = entityDetail.value?.description || ''
  return desc.length > DESCRIPTION_PREVIEW_LIMIT
})

const renderedEntityDescription = computed(() => {
  const desc = entityDetail.value?.description || ''
  if (!desc) return ''
  const text = !entityDescriptionExpanded.value && isEntityDescriptionLong.value
    ? desc.substring(0, DESCRIPTION_PREVIEW_LIMIT) + '…'
    : desc
  return marked.parse(text) as string
})

const isDocumentContentLong = computed(() => {
  const content = documentDetail.value?.ai_markdown_content || ''
  return content.length > DESCRIPTION_PREVIEW_LIMIT
})

const renderedDocumentContent = computed(() => {
  const content = documentDetail.value?.ai_markdown_content || ''
  if (!content) return ''
  const text = !documentContentExpanded.value && isDocumentContentLong.value
    ? content.substring(0, DESCRIPTION_PREVIEW_LIMIT) + '…'
    : content
  return marked.parse(text) as string
})

// Chat history & rename
const showHistory = ref(false)
const editingTitle = ref(false)
const editTitleValue = ref('')
const titleInput = ref<HTMLInputElement | null>(null)

function startEditTitle() {
  if (!chatStore.activeSession) return
  editTitleValue.value = chatStore.activeSession.title
  editingTitle.value = true
  nextTick(() => titleInput.value?.focus())
}

async function saveTitle() {
  if (!chatStore.activeSession || !editTitleValue.value.trim()) {
    editingTitle.value = false
    return
  }
  await chatStore.renameSession(chatStore.activeSession.id, editTitleValue.value.trim())
  editingTitle.value = false
}

async function startNewChat() {
  await chatStore.createSession('New Chat', 'all_library')
  showHistory.value = false
  activeTab.value = 'chat'
}

// Resizable panel
const panelWidth = ref(420)
const MIN_WIDTH = 340
const MAX_WIDTH = 800

function startResize(e: MouseEvent) {
  const startX = e.clientX
  const startWidth = panelWidth.value

  function onMouseMove(ev: MouseEvent) {
    const delta = startX - ev.clientX
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
  activeTab.value = 'chat'
}

defineExpose({
  async sendChatMessage(message: string) {
    if (!chatStore.activeSession) {
      await chatStore.createSession(message.substring(0, 60), 'all_library')
    }
    activeTab.value = 'chat'
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
  font-size: var(--app-font-size, 12px);
}

.hub-chat-panel.open {
  transition: none;
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

/* Header with tabs */
.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-bottom: 1px solid var(--p-content-border-color);
  flex-shrink: 0;
  padding-right: 0.5rem;
}

.tab-bar {
  display: flex;
  gap: 0;
}

.tab-btn {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  padding: 0.7rem 1rem;
  border: none;
  background: none;
  cursor: pointer;
  font-size: 0.95em;
  font-weight: 500;
  color: var(--p-text-muted-color);
  border-bottom: 2px solid transparent;
  transition: color 0.15s, border-color 0.15s;
  position: relative;
}

.tab-btn:hover {
  color: var(--p-text-color);
}

.tab-btn.active {
  color: var(--p-text-color);
  border-bottom-color: var(--p-primary-color);
}

.tab-btn i {
  font-size: 1em;
}

.tab-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--p-primary-color);
  margin-left: 0.1rem;
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

/* Panel content */
.panel-content {
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

.tab-pane {
  height: 100%;
  overflow-y: auto;
}

.chat-pane {
  display: flex;
  flex-direction: column;
}

.chat-pane :deep(.chat-panel-container) {
  height: 100%;
}

/* Details tab */
.details-pane {
  padding: 1rem 1.25rem;
}

.detail-header {
  margin-bottom: 0.75rem;
}

.detail-type-badge {
  font-size: 0.8em;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--p-primary-color);
  background: var(--p-primary-50, #f0fdf4);
  padding: 0.15rem 0.5rem;
  border-radius: 4px;
}

.detail-title {
  font-size: 1.25em;
  font-weight: 700;
  color: var(--p-text-color);
  margin: 0.5rem 0 0 0;
  line-height: 1.3;
}

.detail-title a {
  color: var(--p-text-color);
  text-decoration: none;
  transition: color 0.15s;
}

.detail-title a:hover {
  color: var(--p-primary-color);
  text-decoration: underline;
}

.detail-description {
  font-size: var(--app-font-size, 14px);
  line-height: 1.7;
  color: #1e293b;
  margin-bottom: 0.5rem;
  word-wrap: break-word;
}

.research-meta {
  font-size: 0.85em;
  color: var(--p-text-muted-color);
  margin-top: 0.25rem;
}

.doc-link {
  color: var(--p-primary-color);
  text-decoration: none;
}

.doc-link:hover {
  text-decoration: underline;
}

/* Markdown rendering inside the details panel */
.markdown-body :deep(p) {
  margin: 0 0 1em 0;
  line-height: 1.7;
}
.markdown-body :deep(p:last-child) {
  margin-bottom: 0;
}
.markdown-body :deep(strong) {
  font-weight: 600;
  color: var(--p-text-color);
}
.markdown-body :deep(em) {
  font-style: italic;
}
.markdown-body :deep(h1),
.markdown-body :deep(h2),
.markdown-body :deep(h3),
.markdown-body :deep(h4) {
  font-weight: 700;
  color: var(--p-text-color);
  line-height: 1.3;
}
.markdown-body :deep(h1) { font-size: 1.3em; margin: 1.5em 0 0.5em 0; }
.markdown-body :deep(h2) { font-size: 1.2em; margin: 1.5em 0 0.5em 0; }
.markdown-body :deep(h3) { font-size: 1.1em; margin: 1.25em 0 0.4em 0; }
.markdown-body :deep(h4) { font-size: 1.05em; margin: 1em 0 0.3em 0; }
.markdown-body :deep(ul),
.markdown-body :deep(ol) {
  margin: 0.5em 0 1em 0;
  padding-left: 1.5em;
}
.markdown-body :deep(ul) {
  list-style-type: disc;
}
.markdown-body :deep(li) {
  margin-bottom: 0.4em;
  line-height: 1.65;
}
.markdown-body :deep(a) {
  color: #2563eb;
  text-decoration: underline;
  text-decoration-color: rgba(37, 99, 235, 0.3);
}
.markdown-body :deep(a:hover) {
  text-decoration-color: rgba(37, 99, 235, 0.8);
}
.markdown-body :deep(code) {
  background: var(--p-surface-100);
  padding: 0.1rem 0.3rem;
  border-radius: 3px;
  font-size: 0.95em;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}
.markdown-body :deep(pre) {
  background: var(--p-surface-100);
  padding: 0.5rem 0.75rem;
  border-radius: 4px;
  overflow-x: auto;
  font-size: 0.95em;
  margin: 0 0 0.6rem 0;
}
.markdown-body :deep(pre code) {
  background: none;
  padding: 0;
}
.markdown-body :deep(blockquote) {
  border-left: 3px solid var(--p-content-border-color);
  padding-left: 0.75rem;
  margin: 0 0 0.6rem 0;
  color: var(--p-text-muted-color);
}
.markdown-body :deep(a) {
  color: var(--p-primary-color);
  text-decoration: none;
}
.markdown-body :deep(a:hover) {
  text-decoration: underline;
}

.expand-toggle {
  background: none;
  border: none;
  padding: 0.25rem 0;
  margin-bottom: 1rem;
  cursor: pointer;
  font-size: 0.92em;
  font-weight: 600;
  color: var(--p-primary-color);
  transition: color 0.15s;
}

.expand-toggle:hover {
  text-decoration: underline;
}

.detail-section {
  margin-top: 1.25rem;
}

.section-title {
  font-size: 0.85em;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--p-text-muted-color);
  margin-bottom: 0.5rem;
}

.doc-item {
  display: flex;
  align-items: flex-start;
  gap: 0.5rem;
  padding: 0.5rem 0.6rem;
  border-radius: 6px;
  cursor: pointer;
  font-size: 0.97em;
  color: var(--p-text-color);
  line-height: 1.4;
  transition: background 0.15s;
}

.doc-item:hover {
  background: var(--p-surface-hover);
}

.doc-item i {
  color: var(--p-text-muted-color);
  font-size: 0.95em;
  flex-shrink: 0;
  margin-top: 0.15rem;
}

.no-selection {
  text-align: center;
  padding: 3rem 1rem;
  color: var(--p-text-muted-color);
}

.no-selection p {
  margin-top: 0.75rem;
  font-size: 1em;
}

/* Chat session header */
.chat-session-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.5rem 0.75rem;
  border-bottom: 1px solid var(--p-content-border-color);
  flex-shrink: 0;
  min-height: 2.5rem;
}

.chat-title-row {
  display: flex;
  align-items: center;
  gap: 0.35rem;
  flex: 1;
  min-width: 0;
}

.chat-session-title {
  font-size: 0.95em;
  font-weight: 600;
  color: var(--p-text-color);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  cursor: pointer;
}

.chat-session-title:hover {
  color: var(--p-primary-color);
}

.title-input {
  flex: 1;
  font-size: 0.95em;
  font-weight: 600;
  padding: 0.2rem 0.4rem;
  border: 1px solid var(--p-primary-color);
  border-radius: 4px;
  outline: none;
  background: var(--p-surface-card);
  color: var(--p-text-color);
}

.chat-header-actions {
  display: flex;
  gap: 0.25rem;
  flex-shrink: 0;
}

.icon-btn {
  background: none;
  border: none;
  cursor: pointer;
  padding: 0.3rem;
  border-radius: 4px;
  color: var(--p-text-muted-color);
  font-size: 0.95em;
  transition: background 0.15s, color 0.15s;
}

.icon-btn:hover {
  background: var(--p-surface-hover);
  color: var(--p-text-color);
}

/* History dropdown */
.history-dropdown {
  border-bottom: 1px solid var(--p-content-border-color);
  max-height: 200px;
  overflow-y: auto;
  background: var(--p-surface-ground);
  padding: 0.25rem;
}

.recent-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 0.5rem;
}

.delete-btn {
  background: none;
  border: none;
  cursor: pointer;
  padding: 0.2rem;
  border-radius: 4px;
  color: var(--p-text-muted-color);
  font-size: 0.7rem;
  opacity: 0;
  transition: opacity 0.15s, color 0.15s;
}

.session-item:hover .delete-btn {
  opacity: 1;
}

.delete-btn:hover {
  color: #ef4444;
}

.session-item.active {
  background: var(--p-surface-hover);
  font-weight: 600;
}

/* Recent chats list styles */
.recent-chats {
  padding: 1rem;
}

.recent-title {
  font-size: 0.9em;
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
  font-size: 1em;
}

.no-chats .hint {
  font-size: 0.95em;
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
  font-size: 1em;
  color: var(--p-text-color);
}

.session-item:hover {
  background: var(--p-surface-hover);
}

.session-item i {
  color: var(--p-text-muted-color);
  font-size: 0.95em;
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
