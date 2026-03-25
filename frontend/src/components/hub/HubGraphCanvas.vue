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
        @zoom-in="zoomIn"
        @zoom-out="zoomOut"
        @fit="resetView"
        @relayout="runLayout"
        @reset="onReset"
      />
    </div>

    <!-- Loading spinner -->
    <div v-if="graphStore.loading || hubStore.initialLoading" class="graph-loading">
      <ProgressSpinner strokeWidth="4" style="width: 48px; height: 48px;" />
    </div>

    <!-- Expand "+" button overlay for unexpanded entity nodes -->
    <button
      v-if="expandBtnPos"
      class="expand-btn"
      :style="{ left: expandBtnPos.x + 'px', top: expandBtnPos.y + 'px' }"
      @click="onExpandClick"
      title="Expand this node's connections"
    >
      <i class="pi pi-plus" />
    </button>

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

// Expand button overlay state
const expandBtnPos = ref<{ x: number; y: number } | null>(null)
const expandBtnEntityId = ref<string | null>(null)

function updateExpandBtnPosition() {
  if (!expandBtnEntityId.value || !cy.value) {
    expandBtnPos.value = null
    return
  }
  const node = cy.value.getElementById(expandBtnEntityId.value)
  if (node.length === 0 || node.removed()) {
    expandBtnPos.value = null
    return
  }
  const pos = node.renderedPosition()
  // Offset to top-right of the node
  const container = cyContainer.value
  if (!container) return
  expandBtnPos.value = { x: pos.x + 24, y: pos.y - 24 }
}

function showExpandBtn(entityId: string) {
  // Only show for non-expanded entity nodes
  if (graphStore.isNodeExpanded(entityId)) {
    expandBtnPos.value = null
    expandBtnEntityId.value = null
    return
  }
  expandBtnEntityId.value = entityId
  // Delay to ensure node is rendered and positioned
  nextTick(() => updateExpandBtnPosition())
}

function hideExpandBtn() {
  expandBtnPos.value = null
  expandBtnEntityId.value = null
}

function onExpandClick() {
  if (!expandBtnEntityId.value) return
  const entityId = expandBtnEntityId.value
  hideExpandBtn()
  graphStore.expandEntity(entityId).then(() => {
    focusEntity(entityId)
  })
}

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
  resetView,
  runLayout,
  clearGraph,
} = useCytoscape({
  container: cyContainer,
  elements,
  onEntitySelect: (entityId: string) => {
    if (!entityId) {
      hubStore.clearSelection()
      hideExpandBtn()
      return
    }
    showExpandBtn(entityId)
    hubStore.selectEntity(Number(entityId))
  },
  onDocumentSelect: (docId: string) => {
    hideExpandBtn()
    const numericId = Number(docId.replace('doc-', ''))
    hubStore.selectDocument(numericId)
    focusEntity(docId)
  },
  onRelationshipSelect: (relId: string) => {
    graphStore.selectRelationship(relId)
  },
  onEntityExpand: (entityId: string) => {
    hideExpandBtn()
    graphStore.expandEntity(entityId).then(() => {
      focusEntity(entityId)
    })
  },
})

// Keep expand button position in sync with graph viewport changes
watch(() => cy.value, (instance) => {
  if (!instance) return
  instance.on('zoom pan', () => updateExpandBtnPosition())
}, { immediate: true })

async function onSearchSelect(id: number, type: 'entity' | 'relationship' | 'document') {
  if (type === 'entity') {
    // Reset chat session for new search exploration
    chatStore.activeSession = null

    await graphStore.handleSearchSelect(id, type, () => {})
    // Wait for Vue reactivity + Cytoscape watcher + layout to settle
    await nextTick()
    setTimeout(() => {
      focusEntity(String(id))
      // Show expand button after radial layout settles
      setTimeout(() => showExpandBtn(String(id)), 600)
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

/* Expand "+" button overlay */
.expand-btn {
  position: absolute;
  z-index: 15;
  width: 24px;
  height: 24px;
  border-radius: 50%;
  border: 2px solid #3B82F6;
  background: white;
  color: #3B82F6;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  font-size: 12px;
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.15);
  transition: transform 0.15s, background 0.15s;
  transform: translate(-50%, -50%);
}

.expand-btn:hover {
  background: #3B82F6;
  color: white;
  transform: translate(-50%, -50%) scale(1.15);
}
</style>
