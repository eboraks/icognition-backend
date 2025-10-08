<template>
  <DataTable :value="documents"
             v-model:expandedRows="expandedRows"
             v-model:selection="selection"
             dataKey="id"
             responsiveLayout="scroll"
             class="w-full"
             :loading="loading">
    <Column expander style="width:3rem" />
    <Column field="title" header="Title">
      <template #body="{ data }">
        <div class="flex align-items-center">
          <i :class="getIconForType(data.type)" class="mr-2 text-600"></i>
          <a class="cursor-pointer text-primary" @click="$emit('open', data)">{{ data.title }}</a>
        </div>
      </template>
    </Column>
    <Column field="updatedAt" header="Last updated" />
    <Column header="Source">
      <template #body="{ data }">
        <a v-if="data.sourceUrl" :href="data.sourceUrl" target="_blank" rel="noopener noreferrer" class="text-primary">{{ data.sourceHost }}</a>
        <span v-else class="text-600">-</span>
      </template>
    </Column>
    <Column selectionMode="multiple" style="width:3rem" />

    <template #expansion="{ data }">
      <div class="p-4 bg-white border-round">
        <div class="text-sm text-600 mb-2 font-semibold">Summary</div>
        <div class="mb-4 text-700">{{ data.summary || 'No summary available.' }}</div>
        <div class="text-sm text-600 mb-2 font-semibold">Key Points</div>
        <ul class="pl-3 text-700">
          <li v-for="(kp, i) in data.keyPoints" :key="i" class="mb-1">{{ kp }}</li>
          <li v-if="!data.keyPoints || data.keyPoints.length === 0" class="text-600">No key points available.</li>
        </ul>
      </div>
    </template>
  </DataTable>
</template>

<script setup lang="ts">
import { ref, watchEffect } from 'vue';
import DataTable from 'primevue/datatable';
import Column from 'primevue/column';

interface DocRow {
  id: string | number;
  title: string;
  updatedAt: string;
  sourceUrl?: string;
  sourceHost?: string;
  summary?: string;
  keyPoints?: string[];
  type?: string;
}

const props = defineProps<{ documents: DocRow[]; expandAllKey?: number; loading?: boolean }>();
const emit = defineEmits(['open']);

const expandedRows = ref<any>({});
const selection = ref<DocRow[]>([]);

const getIconForType = (type?: string) => {
  switch (type) {
    case 'web':
      return 'pi pi-globe';
    case 'pdf':
      return 'pi pi-file-pdf';
    case 'document':
      return 'pi pi-file';
    default:
      return 'pi pi-file';
  }
};

watchEffect(() => {
  // Re-compute when expandAllKey changes to support external expand/collapse toggles
  // Parent can toggle by changing the key and setting expandedRows appropriately
});

// Expose methods for parent to control expansion
defineExpose({ expandedRows, selection });
</script>

<style scoped>
</style>


