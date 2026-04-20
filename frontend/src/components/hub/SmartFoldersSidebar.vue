<template>
  <div class="smart-folders-sidebar">
    <!-- Themes -->
    <div v-if="hubStore.themes.length > 0" class="sidebar-section">
      <h3 class="sidebar-title clickable" @click="themesCollapsed = !themesCollapsed">
        <i class="pi" :class="themesCollapsed ? 'pi-chevron-right' : 'pi-chevron-down'" />
        <i class="pi pi-tags" />
        Themes
        <button
          class="recluster-btn"
          title="Re-organize themes"
          @click.stop="hubStore.reclusterThemes()"
        >
          <i class="pi pi-refresh" />
        </button>
      </h3>

      <div v-show="!themesCollapsed">
        <!-- All Themes option -->
        <div
          class="source-item"
          :class="{ active: !hubStore.themeFilter && !activeSource }"
          @click="selectTheme(null)"
        >
          <i class="pi pi-th-large source-icon" />
          <span class="source-name">All Themes</span>
        </div>

        <!-- Theme list -->
        <div
          v-for="theme in hubStore.themes"
          :key="theme.id"
          class="source-item"
          :class="{ active: hubStore.themeFilter === theme.id }"
          @click="selectTheme(theme.id)"
        >
          <span
            class="theme-dot"
            :style="{ background: theme.color || '#6B7280' }"
          />
          <span class="source-name">{{ theme.label }}</span>
          <span class="source-count">{{ theme.doc_count }}</span>
        </div>
      </div>
    </div>

    <!-- Research Sessions -->
    <div v-if="hubStore.researchSessions.length > 0" class="sidebar-section">
      <h3 class="sidebar-title clickable" @click="researchCollapsed = !researchCollapsed">
        <i class="pi" :class="researchCollapsed ? 'pi-chevron-right' : 'pi-chevron-down'" />
        <i class="pi pi-search" />
        Research
      </h3>

      <div v-show="!researchCollapsed">
        <!-- All Research option -->
        <div
          class="source-item"
          :class="{ active: !hubStore.researchFilter && !activeSource && !hubStore.themeFilter }"
          @click="selectResearch(null)"
        >
          <i class="pi pi-th-large source-icon" />
          <span class="source-name">All Research</span>
        </div>

        <!-- Research session list -->
        <div
          v-for="rs in hubStore.researchSessions"
          :key="rs.id"
          class="source-item research-item"
          :class="{ active: hubStore.researchFilter === rs.id }"
          :title="rs.brief"
          @click="selectResearch(rs.id)"
        >
          <i
            class="pi source-icon"
            :class="statusIcon(rs.status)"
          />
          <span class="source-name">{{ briefLabel(rs.brief) }}</span>
          <span class="source-count">{{ rs.doc_count }}</span>
          <button
            class="research-delete-btn"
            title="Delete research"
            @click.stop="deleteResearch(rs.id)"
          >
            <i class="pi pi-trash" />
          </button>
        </div>
      </div>
    </div>

    <!-- Smart Folders -->
    <div class="sidebar-section">
      <h3 class="sidebar-title clickable" @click="sourcesCollapsed = !sourcesCollapsed">
        <i class="pi" :class="sourcesCollapsed ? 'pi-chevron-right' : 'pi-chevron-down'" />
        <i class="pi pi-folder" />
        Smart Folders
      </h3>

      <div v-show="!sourcesCollapsed">
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
        @contextmenu.prevent="onBookmarkContextMenu($event, doc)"
      >
        <i class="pi pi-file" />
        <span class="bookmark-title">{{ doc.title }}</span>
      </div>
    </div>

    <!-- Context menu for reassigning bookmarks to themes -->
    <ContextMenu ref="contextMenuRef" :model="contextMenuItems" />
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import ContextMenu from 'primevue/contextmenu'
import { useHubStore } from '@/stores/hubStore'
import type { DocumentSummary } from '@/types/graph'

const hubStore = useHubStore()

const emit = defineEmits<{
  'bookmark-select': [doc: DocumentSummary]
}>()

