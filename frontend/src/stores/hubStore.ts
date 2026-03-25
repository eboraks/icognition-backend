import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { knowledgeService } from '@/services/knowledgeService'
import { useGraphStore } from './graphStore'
import { useChatStore } from './chat_store'
import type { DocumentSummary } from '@/types/graph'

export interface SourceFolder {
  site_name: string
  count: number
}

export const useHubStore = defineStore('hub', () => {
  const graphStore = useGraphStore()
  const chatStore = useChatStore()

  // Hub-specific state
  const selectedEntityId = ref<number | null>(null)
  const selectedEntityName = ref<string | null>(null)
  const selectedDocumentId = ref<number | null>(null)
  const chatPanelOpen = ref(false)
  const sourceFilter = ref<string | null>(null)
  const sources = ref<SourceFolder[]>([])
  const relatedBookmarks = ref<DocumentSummary[]>([])
  const initialLoading = ref(false)

  const hasSelection = computed(() => selectedEntityId.value !== null || selectedDocumentId.value !== null)

  async function loadDiscoveryGraph(source?: string) {
    initialLoading.value = true
    try {
      graphStore.resetGraph()
      const params: { source?: string; limit?: number } = { limit: 30 }
      if (source) params.source = source
      const resp = await knowledgeService.getDiscoveryGraph(params)
      const data = resp.data

      graphStore.entities.push(...data.entities)
      graphStore.relationships.push(...data.relationships)
      graphStore.documents.push(...(data.documents || []))
    } catch (err) {
      console.error('Failed to load discovery graph:', err)
    } finally {
      initialLoading.value = false
    }
  }

  async function loadSources() {
    try {
      const resp = await knowledgeService.getDocumentSources()
      sources.value = resp.data.sources
    } catch (err) {
      console.error('Failed to load sources:', err)
    }
  }

  async function selectEntity(entityId: number) {
    selectedEntityId.value = entityId
    selectedDocumentId.value = null

    // Select in graph store (highlights node, loads details)
    await graphStore.selectEntity(String(entityId))

    // Get entity name from graph store
    const entity = graphStore.selectedElement
    if (entity && 'name' in entity) {
      selectedEntityName.value = (entity as any).name
    }

    // Load related bookmarks
    try {
      const resp = await knowledgeService.getGraphEntityDocuments(entityId, 20)
      relatedBookmarks.value = resp.data
    } catch (err) {
      console.error('Failed to load related bookmarks:', err)
      relatedBookmarks.value = []
    }

    // Open chat panel
    chatPanelOpen.value = true

    // Ensure we have a chat session ready
    if (!chatStore.activeSession) {
      await chatStore.createSession('Knowledge Explorer', 'all_library')
    }
  }

  async function selectDocument(docId: number) {
    selectedDocumentId.value = docId
    selectedEntityId.value = null
    selectedEntityName.value = null

    await graphStore.selectDocument(`doc-${docId}`)
    chatPanelOpen.value = true

    // Ensure we have a chat session ready
    if (!chatStore.activeSession) {
      await chatStore.createSession('Knowledge Explorer', 'all_library')
    }
  }

  function clearSelection() {
    selectedEntityId.value = null
    selectedEntityName.value = null
    selectedDocumentId.value = null
    relatedBookmarks.value = []
    graphStore.clearSelection()
    // Keep chat panel open if user has an active session
  }

  async function filterBySource(siteName: string | null) {
    sourceFilter.value = siteName
    await loadDiscoveryGraph(siteName || undefined)
  }

  function closeChatPanel() {
    chatPanelOpen.value = false
  }

  function openChatPanel() {
    chatPanelOpen.value = true
  }

  return {
    // State
    selectedEntityId,
    selectedEntityName,
    selectedDocumentId,
    chatPanelOpen,
    sourceFilter,
    sources,
    relatedBookmarks,
    initialLoading,
    hasSelection,
    // Actions
    loadDiscoveryGraph,
    loadSources,
    selectEntity,
    selectDocument,
    clearSelection,
    filterBySource,
    closeChatPanel,
    openChatPanel,
  }
})
