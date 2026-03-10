<template>
  <div class="graph-explorer">
    <!-- Search bar -->
    <div class="graph-explorer__search" :style="graphStore.selectedElement ? { paddingRight: 'calc(320px + 0.75rem)' } : {}">
      <GraphSearchBar @select="onSearchSelect" />
    </div>

    <!-- Graph canvas -->
    <div ref="containerRef" class="graph-explorer__canvas" :style="graphStore.selectedElement ? { marginRight: '320px' } : {}" />

    <!-- Controls overlay (bottom-left) -->
    <GraphControls
      class="graph-explorer__controls"
      @fit="resetView"
      @relayout="runLayout"
      @reset="onReset"
    />

    <!-- Loading indicator -->
    <div v-if="graphStore.loading" class="graph-explorer__loading">
      <ProgressSpinner style="width: 32px; height: 32px" />
    </div>

    <!-- Empty state -->
    <div v-if="elements.length === 0 && !graphStore.loading" class="graph-explorer__empty">
      <i class="pi pi-sitemap text-4xl mb-2 block" style="color: var(--p-text-muted-color)"></i>
      <p class="text-color m-0">Search for an entity to start exploring</p>
      <p class="text-color-secondary text-sm m-0 mt-1">Double-click nodes to expand their neighborhood</p>
    </div>

    <!-- Detail side panel -->
    <div v-if="graphStore.selectedElement" class="graph-explorer__panel">
      <GraphDetailPanel
        :element="graphStore.selectedElement"
        :element-type="graphStore.selectedType!"
        @close="graphStore.clearSelection"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import ProgressSpinner from 'primevue/progressspinner'
import { useCytoscape } from '@/composables/useCytoscape'
import { useGraphStore } from '@/stores/graphStore'
import { transformToCytoscapeElements } from '@/utils/graphTransform'
import GraphSearchBar from './GraphSearchBar.vue'
import GraphDetailPanel from './GraphDetailPanel.vue'
import GraphControls from './GraphControls.vue'

const graphStore = useGraphStore()
const containerRef = ref<HTMLElement | null>(null)

const elements = computed(() =>
  transformToCytoscapeElements(
    graphStore.entities,
    graphStore.relationships,
    graphStore.documents,
    graphStore.entityDocumentLinks,
  )
)

const { focusEntity, resetView, runLayout } = useCytoscape({
  container: containerRef,
  elements,
  onEntitySelect: (id) => {
    if (id) graphStore.selectEntity(id)
    else graphStore.clearSelection()
  },
  onRelationshipSelect: (id) => graphStore.selectRelationship(id),
  onDocumentSelect: (id) => graphStore.selectDocument(id),
  onEntityExpand: (id) => graphStore.expandEntity(id),
})

function onSearchSelect(id: number, type: 'entity' | 'relationship' | 'document') {
  graphStore.handleSearchSelect(id, type, focusEntity)
}

function onReset() {
  graphStore.resetGraph()
}
</script>

<style scoped>
.graph-explorer {
  position: relative;
  width: 100%;
  height: calc(100vh - 4rem - 3rem);
  display: flex;
  flex-direction: column;
}

.graph-explorer__search {
  padding: 0.75rem;
  flex-shrink: 0;
}

.graph-explorer__canvas {
  flex: 1;
  min-height: 0;
}

.graph-explorer__controls {
  position: absolute;
  bottom: 1rem;
  left: 1rem;
  z-index: 10;
}

.graph-explorer__loading {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  z-index: 10;
}

.graph-explorer__empty {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  text-align: center;
  pointer-events: none;
}

.graph-explorer__panel {
  position: absolute;
  top: 0;
  right: 0;
  width: 320px;
  height: 100%;
  border-left: 1px solid #e2e8f0;
  background: #ffffff;
  overflow-y: auto;
  z-index: 15;
  box-shadow: -2px 0 8px rgba(0, 0, 0, 0.1);
}
</style>
