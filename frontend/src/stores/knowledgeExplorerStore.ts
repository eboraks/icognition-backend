import { defineStore } from 'pinia';
import { ref, computed } from 'vue';

interface SelectedNode {
  id: number | null;
  name: string | null;
  type: string | null;
  children: Array<{ id: number; name: string | null; type: string | null }>;
}

interface ChatTab {
  id: number;
  title: string;
  createdAt: number;
}

export const useKnowledgeExplorerStore = defineStore('knowledgeExplorer', () => {
  // Selected nodes from checkbox selections
  const selectedNodes = ref<Map<string, SelectedNode>>(new Map());
  
  // Currently active selections for chat context (arrays of IDs)
  const activeEntityId = ref<number[]>([]);
  const activeDocumentId = ref<number[]>([]);

  // Chat tabs state
  const chatTabs = ref<ChatTab[]>([
    {
      id: 1,
      title: 'Knowledge Exploration',
      createdAt: Date.now(),
    },
  ]);
  const activeChatTabId = ref<number>(1);
  const nextChatTabIndex = ref(2);

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

  const activeChatTab = computed(() => {
    return chatTabs.value.find((tab) => tab.id === activeChatTabId.value) ?? chatTabs.value[0] ?? null;
  });

  // Actions
  function setNodeSelected(nodeKey: string, node: SelectedNode) {
    selectedNodes.value.set(nodeKey, node);
    console.log('[KnowledgeExplorerStore] Node selected:', { nodeKey, node });
    
    // Update active selections arrays
    updateActiveSelections();
  }

  function setNodeUnselected(nodeKey: string) {
    selectedNodes.value.delete(nodeKey);
    console.log('[KnowledgeExplorerStore] Node unselected:', nodeKey);
    
    // Update active selections arrays
    updateActiveSelections();
  }

  function clearSelection() {
    selectedNodes.value.clear();
    activeEntityId.value = [];
    activeDocumentId.value = [];
    console.log('[KnowledgeExplorerStore] Selection cleared');
  }

  function updateActiveSelections() {
    // Collect all selected entity IDs (including from children)
    const entityIds: number[] = [];
    const documentIds: number[] = [];

    selectedNodes.value.forEach((node) => {
      if (node.type === 'entity' && node.id !== null) {
        entityIds.push(node.id);
      } else if (node.type === 'document' && node.id !== null) {
        documentIds.push(node.id);
      }

      // Also collect IDs from children
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

    // Remove duplicates and update arrays
    activeEntityId.value = [...new Set(entityIds)];
    activeDocumentId.value = [...new Set(documentIds)];
    
    console.log('[KnowledgeExplorerStore] Updated active selections:', {
      entityIds: activeEntityId.value,
      documentIds: activeDocumentId.value
    });
  }

  function ensureActiveChatTab() {
    if (!chatTabs.value.length) {
      addChatTab('New Chat');
      return;
    }
    const exists = chatTabs.value.some((tab) => tab.id === activeChatTabId.value);
    if (!exists) {
      activeChatTabId.value = chatTabs.value[chatTabs.value.length - 1].id;
    }
  }

  function addChatTab(title?: string) {
    const nextIndex = nextChatTabIndex.value++;
    const newTab: ChatTab = {
      id: Date.now() + nextIndex,
      title: title || `Chat ${nextIndex}`,
      createdAt: Date.now(),
    };
    chatTabs.value.push(newTab);
    activeChatTabId.value = newTab.id;
  }

  function setActiveChatTab(tabId: number) {
    if (chatTabs.value.some((tab) => tab.id === tabId)) {
      activeChatTabId.value = tabId;
    }
  }

  return {
    // State
    selectedNodes,
    activeEntityId,
    activeDocumentId,
    chatTabs,
    activeChatTabId,
    // Computed
    selectedNodeIds,
    selectedEntities,
    selectedDocuments,
    activeChatTab,
    // Actions
    setNodeSelected,
    setNodeUnselected,
    clearSelection,
    addChatTab,
    setActiveChatTab,
    ensureActiveChatTab,
  };
});

