<template>
  <div v-if="libraryStore.loading" class="flex flex-flow justify-content-center align-items-center h-full">
    <i class="pi pi-spin pi-spinner" style="font-size: 2rem; color: var(--p-primary-contrast-color);"></i>
  </div>
  <LibraryFilters v-else :nodes="libraryStore.entityTree" @update:filters="onCheckedIds" />
</template>

<script setup lang="ts">
import { onMounted } from 'vue';
import LibraryFilters from './LibraryFilters.vue';
import { useLibraryStore } from '@/stores/library_store';

const libraryStore = useLibraryStore();

const onCheckedIds = (checkedIds: any) => {
  libraryStore.updateSelectedEntities(checkedIds);
};

onMounted(async () => {
  if (libraryStore.entityTree.length === 0) {
    await libraryStore.fetchEntityTree();
  }
});
</script>

<style scoped>
</style>

