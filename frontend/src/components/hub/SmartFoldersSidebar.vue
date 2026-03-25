<template>
  <div class="smart-folders-sidebar">
    <!-- Smart Folders Header -->
    <div class="sidebar-section">
      <h3 class="sidebar-title">
        <i class="pi pi-folder" />
        Smart Folders
      </h3>

      <!-- All Sources option -->
      <div
        class="source-item"
        :class="{ active: !activeSource }"
        @click="selectSource(null)"
      >
        <i class="pi pi-th-large source-icon" />
        <span class="source-name">All Sources</span>
        <span class="source-count">{{ totalCount }}</span>
      </div>

      <!-- Source list -->
      <div
        v-for="source in hubStore.sources"
        :key="source.site_name"
        class="source-item"
        :class="{ active: activeSource === source.site_name }"
        @click="selectSource(source.site_name)"
      >
        <img
          :src="faviconUrl(source.site_name)"
          :alt="source.site_name"
          class="source-favicon"
          @error="onFaviconError"
        />
        <span class="source-name">{{ source.site_name }}</span>
        <span class="source-count">{{ source.count }}</span>
      </div>
    </div>

    <!-- Related Bookmarks (when entity selected) -->
    <div v-if="hubStore.relatedBookmarks.length > 0" class="sidebar-section related-section">
      <h3 class="sidebar-title">
        <i class="pi pi-bookmark" />
        Related Bookmarks
      </h3>
      <div
        v-for="doc in hubStore.relatedBookmarks"
        :key="doc.id"
        class="bookmark-item"
        @click="onBookmarkClick(doc)"
      >
        <i class="pi pi-file" />
        <span class="bookmark-title">{{ doc.title }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useHubStore } from '@/stores/hubStore'
import type { DocumentSummary } from '@/types/graph'

const hubStore = useHubStore()

const emit = defineEmits<{
  'bookmark-select': [doc: DocumentSummary]
}>()

const activeSource = computed(() => hubStore.sourceFilter)

const totalCount = computed(() =>
  hubStore.sources.reduce((sum, s) => sum + s.count, 0)
)

function faviconUrl(domain: string): string {
  // Clean up domain for favicon lookup
  const clean = domain.replace(/^www\./, '')
  return `https://www.google.com/s2/favicons?domain=${clean}&sz=16`
}

function onFaviconError(event: Event) {
  const img = event.target as HTMLImageElement
  img.style.display = 'none'
}

function selectSource(source: string | null) {
  hubStore.filterBySource(source)
}

function onBookmarkClick(doc: DocumentSummary) {
  emit('bookmark-select', doc)
}
</script>

<style scoped>
.smart-folders-sidebar {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow-y: auto;
  padding: 1rem;
  background: var(--p-surface-card);
  border-right: 1px solid var(--p-content-border-color);
}

.sidebar-section {
  margin-bottom: 1.5rem;
}

.related-section {
  border-top: 1px solid var(--p-content-border-color);
  padding-top: 1rem;
}

.sidebar-title {
  font-size: 0.75rem;
  font-weight: 600;
  text-transform: uppercase;
  color: var(--p-text-muted-color);
  letter-spacing: 0.05em;
  margin-bottom: 0.75rem;
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.sidebar-title i {
  font-size: 0.8rem;
}

.source-item {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem 0.75rem;
  border-radius: 6px;
  cursor: pointer;
  transition: background-color 0.15s;
  font-size: 0.85rem;
  color: var(--p-text-color);
}

.source-item:hover {
  background: var(--p-surface-hover);
}

.source-item.active {
  background: var(--p-primary-50);
  color: var(--p-primary-color);
  font-weight: 500;
}

.source-favicon {
  width: 16px;
  height: 16px;
  border-radius: 2px;
  flex-shrink: 0;
}

.source-icon {
  font-size: 0.8rem;
  width: 16px;
  text-align: center;
  flex-shrink: 0;
  color: var(--p-text-muted-color);
}

.source-name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.source-count {
  font-size: 0.7rem;
  background: var(--p-surface-200);
  color: var(--p-text-muted-color);
  padding: 0.1rem 0.4rem;
  border-radius: 10px;
  flex-shrink: 0;
  min-width: 1.4rem;
  text-align: center;
}

.bookmark-item {
  display: flex;
  align-items: flex-start;
  gap: 0.5rem;
  padding: 0.4rem 0.75rem;
  border-radius: 6px;
  cursor: pointer;
  transition: background-color 0.15s;
  font-size: 0.8rem;
  color: var(--p-text-color);
}

.bookmark-item:hover {
  background: var(--p-surface-hover);
}

.bookmark-item i {
  font-size: 0.75rem;
  margin-top: 0.15rem;
  color: var(--p-text-muted-color);
  flex-shrink: 0;
}

.bookmark-title {
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}
</style>
