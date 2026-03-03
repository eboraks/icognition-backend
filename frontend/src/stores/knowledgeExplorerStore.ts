import { defineStore } from 'pinia';
import { ref, computed } from 'vue';

interface SelectedNode {
  id: number | null;
  name: string | null;
  type: string | null;
  children: Array<{ id: number; name: string | null; type: string | null }>;
}

export const useKnowledgeExplorerStore = defineStore('knowledgeExplorer', () => {
  // Selected nodes from checkbox selections
  const selectedNodes = ref<Map<string, SelectedNode>>(new Map());

  // Currently active selections for chat context (arrays of IDs)
  const activeEntityId = ref<number[]>([]);
  const activeDocumentId = ref<number[]>([]);

  // Computed: Get all selected node IDs
  const selectedNodeIds = computed(() => {
    const ids: number[] = [];
    selectedNodes.value.forEach((node) => {
      if (node.id !== null) {
        ids.push(node.id);
      }
      node.children.forEach((child) => {
        if (child.id !== null && !ids.includes(child.id)) {
          ids.push(child.id);
        }
      });
    });
    return ids;
  });

  // Computed: Get selected entities
  const selectedEntities = computed(() => {
    const entities: SelectedNode[] = [];
    selectedNodes.value.forEach((node) => {
      if (node.type === 'entity' && node.id !== null) {
        entities.push(node);
      }
    });
    return entities;
  });

  // Computed: Get selected documents
  const selectedDocuments = computed(() => {
    const documents: SelectedNode[] = [];
    selectedNodes.value.forEach((node) => {
      if (node.type === 'document' && node.id !== null) {
        documents.push(node);
      }
    });
    return documents;
  });

  // Actions
  function setNodeSelected(nodeKey: string, node: SelectedNode) {
    selectedNodes.value.set(nodeKey, node);
    console.log('[KnowledgeExplorerStore] Node selected:', { nodeKey, node });
    updateActiveSelections();
  }

  function setNodeUnselected(nodeKey: string) {
    selectedNodes.value.delete(nodeKey);
    console.log('[KnowledgeExplorerStore] Node unselected:', nodeKey);
    updateActiveSelections();
  }

  function clearSelection() {
    selectedNodes.value.clear();
    activeEntityId.value = [];
    activeDocumentId.value = [];
    console.log('[KnowledgeExplorerStore] Selection cleared');
  }

  function updateActiveSelections() {
    const entityIds: number[] = [];
    const documentIds: number[] = [];

    selectedNodes.value.forEach((node) => {
      if (node.type === 'entity' && node.id !== null) {
        entityIds.push(node.id);
      } else if (node.type === 'document' && node.id !== null) {
        documentIds.push(node.id);
      }

      node.children.forEach((child) => {
        if (child.id !== null) {
          if (child.type === 'entity') {
            entityIds.push(child.id);
          } else if (child.type === 'document') {
            documentIds.push(child.id);
          }
        }
      });
    });

    activeEntityId.value = [...new Set(entityIds)];
    activeDocumentId.value = [...new Set(documentIds)];

    console.log('[KnowledgeExplorerStore] Updated active selections:', {
      entityIds: activeEntityId.value,
      documentIds: activeDocumentId.value
    });
  }

  return {
    // State
    selectedNodes,
    activeEntityId,
    activeDocumentId,
    // Computed
    selectedNodeIds,
    selectedEntities,
    selectedDocuments,
    // Actions
    setNodeSelected,
    setNodeUnselected,
    clearSelection,
  };
});
