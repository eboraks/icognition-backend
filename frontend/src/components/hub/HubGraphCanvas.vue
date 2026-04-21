<template>
  <div class="hub-graph-canvas">
    <!-- Search bar overlay -->
    <UnifiedSearchBar
      @select="onSearchSelect"
      @chat="onSearchChat"
    />

    <!-- Graph canvas -->
    <div ref="cyContainer" class="graph-container" />

    <!-- Controls overlay -->
    <div class="graph-controls-overlay">
      <GraphControls
        :can-expand="canExpandSelected"
        :has-selection="!!selectedNodeId"
        :font-size="currentFontSize"
        :chat-filter-active="chatStore.chatFilterActive"
        @zoom-in="zoomIn"
        @zoom-out="zoomOut"
        @fit="resetView"
        @focus="onFocusSelected"
        @expand="onExpandSelected"
        @font-size-change="setFontSize"
        @relayout="runLayout"
        @toggle-chat-filter="onToggleChatFilter"
        @toggle-chat="hubStore.chatPanelOpen ? hubStore.closeChatPanel() : hubStore.openChatPanel()"
        @reset="onReset"
      />
    </div>

    <!-- Loading spinner -->
    <div v-if="graphStore.loading || hubStore.initialLoading" class="graph-loading">
      <ProgressSpinner strokeWidth="4" style="width: 48px; height: 48px;" />
    </div>

    <!-- Empty state -->
    <div v-if="!hubStore.initialLoading && elements.length === 0" class="graph-empty">
      <i class="pi pi-sitemap" style="font-size: 3rem; color: var(--p-text-muted-color);" />
      <p>No knowledge graph data yet.</p>
      <p class="text-sm" style="color: var(--p-text-muted-color);">
        Save articles to build your knowledge graph.
      </p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch, nextTick } from 'vue'
import ProgressSpinner from 'primevue/progressspinner'
import UnifiedSearchBar from './UnifiedSearchBar.vue'
import GraphControls from '@/components/knowledge_explorer/GraphControls.vue'
import { useGraphStore } from '@/stores/graphStore'
import { useHubStore } from '@/stores/hubStore'
import { useChatStore } from '@/stores/chat_store'
import { useCytoscape } from '@/composables/useCytoscape'
import { transformToCytoscapeElements } from '@/utils/graphTransform'

const emit = defineEmits<{
  'search-chat': [query: string]
}>()

const graphStore = useGraphStore()
const hubStore = useHubStore()
const chatStore = useChatStore()
const cyContainer = ref<HTMLElement | null>(null)

// Track selected entity for expand button
const selectedEntityId = ref<string | null>(null)
// Track ANY selected node (entity or document) for focus button
const selectedNodeId = ref<string | null>(null)

const canExpandSelected = computed(() => {
  if (!selectedEntityId.value) return false
  return !graphStore.isNodeExpanded(selectedEntityId.value)
})

function onExpandSelected() {
  if (!selectedEntityId.value || !canExpandSelected.value) return
  const entityId = selectedEntityId.value
  graphStore.expandEntity(entityId).then(() => {
    focusEntity(entityId)
  })
}

function onFocusSelected() {
  const nodeId = selectedNodeId.value
  if (!nodeId || !cy.value) return
  const node = cy.value.getElementById(nodeId)
  if (node.length === 0) return

  // Animate fit on the selected node + its direct neighbors
  const neighborhood = node.closedNeighborhood()
  cy.value.animate(
    { fit: { eles: neighborhood, padding: 80 } },
    { duration: 400 }
  )
  // Ensure the node is selected visually
  cy.value.elements().unselect()
  node.select()
}

function onToggleChatFilter() {
  chatStore.toggleChatFilter()
  if (chatStore.chatFilterActive) {
    const entityIds = chatStore.chatContextEntityIds
    const docIds = chatStore.chatContextDocumentIds
    if (entityIds.size > 0 || docIds.size > 0) {
      applyChatContextFilter(entityIds, docIds)
    }
  } else {
    clearChatContextFilter()
  }
}

