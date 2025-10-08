<template>
  <div class="flex flex-column gap-2 w-full h-full">
    <IconField iconPosition="left" class="w-full mb-2">
      <InputIcon class="pi pi-search" />
      <InputText v-model="searchText" placeholder="Search Topics" class="w-full" />
    </IconField>
    <div class="flex-1 overflow-auto">
      <Tree :value="filteredNodes"
            selectionMode="checkbox"
            v-model:selectionKeys="selectedKeys"
            class="w-full" />
    </div>
    <div class="flex align-items-center justify-content-between mt-2 pt-2 border-top-1 border-white-alpha-20" v-if="selectedLabels.length > 0">
      <div class="flex gap-1 flex-wrap flex-1">
        <span class="text-white text-xs">{{ selectedLabels.length }} Selected Filters</span>
      </div>
      <Button label="Clear" text size="small" @click="clear" class="text-white" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import Tree, { TreeSelectionKeys } from 'primevue/tree';
import Tag from 'primevue/tag';
import Button from 'primevue/button';
import InputText from 'primevue/inputtext';
import IconField from 'primevue/iconfield';
import InputIcon from 'primevue/inputicon';

interface TreeNode {
  key: string;
  label: string;
  children?: TreeNode[];
}

const props = defineProps<{ nodes: TreeNode[] }>();
const emit = defineEmits(['update:filters']);

const selectedKeys = ref<TreeSelectionKeys>({});
const searchText = ref('');

// Sample tree data if no nodes provided
const sampleNodes: TreeNode[] = [
  {
    key: 'seinfeld',
    label: "Jerry Seinfeld and Larry David's Seinfeld",
    children: [
      { key: 'jerry', label: 'Jerry Seinfeld (person)' },
      { key: 'larry', label: 'Larry David (person)' },
      { key: 'show', label: 'Seinfeld (concept)' }
    ]
  },
  {
    key: 'ai',
    label: 'Optimizing Vector Databases for Retrieval - Augmented Generation (RAG) in AI',
    children: [
      { key: 'vector', label: 'Vector Databases' },
      { key: 'rag', label: 'RAG Systems' },
      { key: 'ai', label: 'Artificial Intelligence' }
    ]
  },
  {
    key: 'knowledge',
    label: 'Knowledge Graph Construction and Retrieval with Neo4j and Longchain',
    children: [
      { key: 'neo4j', label: 'Neo4j' },
      { key: 'longchain', label: 'Longchain' },
      { key: 'graphs', label: 'Knowledge Graphs' }
    ]
  },
  {
    key: 'meetings',
    label: 'Effective Virtual Meeting Management',
    children: [
      { key: 'virtual', label: 'Virtual Meetings' },
      { key: 'management', label: 'Meeting Management' }
    ]
  },
  {
    key: 'nba',
    label: 'NBA Teams',
    children: [
      { key: 'lakers', label: 'Los Angeles Lakers' },
      { key: 'warriors', label: 'Golden State Warriors' }
    ]
  }
];

const displayNodes = computed(() => props.nodes && props.nodes.length > 0 ? props.nodes : sampleNodes);

const filteredNodes = computed(() => {
  if (!searchText.value) return displayNodes.value;
  
  const filterNode = (node: TreeNode): TreeNode | null => {
    const matchesSearch = node.label.toLowerCase().includes(searchText.value.toLowerCase());
    const filteredChildren = node.children?.map(filterNode).filter(Boolean) as TreeNode[] || [];
    
    if (matchesSearch || filteredChildren.length > 0) {
      return {
        ...node,
        children: filteredChildren.length > 0 ? filteredChildren : node.children
      };
    }
    return null;
  };
  
  return displayNodes.value.map(filterNode).filter(Boolean) as TreeNode[];
});

const keyToLabel = (node: TreeNode, map: Record<string, string>) => {
  map[node.key] = node.label;
  (node.children || []).forEach((c) => keyToLabel(c, map));
  return map;
};

const labelsMap = computed(() => {
  const m: Record<string, string> = {};
  displayNodes.value.forEach((n) => keyToLabel(n, m));
  return m;
});

const selectedLabels = computed(() =>
  Object.keys(selectedKeys.value || {})
    .filter((k) => (selectedKeys.value as any)[k]?.checked)
    .map((k) => labelsMap.value[k])
);

watch(selectedKeys, () => {
  emit('update:filters', selectedKeys.value);
});

const clear = () => {
  selectedKeys.value = {};
  emit('update:filters', selectedKeys.value);
};
</script>

<style scoped>
</style>

