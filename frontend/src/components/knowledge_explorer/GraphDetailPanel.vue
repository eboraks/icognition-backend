<template>
  <div class="graph-detail-panel">
    <div class="flex align-items-center justify-content-between mb-3">
      <span class="font-semibold text-lg text-color">Details</span>
      <Button icon="pi pi-times" text rounded size="small" @click="emit('close')" />
    </div>

    <!-- Entity detail -->
    <template v-if="elementType === 'entity' && entityData">
      <div class="flex align-items-center gap-2 mb-3">
        <i class="pi pi-circle-fill" :style="{ color: getNodeColor(entityData.type) }" />
        <span class="font-semibold text-color">{{ entityData.name }}</span>
        <Tag :value="entityData.type" severity="secondary" class="text-xs" />
      </div>
      <p v-if="entityData.description" class="text-color-secondary text-sm mb-3">{{ entityData.description }}</p>

      <!-- Source Documents -->
      <div v-if="entityData.documents && entityData.documents.length > 0" class="mb-3">
        <p class="section-label">
          Source Documents ({{ entityData.document_count }})
        </p>
        <ul class="list-none p-0 m-0 flex flex-column gap-1">
          <li v-for="doc in entityData.documents" :key="doc.id" class="text-sm text-color">
            <i class="pi pi-file text-xs mr-1" />
            {{ doc.title }}
          </li>
        </ul>
      </div>
    </template>

    <!-- Relationship detail -->
    <template v-if="elementType === 'relationship' && relationshipData">
      <div class="mb-3">
        <p class="section-label">Relationship</p>
        <div class="flex align-items-center gap-2 flex-wrap text-sm">
          <Tag :value="relationshipData.from_entity.name" severity="info" />
          <span class="font-medium text-primary">{{ relationshipData.relationship_type.replace(/_/g, ' ') }}</span>
          <Tag :value="relationshipData.to_entity.name" severity="info" />
        </div>
      </div>

      <div v-if="relationshipData.source_document" class="mb-3">
        <p class="section-label">Source Document</p>
        <p class="text-sm text-color">
          <i class="pi pi-file text-xs mr-1" />
          {{ relationshipData.source_document.title }}
        </p>
      </div>
    </template>

    <!-- Document detail -->
    <template v-if="elementType === 'document' && documentData">
      <div class="flex align-items-center gap-2 mb-3">
        <i class="pi pi-file" :style="{ color: getNodeColor('document') }" />
        <span class="font-semibold text-color">{{ documentData.title }}</span>
      </div>

      <a
        v-if="documentData.url"
        :href="documentData.url"
        target="_blank"
        rel="noopener"
        class="text-sm text-primary mb-3 block"
      >
        <i class="pi pi-external-link text-xs mr-1" />
        Open original
      </a>

      <!-- Linked entities -->
      <div v-if="documentData.entities && documentData.entities.length > 0" class="mb-3">
        <p class="section-label">
          Entities ({{ documentData.entities.length }})
        </p>
        <div class="flex flex-wrap gap-1">
          <Tag
            v-for="ent in documentData.entities"
            :key="ent.id"
            :value="ent.name"
            severity="secondary"
            class="text-xs"
          />
        </div>
      </div>

      <!-- Markdown content -->
      <div v-if="documentData.ai_markdown_content" class="document-content">
        <p class="section-label">Content</p>
        <div class="markdown-body text-sm text-color" v-html="renderedMarkdown"></div>
      </div>
      <p v-else class="text-color-secondary text-sm">No content available for this document.</p>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { marked } from 'marked'
import Button from 'primevue/button'
import Tag from 'primevue/tag'
import type { EntityRead, RelationshipRead, DocumentRead } from '@/types/graph'
import { getNodeColor } from '@/utils/graphStyles'

const props = defineProps<{
  element: EntityRead | RelationshipRead | DocumentRead
  elementType: 'entity' | 'relationship' | 'document'
}>()

const emit = defineEmits<{ close: [] }>()

const entityData = computed(() =>
  props.elementType === 'entity' ? (props.element as EntityRead) : null
)
const relationshipData = computed(() =>
  props.elementType === 'relationship' ? (props.element as RelationshipRead) : null
)
const documentData = computed(() =>
  props.elementType === 'document' ? (props.element as DocumentRead) : null
)

const renderedMarkdown = computed(() => {
  if (!documentData.value?.ai_markdown_content) return ''
  return marked.parse(documentData.value.ai_markdown_content) as string
})
</script>

<style scoped>
.graph-detail-panel {
  padding: 1rem;
  height: 100%;
  overflow-y: auto;
  color: var(--p-text-color);
}

.section-label {
  font-size: 0.75rem;
  font-weight: 600;
  text-transform: uppercase;
  color: var(--p-text-muted-color);
  margin-bottom: 0.5rem;
}

.document-content {
  border-top: 1px solid var(--p-content-border-color);
  padding-top: 0.75rem;
}

.markdown-body {
  line-height: 1.6;
}

.markdown-body :deep(h1),
.markdown-body :deep(h2),
.markdown-body :deep(h3) {
  font-size: 0.95rem;
  font-weight: 600;
  margin: 0.75rem 0 0.25rem;
  color: var(--p-text-color);
}

.markdown-body :deep(p) {
  margin: 0.25rem 0;
}

.markdown-body :deep(ul),
.markdown-body :deep(ol) {
  padding-left: 1.25rem;
  margin: 0.25rem 0;
}
</style>
