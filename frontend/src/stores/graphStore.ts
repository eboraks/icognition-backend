import { defineStore } from 'pinia'
import { ref } from 'vue'
import { knowledgeService } from '@/services/knowledgeService'
import type {
  EntitySummary, RelationshipSummary, DocumentSummary,
  EntityRead, RelationshipRead, DocumentRead,
} from '@/types/graph'

export const useGraphStore = defineStore('graph', () => {
  // Graph data
  const entities = ref<EntitySummary[]>([])
  const relationships = ref<RelationshipSummary[]>([])
  const documents = ref<DocumentSummary[]>([])
  const entityDocumentLinks = ref<{ entityId: number; documentId: number }[]>([])

  // Track which nodes have been expanded (their neighborhood loaded)
  const expandedNodeIds = ref<Set<string>>(new Set())

  // Selection state
  const selectedElement = ref<EntityRead | RelationshipRead | DocumentRead | null>(null)
  const selectedType = ref<'entity' | 'relationship' | 'document' | null>(null)
  const loading = ref(false)

  async function selectEntity(entityId: string) {
    if (!entityId) {
      clearSelection()
      return
    }
    selectedType.value = 'entity'
    const resp = await knowledgeService.getGraphEntity(Number(entityId))
    selectedElement.value = resp.data
  }

  async function selectRelationship(relId: string) {
    selectedType.value = 'relationship'
    const resp = await knowledgeService.getGraphRelationship(Number(relId))
    selectedElement.value = resp.data
  }

  async function selectDocument(docId: string) {
    // docId comes as "doc-123", strip prefix
    const numericId = Number(docId.replace('doc-', ''))
    selectedType.value = 'document'
    const resp = await knowledgeService.getGraphDocument(numericId)
    selectedElement.value = resp.data
  }

  function clearSelection() {
    selectedElement.value = null
    selectedType.value = null
  }

  /**
   * Focus the graph on a single entity: reset everything, load only 1-hop neighborhood.
   * Documents are omitted from the graph to keep it clean — they appear in the sidebar.
   */
  async function focusOnEntity(entityId: string) {
    loading.value = true
    try {
      // Fetch data FIRST, then replace arrays in one go.
      // This prevents race conditions with loadDiscoveryGraph.
      const resp = await knowledgeService.getNeighborhood(Number(entityId), { limit: 15 })
      const neighborhood = resp.data

      // Direct assignment — single reactive change per array, no intermediate empty state
      entities.value = neighborhood.entities
      relationships.value = neighborhood.relationships
      documents.value = []
      entityDocumentLinks.value = []
      expandedNodeIds.value = new Set([entityId])
      clearSelection()
    } finally {
      loading.value = false
    }
  }

  /**
   * Expand a node's neighborhood incrementally (adds to existing graph).
   */
  async function expandEntity(entityId: string) {
    loading.value = true
    try {
      const resp = await knowledgeService.getNeighborhood(Number(entityId))
      const neighborhood = resp.data

      const existingEntityIds = new Set(entities.value.map((e) => e.id))
      const existingRelIds = new Set(relationships.value.map((r) => r.id))
      const existingDocIds = new Set(documents.value.map((d) => d.id))

      entities.value.push(
        ...neighborhood.entities.filter((e) => !existingEntityIds.has(e.id))
      )
      relationships.value.push(
        ...neighborhood.relationships.filter((r) => !existingRelIds.has(r.id))
      )

      // Add new documents
      const newDocs = (neighborhood.documents || []).filter((d) => !existingDocIds.has(d.id))
      documents.value.push(...newDocs)

      // Build entity-document links from the neighborhood entities
      const existingLinkKeys = new Set(
        entityDocumentLinks.value.map((l) => `${l.entityId}-${l.documentId}`)
      )
      const allEntityIds = neighborhood.entities.map((e) => e.id)
      const allDocIds = (neighborhood.documents || []).map((d) => d.id)

      // Link center entity to all its documents
      for (const docId of allDocIds) {
        for (const eId of allEntityIds) {
          if (eId === Number(entityId)) {
            const key = `${eId}-${docId}`
            if (!existingLinkKeys.has(key)) {
              entityDocumentLinks.value.push({ entityId: eId, documentId: docId })
              existingLinkKeys.add(key)
            }
          }
        }
      }

      // Mark this node as expanded
      expandedNodeIds.value.add(entityId)
    } finally {
      loading.value = false
    }
  }

  async function handleSearchSelect(
    id: number,
    type: 'entity' | 'relationship' | 'document',
    focusFn: (id: string) => void,
  ) {
    if (type === 'entity') {
      await focusOnEntity(String(id))
      focusFn(String(id))
      await selectEntity(String(id))
    } else if (type === 'document') {
      // Load the document subgraph and show it
      loading.value = true
      try {
        const resp = await knowledgeService.getDocumentSubgraph(id)
        const subgraph = resp.data

        const existingEntityIds = new Set(entities.value.map((e) => e.id))
        const existingRelIds = new Set(relationships.value.map((r) => r.id))
        const existingDocIds = new Set(documents.value.map((d) => d.id))

        entities.value.push(
          ...subgraph.entities.filter((e) => !existingEntityIds.has(e.id))
        )
        relationships.value.push(
          ...subgraph.relationships.filter((r) => !existingRelIds.has(r.id))
        )
        const newDocs = (subgraph.documents || []).filter((d) => !existingDocIds.has(d.id))
        documents.value.push(...newDocs)

        // Build entity-document links
        const existingLinkKeys = new Set(
          entityDocumentLinks.value.map((l) => `${l.entityId}-${l.documentId}`)
        )
        for (const entity of subgraph.entities) {
          const key = `${entity.id}-${id}`
          if (!existingLinkKeys.has(key)) {
            entityDocumentLinks.value.push({ entityId: entity.id, documentId: id })
            existingLinkKeys.add(key)
          }
        }

        // Focus on the document node
        focusFn(`doc-${id}`)
        await selectDocument(`doc-${id}`)
      } finally {
        loading.value = false
      }
    } else {
      await selectRelationship(String(id))
    }
  }

  function resetGraph() {
    entities.value = []
    relationships.value = []
    documents.value = []
    entityDocumentLinks.value = []
    expandedNodeIds.value.clear()
    clearSelection()
  }

  function isNodeExpanded(nodeId: string) {
    return expandedNodeIds.value.has(nodeId)
  }

  return {
    entities, relationships, documents, entityDocumentLinks,
    expandedNodeIds,
    selectedElement, selectedType, loading,
    selectEntity, selectRelationship, selectDocument, clearSelection,
    focusOnEntity, expandEntity, handleSearchSelect, resetGraph, isNodeExpanded,
  }
})
