<template>
  <div class="discovery-hub">
    <!-- Left Sidebar: Smart Folders -->
    <div
      class="hub-sidebar"
      :class="{ collapsed: !sidebarVisible }"
      :style="sidebarVisible ? { width: sidebarWidth + 'px', minWidth: sidebarWidth + 'px' } : {}"
    >
      <SmartFoldersSidebar
        @bookmark-select="onBookmarkSelect"
      />
      <!-- Resize handle -->
      <div
        v-if="sidebarVisible"
        class="sidebar-resize-handle"
        @mousedown.prevent="startSidebarResize"
      />
    </div>

    <!-- Sidebar toggle for mobile -->
    <button
      class="sidebar-toggle"
      :class="{ 'sidebar-open': sidebarVisible }"
      @click="sidebarVisible = !sidebarVisible"
    >
      <i :class="sidebarVisible ? 'pi pi-angle-left' : 'pi pi-angle-right'" />
    </button>

    <!-- Center: Graph Canvas -->
    <div class="hub-center">
      <HubGraphCanvas
        ref="graphCanvas"
        @search-chat="onSearchChat"
      />
    </div>

    <!-- Right: Chat Panel -->
    <HubChatPanel ref="chatPanel" @panel-resize="onPanelResize" />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import SmartFoldersSidebar from '@/components/hub/SmartFoldersSidebar.vue'
import HubGraphCanvas from '@/components/hub/HubGraphCanvas.vue'
import HubChatPanel from '@/components/hub/HubChatPanel.vue'
import { useHubStore } from '@/stores/hubStore'
import { useChatStore } from '@/stores/chat_store'
import type { DocumentSummary } from '@/types/graph'

const route = useRoute()
const hubStore = useHubStore()
const chatStore = useChatStore()

const graphCanvas = ref<InstanceType<typeof HubGraphCanvas> | null>(null)
const chatPanel = ref<InstanceType<typeof HubChatPanel> | null>(null)
const sidebarVisible = ref(true)

// Resizable left sidebar
const sidebarWidth = ref(250)
const SIDEBAR_MIN_WIDTH = 200
const SIDEBAR_MAX_WIDTH = 500

function startSidebarResize(e: MouseEvent) {
  const startX = e.clientX
  const startWidth = sidebarWidth.value

  function onMouseMove(ev: MouseEvent) {
    const delta = ev.clientX - startX
    sidebarWidth.value = Math.min(SIDEBAR_MAX_WIDTH, Math.max(SIDEBAR_MIN_WIDTH, startWidth + delta))
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

// Refit graph when chat panel is resized
function onPanelResize() {
  graphCanvas.value?.refitGraph()
}

// Handle search bar enter → send to chat
async function onSearchChat(query: string) {
  await chatPanel.value?.sendChatMessage(query)
}

// Handle bookmark click in sidebar → select document in graph
function onBookmarkSelect(doc: DocumentSummary) {
  hubStore.selectDocument(doc.id)
}

onMounted(async () => {
  // Load initial data
  await Promise.all([
    hubStore.loadDiscoveryGraph(),
    hubStore.loadSources(),
    hubStore.loadThemes(),
    hubStore.loadResearchSessions(),
    chatStore.loadSessions(),
  ])

  // Handle deep-link query params
  const entityId = route.query.entity
  if (entityId) {
    await hubStore.selectEntity(Number(entityId))
  }

  const chatId = route.query.chat
  if (chatId) {
    await chatStore.switchActiveSession(Number(chatId))
    hubStore.openChatPanel()
  }

  // Handle mobile
  if (window.innerWidth < 992) {
    sidebarVisible.value = false
  }
})
</script>

<style scoped>
.discovery-hub {
  display: flex;
  height: calc(100vh - 4rem);
  overflow: hidden;
  position: relative;
  font-size: var(--app-font-size, 1.125rem);
}

/* Left Sidebar */
.hub-sidebar {
  width: 250px;
  min-width: 250px;
  flex-shrink: 0;
  overflow: hidden;
  position: relative;
}

/* Sidebar resize handle */
.sidebar-resize-handle {
  position: absolute;
  right: 0;
  top: 0;
  bottom: 0;
  width: 5px;
  cursor: col-resize;
  z-index: 10;
  background: transparent;
  transition: background 0.15s;
}

.sidebar-resize-handle:hover,
.sidebar-resize-handle:active {
  background: var(--p-primary-color);
  opacity: 0.4;
}

.hub-sidebar.collapsed {
  width: 0 !important;
  min-width: 0 !important;
  opacity: 0;
  transition: width 0.3s ease, min-width 0.3s ease, opacity 0.3s ease;
}

/* Sidebar toggle button */
.sidebar-toggle {
  display: none;
  position: absolute;
  left: 0;
  top: 50%;
  transform: translateY(-50%);
  z-index: 30;
  background: var(--p-surface-card);
  border: 1px solid var(--p-content-border-color);
  border-left: none;
  border-radius: 0 6px 6px 0;
  padding: 0.5rem 0.25rem;
  cursor: pointer;
  color: var(--p-text-muted-color);
  transition: left 0.3s ease;
}

.sidebar-toggle.sidebar-open {
  left: 250px;
}

/* Center Graph */
.hub-center {
  flex: 1;
  min-width: 0;
  overflow: hidden;
}

@media (max-width: 991px) {
  .hub-sidebar {
    position: fixed;
    top: 4rem;
    left: 0;
    bottom: 0;
    z-index: 50;
    box-shadow: 2px 0 8px rgba(0, 0, 0, 0.1);
  }

  .hub-sidebar.collapsed {
    transform: translateX(-100%);
    opacity: 1;
    width: 250px;
    min-width: 250px;
  }

  .sidebar-toggle {
    display: block;
  }
}
</style>
