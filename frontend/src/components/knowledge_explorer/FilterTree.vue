<template>
  <div class="filter-tree-container">
    <IconField iconPosition="left" class="w-full mb-3 filter-search-input">
        <InputIcon class="pi pi-search" />
        <InputText
          v-model="searchQuery"
          placeholder="Search Topics"
          class="w-full"
        />
    </IconField>
    <ScrollPanel v-if="!loading" class="tree-content">
      <Tree
        :value="filteredNodes"
        v-model:expandedKeys="expandedKeys"
        v-model:selectionKeys="selectionKeys"
        selectionMode="checkbox"
        :showIcon="false"
        class="w-full"
        @node-select="onNodeSelect"
        @node-unselect="onNodeUnselect"
      >
        <template #default="slotProps">
          <div class="node-content">
            <span
              v-if="slotProps.node.data?.type === 'document' && slotProps.node.label && slotProps.node.label.length > 30"
              v-tooltip="slotProps.node.label"
              class="truncated-title"
            >
              {{ slotProps.node.label.substring(0, 30) }}…
            </span>
            <span v-else>
              {{ slotProps.node.label }}
            </span>
          </div>
        </template>
      </Tree>
    </ScrollPanel>
    <div v-else class="loading">
      <ProgressSpinner />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed, watch } from 'vue';
import Tree, { TreeSelectionKeys } from 'primevue/tree';
import InputText from 'primevue/inputtext';
import IconField from 'primevue/iconfield';
import InputIcon from 'primevue/inputicon';
import ProgressSpinner from 'primevue/progressspinner';
import ScrollPanel from 'primevue/scrollpanel';
import { knowledgeService, type FilterTreeData } from '@/services/knowledgeService';
import { useKnowledgeExplorerStore } from '@/stores/knowledgeExplorerStore';

const knowledgeStore = useKnowledgeExplorerStore();

const treeNodes = ref<FilterTreeData>([]);
const loading = ref(true);
const searchQuery = ref('');
const expandedKeys = ref<Record<string, boolean>>({});
const selectionKeys = ref<TreeSelectionKeys>({});

const collectChildNodes = (
  node: any
): Array<{ id: number; name: string | null; type: string | null }> => {
  if (!node?.children || !Array.isArray(node.children)) {
    return [];
  }

  const results: Array<{ id: number; name: string | null; type: string | null }> = [];

  node.children.forEach((child: any) => {
    const childData = child?.data ?? {};

    if (typeof childData.id === 'number') {
      results.push({
        id: childData.id,
        name: child?.label ?? null,
        type: childData.type ?? null,
      });
    }

    collectChildNodes(child).forEach((descendant) => results.push(descendant));
  });

  return results;
};

const filterTreeNodes = (nodes: FilterTreeData, query: string): FilterTreeData => {
  if (!query) return nodes;
  
  const lowerQuery = query.toLowerCase();
  const filtered: FilterTreeData = [];
  
  for (const node of nodes) {
    const matchesLabel = node.label?.toLowerCase().includes(lowerQuery);
    
    // Check if any children match
    let filteredChildren: FilterTreeData | undefined;
    if (node.children) {
      filteredChildren = filterTreeNodes(node.children, query);
    }
    
    // Include node if it matches or has matching children
    if (matchesLabel || (filteredChildren && filteredChildren.length > 0)) {
      filtered.push({
        ...node,
        children: filteredChildren
      });
    }
  }
  
  return filtered;
};

const filteredNodes = computed(() => {
  return filterTreeNodes(treeNodes.value, searchQuery.value);
});

// Helper function to find node by key in tree
const findNodeByKey = (nodes: any[], key: string): any => {
  for (const node of nodes) {
    if (node.key === key) {
      return node;
    }
    if (node.children) {
      const found = findNodeByKey(node.children, key);
      if (found) return found;
    }
  }
  return null;
};

// Watch for changes in selection keys (checkbox selections)
watch(selectionKeys, (newSelection, oldSelection) => {
  if (!newSelection) return;

  // Handle newly selected nodes
  Object.keys(newSelection).forEach(key => {
    const newValue = newSelection[key];
    const oldValue = oldSelection?.[key];
    
    // Check if this node was just selected (checked)
    const isNewlySelected = (
      (newValue === true && (!oldValue || oldValue !== true)) ||
      (typeof newValue === 'object' && newValue?.checked && (!oldValue || !oldValue?.checked))
    );
    
    if (isNewlySelected) {
      const node = findNodeByKey(treeNodes.value, key);
      if (node && node.data) {
        const payload = {
          id: typeof node.data.id === 'number' ? node.data.id : null,
          name: node.label ?? null,
          type: node.data.type ?? null,
          children: collectChildNodes(node),
        };
        knowledgeStore.setNodeSelected(key, payload);
      }
    }
  });

  // Handle newly unselected nodes (only if oldSelection exists)
  if (oldSelection) {
    Object.keys(oldSelection).forEach(key => {
      const newValue = newSelection[key];
      const oldValue = oldSelection[key];
      
      // Check if this node was just unselected (unchecked)
      const isNewlyUnselected = (
        (oldValue === true && (!newValue || newValue !== true)) ||
        (typeof oldValue === 'object' && oldValue?.checked && (!newValue || !newValue?.checked))
      );
      
      if (isNewlyUnselected) {
        knowledgeStore.setNodeUnselected(key);
      }
    });
  }
}, { deep: true });

const onNodeSelect = () => {
  // Node select events are handled by the checkbox watcher
};

const onNodeUnselect = () => {
  // Node unselect events are handled by the checkbox watcher
};

const loadFilterTree = async () => {
  try {
    loading.value = true;
    const response = await knowledgeService.getFilterTree();
    treeNodes.value = response.data;
    
    // Collapse all nodes by default
    expandedKeys.value = {};
  } catch (error) {
    console.error('Failed to load filter tree:', error);
  } finally {
    loading.value = false;
  }
};

onMounted(() => {
  loadFilterTree();
});
</script>

<style scoped>
.filter-tree-container {
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  min-height: 0;
}

.filter-search-input {
  flex-shrink: 0;
  position: relative;
  z-index: 1;
}

:deep(.p-tree) {
  border: none;
  background: transparent;
  color: var(--p-text-color);
}

:deep(.p-scrollpanel) {
  height: 100%;
}

:deep(.p-scrollpanel-wrapper) {
  height: 100%;
}

:deep(.p-tree-node-content) {
  color: var(--p-text-color);
  border-radius: 0.75rem;
  padding: 0.5rem 0.75rem;
  transition: background-color 0.2s ease, box-shadow 0.2s ease;
  gap: 0.5rem;
}

:deep(.p-iconfield .p-inputtext) {
  border-radius: 0.75rem;
}

.tree-content {
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

:deep(.p-tree-container) {
  gap: 0.25rem;
}

:deep(.p-treenode-selectable .p-tree-node-content:hover),
:deep(.p-tree-node-content.p-highlight) {
  background: var(--p-surface-hover);
}

:deep(.p-tree-toggler) {
  color: var(--p-text-muted-color);
}

:deep(.p-tree-toggler.p-tree-toggler-icon) {
  font-size: 0.85rem;
}

:deep(.p-checkbox .p-checkbox-box) {
  border-radius: 0.5rem;
}

.node-content {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  color: var(--p-text-color);
}

.node-content > span {
  flex: 0 1 auto;
}

.truncated-title {
  cursor: help;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 30ch;
  display: inline-block;
  vertical-align: bottom;
}

.loading {
  display: flex;
  justify-content: center;
  align-items: center;
  height: 200px;
}

</style>
