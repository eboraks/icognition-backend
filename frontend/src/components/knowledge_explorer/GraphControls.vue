<template>
  <div class="graph-controls flex gap-2">
    <Button icon="pi pi-search-plus" v-tooltip.top="'Zoom in (Ctrl +)'" text rounded size="small" @click="emit('zoomIn')" />
    <Button icon="pi pi-search-minus" v-tooltip.top="'Zoom out (Ctrl -)'" text rounded size="small" @click="emit('zoomOut')" />
    <Button icon="pi pi-arrows-alt" v-tooltip.top="'Fit to screen'" text rounded size="small" @click="emit('fit')" />
    <Button icon="pi pi-refresh" v-tooltip.top="'Re-layout'" text rounded size="small" @click="emit('relayout')" />
    <Button icon="pi pi-trash" v-tooltip.top="'Clear graph'" text rounded size="small" severity="danger" @click="emit('reset')" />
  </div>
</template>

<script setup lang="ts">
import Button from 'primevue/button'

const emit = defineEmits<{
  zoomIn: []
  zoomOut: []
  fit: []
  relayout: []
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
</style>
