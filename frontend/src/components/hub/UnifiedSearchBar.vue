<template>
  <div class="unified-search-bar">
    <div class="search-wrapper">
      <i class="pi pi-search search-icon" />
      <AutoComplete
        v-model="selected"
        :suggestions="groupedSuggestions"
        optionLabel="label"
        optionGroupLabel="groupLabel"
        optionGroupChildren="items"
        placeholder="Search entities, topics, documents..."
        class="w-full"
        :input-style="{ width: '100%', paddingLeft: '2.5rem' }"
        @complete="onComplete"
        @item-select="onItemSelect"
        @keydown.enter="onEnterKey"
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
            <span class="type-dot" :style="{ backgroundColor: dotColor(option) }" />
            <span class="flex-1" style="overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">
              {{ option.label }}
            </span>
            <span v-if="option.result_type !== 'document'" class="type-badge">
              {{ option.type }}
            </span>
          </div>
        </template>
      </AutoComplete>
      <!-- Hint: nudge user to chat panel when typing a question -->
      <div v-if="chatHint" class="chat-hint">
        <i class="pi pi-comments" />
        <span>Press <strong>Enter</strong> to ask this in the chat, or select a result above</span>
      </div>
    </div>
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
  chat: [query: string]
}>()

const selected = ref<SearchHit | string>('')
const results = ref<SearchHit[]>([])
const searching = ref(false)
let itemJustSelected = false

const chatHint = computed(() => {
  const q = typeof selected.value === 'string' ? selected.value.trim().toLowerCase() : ''
  if (q.length < 5) return false
  return /^(what|who|how|why|when|where|which|is |are |do |does |can |could |tell |explain |describe )/.test(q) || q.includes('?')
})

const groupedSuggestions = computed(() => {
  const groups: { groupLabel: string; groupType: string; items: SearchHit[] }[] = []
  const entities = results.value.filter((r) => r.result_type === 'entity')
  const docs = results.value.filter((r) => r.result_type === 'document')
  const rels = results.value.filter((r) => r.result_type === 'relationship')
  if (entities.length > 0) groups.push({ groupLabel: 'Entities', groupType: 'entity', items: entities })
  if (docs.length > 0) groups.push({ groupLabel: 'Documents', groupType: 'document', items: docs })
  if (rels.length > 0) groups.push({ groupLabel: 'Relationships', groupType: 'relationship', items: rels })
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
    console.error('[UnifiedSearch] Search failed', e)
    results.value = []
  } finally {
    searching.value = false
  }
}

function onItemSelect(event: { value: SearchHit }) {
  itemJustSelected = true
  const hit = event.value
  emit('select', hit.id, hit.result_type as 'entity' | 'relationship' | 'document')
  selected.value = hit.label as any
}

function onEnterKey(event: KeyboardEvent) {
  // If an item was just selected from dropdown, skip chat
  if (itemJustSelected) {
    itemJustSelected = false
    return
  }
  const query = typeof selected.value === 'string' ? selected.value.trim() : ''
  if (query) {
    emit('chat', query)
  }
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
.unified-search-bar {
  position: relative;
  z-index: 20;
  padding: 0.75rem 1rem;
}

.search-wrapper {
  position: relative;
  max-width: 600px;
  margin: 0 auto;
}

.search-icon {
  position: absolute;
  left: 0.85rem;
  top: 50%;
  transform: translateY(-50%);
  z-index: 1;
  color: var(--p-text-muted-color);
  font-size: 0.9rem;
  pointer-events: none;
}

.unified-search-bar :deep(.p-autocomplete) {
  width: 100% !important;
}

.unified-search-bar :deep(.p-autocomplete-input) {
  width: 100% !important;
  border-radius: 12px !important;
  padding: 0.75rem 1rem 0.75rem 2.5rem !important;
  font-size: 0.95rem;
  background: var(--p-surface-card);
  border: 1px solid var(--p-content-border-color);
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.06);
  transition: box-shadow 0.2s, border-color 0.2s;
}

.unified-search-bar :deep(.p-autocomplete-input:focus) {
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.1);
  border-color: var(--p-primary-color);
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

.chat-hint {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-top: 0.4rem;
  padding: 0.4rem 0.75rem;
  font-size: 0.8rem;
  color: #3B82F6;
  background: #EFF6FF;
  border-radius: 8px;
}

.chat-hint i {
  font-size: 0.85rem;
}
</style>
