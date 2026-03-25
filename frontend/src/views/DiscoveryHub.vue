<template>
  <div class="discovery-hub">
    <!-- Left Sidebar: Smart Folders -->
    <div class="hub-sidebar" :class="{ collapsed: !sidebarVisible }">
      <SmartFoldersSidebar
        @bookmark-select="onBookmarkSelect"
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
    <HubChatPanel ref="chatPanel" />
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
}

/* Left Sidebar */
.hub-sidebar {
  width: 250px;
  min-width: 250px;
  flex-shrink: 0;
  transition: width 0.3s ease, min-width 0.3s ease, opacity 0.3s ease;
  overflow: hidden;
}

.hub-sidebar.collapsed {
  width: 0;
  min-width: 0;
  opacity: 0;
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
