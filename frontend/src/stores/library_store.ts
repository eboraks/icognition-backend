import { defineStore } from 'pinia';
import { ref, computed } from 'vue';
import { useDocumentStore } from './documents_store.js';
import { documentService, type EntityTreeNode, type EntityTreeResponse } from '@/services/DocumentService.js';
import type { TreeSelectionKeys } from 'primevue/tree';

interface DocRow {
  id: string | number;
  title: string;
  updatedAt: string;
  url?: string;
  sourceUrl?: string;
  sourceHost?: string;
  summary?: string;
  keyPoints?: string;
}

export const useLibraryStore = defineStore('library', () => {
  // State using Vue refs for reactivity
  const documents = ref<DocRow[]>([]);
  const loading = ref(false);
  const searchText = ref('');
  const entityTree = ref<EntityTreeNode[]>([]);
  const entityDocumentMap = ref<Map<number, Set<number>>>(new Map());
  const selectedEntityIds = ref<Set<number>>(new Set());

  // Computed: selectedDocumentIds - union of document_ids from selected entities
  const selectedDocumentIds = computed(() => {
    if (selectedEntityIds.value.size === 0) {
      return new Set<number>();
    }

    const docIdsSet = new Set<number>();
    selectedEntityIds.value.forEach(entityId => {
      const docIds = entityDocumentMap.value.get(entityId);
      if (docIds) {
        docIds.forEach(docId => docIdsSet.add(docId));
      }
    });
    return docIdsSet;
  });

  // Computed: filteredDocuments - applies search and entity filters
  const filteredDocuments = computed(() => {
    let filtered = documents.value;

    // Apply search filter first
    const q = (searchText.value || '').toLowerCase();
    if (q) {
      filtered = filtered.filter((d) =>
        d.title.toLowerCase().includes(q) || (d.summary || '').toLowerCase().includes(q)
      );
    }

    // Apply entity filter if any entities are selected
    if (selectedDocumentIds.value.size > 0) {
      filtered = filtered.filter((d) =>
        selectedDocumentIds.value.has(Number(d.id))
      );
    }

    return filtered;
  });

  // Actions
  async function fetchDocuments() {
    loading.value = true;
    try {
      // Get real documents from documentStore instead of using mock data
      const documentStore = useDocumentStore();

      // Transform documentStore documents to library store format
      documents.value = documentStore.docs.map(doc => ({
        id: doc.id || 0,
        title: doc.title || 'Untitled',
        updatedAt: doc.updatedAt ? doc.updatedAt.format('YYYY-MM-DD') : new Date().toISOString(),
        url: doc.url || '',
        sourceUrl: doc.url || '',
        sourceHost: doc.url ? new URL(doc.url).hostname : undefined,
        summary: doc.is_about,
        keyPoints: doc.aiMarkdownContent || "",
        type: 'web'
      }));

      console.log('Library store updated with real documents:', documents.value.length);
    } catch (error) {
      console.error('Error fetching documents for library store:', error);
      // Fallback to empty array if there's an error
      documents.value = [];
    } finally {
      loading.value = false;
    }
  }

  function setSearch(text: string) {
    searchText.value = text;
  }

  async function fetchEntityTree() {
    try {
      const response: EntityTreeResponse = await documentService.getEntityTree();
      entityTree.value = response.tree;
      buildEntityDocumentMap();
    } catch (error) {
      console.error('Error fetching entity tree:', error);
      entityTree.value = [];
      entityDocumentMap.value = new Map();
    }
  }

  function buildEntityDocumentMap() {
    const map = new Map<number, Set<number>>();

    const traverse = (nodes: EntityTreeNode[]) => {
      for (const node of nodes) {
        if (node.data && node.data.entity_id && node.data.document_ids) {
          map.set(node.data.entity_id, new Set(node.data.document_ids));
        }
        if (node.children) {
          traverse(node.children);
        }
      }
    };

    traverse(entityTree.value);
    entityDocumentMap.value = map;
    console.log('Built entity document map:', map.size, 'entities');
  }

  function updateSelectedEntities(selectedKeys: TreeSelectionKeys) {
    const newSelectedIds = new Set<number>();

    // Parse entity IDs from tree keys (format: "entity-{type}-{id}")
    Object.keys(selectedKeys || {}).forEach(key => {
      const checked = (selectedKeys as any)[key]?.checked;
      if (checked && key.startsWith('entity-')) {
        // Extract entity ID from key like "entity-location-1"
        const parts = key.split('-');
        if (parts.length >= 3 && parts[2]) {
          const entityId = parseInt(parts[2], 10);
          if (!isNaN(entityId)) {
            newSelectedIds.add(entityId);
          }
        }
      }
    });

    selectedEntityIds.value = newSelectedIds;
    console.log('Updated selected entities:', newSelectedIds.size, 'entities');
  }

  return {
    // State
    documents,
    loading,
    searchText,
    entityTree,
    entityDocumentMap,
    selectedEntityIds,
    // Computed
    selectedDocumentIds,
    filteredDocuments,
    // Actions
    fetchDocuments,
    setSearch,
    fetchEntityTree,
    buildEntityDocumentMap,
    updateSelectedEntities,
  };
});


