<template>
  <div class="graph-search-bar">
    <AutoComplete
      v-model="selected"
      :suggestions="groupedSuggestions"
      optionLabel="label"
      optionGroupLabel="groupLabel"
      optionGroupChildren="items"
      placeholder="Search entities, relationships, and documents..."
      class="w-full"
      :input-style="{ width: '100%' }"
      @complete="onComplete"
      @item-select="onItemSelect"
      :loading="searching"
      scrollHeight="400px"
    >
      <template #optiongroup="{ option }">
        <div class="flex align-items-center gap-2" style="padding: 0.25rem 0;">
          <i :class="groupIcon(option.groupType)" class="text-sm" style="color: #64748b;" />
          <span style="font-weight: 600; font-size: 0.8rem; color: #64748b; text-transform: uppercase;">
            {{ option.groupLabel }}
          </span>
        </div>
      </template>
      <template #option="{ option }">
        <div class="flex align-items-center gap-2 w-full">
          <span
            class="type-dot"
            :style="{ backgroundColor: dotColor(option) }"
          />
          <span class="flex-1" style="overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">
            {{ option.label }}
          </span>
          <span
            v-if="option.result_type !== 'document'"
            class="type-badge"
          >
            {{ option.type }}
          </span>
        </div>
      </template>
    </AutoComplete>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import AutoComplete from 'primevue/autocomplete'
import { knowledgeService } from '@/services/knowledgeService'
import { getNodeColor } from '@/utils/graphStyles'
import type { SearchHit } from '@/types/graph'

const emit = defineEmits<{
  select: [id: number, type: 'entity' | 'relationship' | 'document']
}>()

const selected = ref<SearchHit | string>('')
const results = ref<SearchHit[]>([])
const searching = ref(false)

const groupedSuggestions = computed(() => {
  const groups: { groupLabel: string; groupType: string; items: SearchHit[] }[] = []

  const entities = results.value.filter((r) => r.result_type === 'entity')
  const docs = results.value.filter((r) => r.result_type === 'document')
  const rels = results.value.filter((r) => r.result_type === 'relationship')

  if (entities.length > 0) {
    groups.push({ groupLabel: 'Entities', groupType: 'entity', items: entities })
  }
  if (docs.length > 0) {
    groups.push({ groupLabel: 'Documents', groupType: 'document', items: docs })
  }
  if (rels.length > 0) {
    groups.push({ groupLabel: 'Relationships', groupType: 'relationship', items: rels })
  }

  return groups
})

async function onComplete(event: { query: string }) {
  const q = event.query?.trim()
  if (!q || q.length < 2) {
    results.value = []
    return
  }
  searching.value = true
  try {
    const resp = await knowledgeService.graphSearch(q, { limit: 20 })
    results.value = resp.data.results
  } catch (e) {
    console.error('[GraphSearch] Search failed', e)
    results.value = []
  } finally {
    searching.value = false
  }
}

function onItemSelect(event: { value: SearchHit }) {
  const hit = event.value
  emit('select', hit.id, hit.result_type as 'entity' | 'relationship' | 'document')
  // Show the label in the input after selection
  selected.value = hit.label as any
}

function dotColor(hit: SearchHit): string {
  if (hit.result_type === 'document') return '#D97706'
  if (hit.result_type === 'relationship') return '#6B7280'
  return getNodeColor(hit.type)
}

function groupIcon(type: string): string {
  switch (type) {
    case 'entity': return 'pi pi-circle-fill'
    case 'document': return 'pi pi-file'
    case 'relationship': return 'pi pi-arrows-h'
    default: return 'pi pi-search'
  }
}
</script>

<style scoped>
.graph-search-bar {
  position: relative;
  z-index: 20;
}

.graph-search-bar :deep(.p-autocomplete) {
  width: 100% !important;
}

.graph-search-bar :deep(.p-autocomplete-input) {
  width: 100% !important;
}

.type-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
}

.type-badge {
  font-size: 0.7rem;
  padding: 0.1rem 0.4rem;
  border-radius: 4px;
  background: #f1f5f9;
  color: #64748b;
  flex-shrink: 0;
}
</style>