// Auto-apply filter when new context arrives from a chat response
watch(
  () => [chatStore.chatContextEntityIds.size, chatStore.chatContextDocumentIds.size],
  ([entityCount, docCount]) => {
    if (entityCount > 0 || docCount > 0) {
      // Auto-activate filter when context first arrives
      if (!chatStore.chatFilterActive) {
        chatStore.chatFilterActive = true
      }
      applyChatContextFilter(chatStore.chatContextEntityIds, chatStore.chatContextDocumentIds)
    }
  }
)

const elements = computed(() =>
  transformToCytoscapeElements(
    graphStore.entities,
    graphStore.relationships,
    graphStore.documents,
    graphStore.entityDocumentLinks
  )
)

const {
  cy,
  focusEntity,
  zoomIn,
  zoomOut,
  zoomToEntity,
  resetView,
  runLayout,
  clearGraph,
  setFontSize,
  currentFontSize,
  applyChatContextFilter,
  clearChatContextFilter,
} = useCytoscape({
  container: cyContainer,
  elements,
  onEntitySelect: (entityId: string) => {
    if (!entityId) {
      hubStore.clearSelection()
      selectedEntityId.value = null
      selectedNodeId.value = null
      return
    }
    selectedEntityId.value = entityId
    selectedNodeId.value = entityId
    hubStore.selectEntity(Number(entityId))
  },
  onDocumentSelect: (docId: string) => {
    selectedEntityId.value = null
    selectedNodeId.value = docId
    const numericId = Number(docId.replace('doc-', ''))
    hubStore.selectDocument(numericId)
  },
  onRelationshipSelect: (relId: string) => {
    graphStore.selectRelationship(relId)
  },
  onEntityExpand: (entityId: string) => {
    graphStore.expandEntity(entityId).then(() => {
      focusEntity(entityId)
    })
  },
})


async function onSearchSelect(id: number, type: 'entity' | 'relationship' | 'document') {
  if (type === 'entity') {
    // Reset chat session for new search exploration
    chatStore.activeSession = null

    await graphStore.handleSearchSelect(id, type, () => {})
    selectedEntityId.value = String(id)
    // Wait for Vue reactivity + Cytoscape watcher + layout to settle
    await nextTick()
    setTimeout(() => {
      focusEntity(String(id))
    }, 100)
    hubStore.selectEntity(id)
  } else if (type === 'document') {
    graphStore.handleSearchSelect(id, type, (nodeId: string) => {
      focusEntity(nodeId)
    })
    hubStore.selectDocument(id)
  } else {
    graphStore.handleSearchSelect(id, type, () => {})
  }
}

function onSearchChat(query: string) {
  emit('search-chat', query)
}

function onReset() {
  graphStore.resetGraph()
  hubStore.clearSelection()
  hubStore.loadDiscoveryGraph(hubStore.sourceFilter || undefined)
}

function refitGraph() {
  cy.value?.resize()
  cy.value?.fit(undefined, 50)
}

defineExpose({ refitGraph })

onMounted(() => {
  // Initial view fit after data loads
  setTimeout(() => {
    if (elements.value.length > 0) {
      resetView()
    }
  }, 500)
})
</script>

<style scoped>
.hub-graph-canvas {
  position: relative;
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
  background: var(--p-surface-ground);
}

.graph-container {
  flex: 1;
  min-height: 0;
}

.graph-controls-overlay {
  position: absolute;
  bottom: 1rem;
  left: 1rem;
  z-index: 10;
}

.graph-loading {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  z-index: 5;
}

.graph-empty {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  text-align: center;
  color: var(--p-text-color);
  z-index: 5;
}

.graph-empty p {
  margin-top: 0.75rem;
}



</style>
