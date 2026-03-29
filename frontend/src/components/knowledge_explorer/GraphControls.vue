<template>
  <div class="graph-controls flex gap-2 align-items-center">
    <Button icon="pi pi-search-plus" v-tooltip.top="'Zoom in (Ctrl +)'" text rounded size="small" @click="emit('zoomIn')" />
    <Button icon="pi pi-search-minus" v-tooltip.top="'Zoom out (Ctrl -)'" text rounded size="small" @click="emit('zoomOut')" />
    <Button icon="pi pi-arrows-alt" v-tooltip.top="'Fit to screen'" text rounded size="small" @click="emit('fit')" />
    <Button icon="pi pi-plus-circle" v-tooltip.top="'Expand selected node'" text rounded size="small" :disabled="!canExpand" @click="emit('expand')" />
    <select
      class="font-size-select"
      :value="fontSize"
      @change="emit('fontSizeChange', ($event.target as HTMLSelectElement).value)"
      title="Font size"
    >
      <option value="small">A-</option>
      <option value="medium">A</option>
      <option value="large">A+</option>
    </select>
    <Button icon="pi pi-refresh" v-tooltip.top="'Re-layout'" text rounded size="small" @click="emit('relayout')" />
    <Button icon="pi pi-filter" v-tooltip.top="'Filter graph by chat context'" text rounded size="small" :class="{ 'filter-active': chatFilterActive }" @click="emit('toggleChatFilter')" />
    <Button icon="pi pi-comments" v-tooltip.top="'Toggle chat'" text rounded size="small" @click="emit('toggleChat')" />
    <Button icon="pi pi-trash" v-tooltip.top="'Clear graph'" text rounded size="small" severity="danger" @click="emit('reset')" />
  </div>
</template>

<script setup lang="ts">
import Button from 'primevue/button'

defineProps<{
  canExpand?: boolean
  fontSize?: string
  chatFilterActive?: boolean
}>()

const emit = defineEmits<{
  zoomIn: []
  zoomOut: []
  fit: []
  expand: []
  fontSizeChange: [size: string]
  relayout: []
  toggleChatFilter: []
  toggleChat: []
  reset: []
}>()
</script>

<style scoped>
.graph-controls {
  background: var(--p-surface-card);
  border: 1px solid var(--p-content-border-color);
  border-radius: var(--p-border-radius);
  padding: 0.25rem;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
}

.font-size-select {
  appearance: none;
  background: none;
  border: 1px solid var(--p-content-border-color);
  border-radius: 4px;
  padding: 0.2rem 0.4rem;
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--p-text-color);
  cursor: pointer;
  text-align: center;
  min-width: 2rem;
}

.font-size-select:hover {
  background: var(--p-surface-hover);
}

.font-size-select:focus {
  outline: 1px solid var(--p-primary-color);
}

:deep(.filter-active) {
  color: var(--p-primary-color) !important;
  background: var(--p-primary-50, #eff6ff) !important;
}
</style>