// Collapsible section state
const sourcesCollapsed = ref(false)
const themesCollapsed = ref(false)
const researchCollapsed = ref(false)

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

function selectTheme(themeId: number | null) {
  hubStore.filterByTheme(themeId)
}

function selectResearch(researchId: number | null) {
  hubStore.filterByResearch(researchId)
}

async function deleteResearch(researchId: number) {
  await hubStore.deleteResearchSession(researchId)
}

function briefLabel(brief: string): string {
  if (!brief) return 'Untitled research'
  const trimmed = brief.trim()
  return trimmed.length > 40 ? trimmed.slice(0, 40) + '…' : trimmed
}

function statusIcon(status: string): string {
  if (status === 'running') return 'pi-spin pi-spinner'
  if (status === 'failed') return 'pi-exclamation-triangle'
  return 'pi-search'
}

function onBookmarkClick(doc: DocumentSummary) {
  emit('bookmark-select', doc)
}

// Context menu for reassigning bookmarks to themes
const contextMenuRef = ref()
const contextMenuDocId = ref<number | null>(null)

const contextMenuItems = computed(() => {
  if (!hubStore.themes.length || !hubStore.themeFilter) return []
  return [
    {
      label: 'Move to theme...',
      icon: 'pi pi-arrow-right',
      items: hubStore.themes
        .filter((t) => t.id !== hubStore.themeFilter)
        .map((t) => ({
          label: t.label,
          icon: 'pi pi-tag',
          command: () => {
            if (contextMenuDocId.value && hubStore.themeFilter) {
              hubStore.reassignDocument(contextMenuDocId.value, hubStore.themeFilter, t.id)
            }
          },
        })),
    },
  ]
})

function onBookmarkContextMenu(event: MouseEvent, doc: DocumentSummary) {
  if (!hubStore.themes.length || !hubStore.themeFilter) return
  contextMenuDocId.value = doc.id
  contextMenuRef.value?.show(event)
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
  font-size: var(--app-font-size, 12px);
}

.sidebar-section {
  margin-bottom: 1.5rem;
}

.related-section {
  border-top: 1px solid var(--p-content-border-color);
  padding-top: 1rem;
}

.sidebar-title {
  font-size: 0.9em;
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
  font-size: 0.95em;
}

.sidebar-title.clickable {
  cursor: pointer;
  user-select: none;
  padding: 0.25rem 0;
  border-radius: 4px;
  transition: color 0.15s;
}

.sidebar-title.clickable:hover {
  color: var(--p-text-color);
}

.source-item {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem 0.75rem;
  border-radius: 6px;
  cursor: pointer;
  transition: background-color 0.15s;
  font-size: 1em;
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
  font-size: 0.95em;
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
  font-size: 0.85em;
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
  font-size: 0.95em;
  color: var(--p-text-color);
}

.bookmark-item:hover {
  background: var(--p-surface-hover);
}

.bookmark-item i {
  font-size: 0.9em;
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

.theme-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
}

.recluster-btn {
  margin-left: auto;
  background: none;
  border: none;
  cursor: pointer;
  padding: 0.15rem 0.3rem;
  border-radius: 4px;
  color: var(--p-text-muted-color);
  font-size: 0.85em;
  transition: background-color 0.15s, color 0.15s;
}

.recluster-btn:hover {
  background: var(--p-surface-hover);
  color: var(--p-text-color);
}

.research-item .source-name {
  font-size: 0.95em;
  line-height: 1.2;
}

.research-delete-btn {
  opacity: 0;
  background: none;
  border: none;
  cursor: pointer;
  padding: 0.2rem 0.35rem;
  border-radius: 3px;
  color: var(--p-text-muted-color);
  font-size: 0.85em;
  flex-shrink: 0;
  transition: opacity 0.15s, background 0.15s, color 0.15s;
}

.research-item:hover .research-delete-btn {
  opacity: 1;
}

.research-delete-btn:hover {
  background: var(--p-red-50);
  color: var(--p-red-500);
}
</style>
