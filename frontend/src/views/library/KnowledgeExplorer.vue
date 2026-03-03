<template>
  <div class="knowledge-explorer-view flex flex-column h-full p-3 gap-3">

    <!-- Entity detail panel (single entity selected) -->
    <div v-if="singleEntity" class="entity-detail surface-card border-round border-1 border-200 p-4">
      <div class="flex align-items-center gap-2 mb-3">
        <i class="pi pi-tag text-primary text-xl"></i>
        <span class="font-semibold text-lg">{{ singleEntity.name }}</span>
        <Tag :value="singleEntity.type" severity="secondary" class="text-xs" />
      </div>
      <p v-if="singleEntity.description" class="text-600 text-sm mb-3">{{ singleEntity.description }}</p>

      <!-- Relationships -->
      <div v-if="loadingRels" class="flex align-items-center gap-2 text-500 text-sm">
        <i class="pi pi-spin pi-spinner"></i> Loading relationships…
      </div>
      <div v-else-if="relationships.length > 0">
        <p class="text-xs font-semibold text-500 uppercase mb-2">Relationships</p>
        <ul class="list-none p-0 m-0 flex flex-column gap-2">
          <li
            v-for="(rel, i) in relationships"
            :key="i"
            class="flex align-items-center gap-2 text-sm flex-wrap"
          >
            <span class="font-medium">{{ rel.from_entity.name }}</span>
            <Tag :value="rel.relationship_type.replace(/_/g, ' ')" severity="info" class="text-xs" />
            <span class="font-medium">{{ rel.to_entity.name }}</span>
          </li>
        </ul>
      </div>
      <p v-else class="text-500 text-sm">No relationships found for this entity.</p>

      <Button
        label="Explore in Chat"
        icon="pi pi-comments"
        class="mt-4 w-full"
        @click="exploreInChat"
        :loading="creating"
      />
    </div>

    <!-- Multi-selection summary -->
    <div v-else-if="hasSelection" class="selection-summary text-center surface-card border-round border-1 border-200 p-4">
      <i class="pi pi-tags text-4xl text-primary mb-3 block"></i>
      <p class="text-lg font-semibold mb-1">{{ selectionLabel }}</p>
      <p class="text-600 text-sm mb-4">{{ selectionSubtitle }}</p>
      <Button
        label="Explore in Chat"
        icon="pi pi-comments"
        @click="exploreInChat"
        :loading="creating"
      />
    </div>

    <!-- Empty state -->
    <div v-else class="empty-state text-center p-4 flex flex-column align-items-center justify-content-center flex-1">
      <i class="pi pi-sitemap text-4xl text-400 mb-3 block"></i>
      <p class="text-lg text-600 mb-1">Select topics to explore</p>
      <p class="text-500 text-sm">Use the sidebar to browse and select entities or documents</p>
    </div>

  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { useRouter } from 'vue-router';
import Button from 'primevue/button';
import Tag from 'primevue/tag';
import { useKnowledgeExplorerStore } from '@/stores/knowledgeExplorerStore';
import { useChatStore } from '@/stores/chat_store';
import { knowledgeService, type EntityRelationshipItem } from '@/services/knowledgeService';

const router = useRouter();
const knowledgeStore = useKnowledgeExplorerStore();
const chatStore = useChatStore();
const creating = ref(false);

const singleEntity = ref<{ id: number; name: string; type: string; description?: string } | null>(null);
const relationships = ref<EntityRelationshipItem[]>([]);
const loadingRels = ref(false);

const hasSelection = computed(() =>
  knowledgeStore.activeEntityId.length > 0 || knowledgeStore.activeDocumentId.length > 0
);

const selectionLabel = computed(() => {
  const entityCount = knowledgeStore.activeEntityId.length;
  const docCount = knowledgeStore.activeDocumentId.length;
  const parts: string[] = [];
  if (entityCount > 0) parts.push(`${entityCount} ${entityCount === 1 ? 'entity' : 'entities'}`);
  if (docCount > 0) parts.push(`${docCount} ${docCount === 1 ? 'document' : 'documents'}`);
  return parts.join(' and ') + ' selected';
});

const selectionSubtitle = computed(() => {
  const first = knowledgeStore.selectedEntities[0] ?? knowledgeStore.selectedDocuments[0];
  return first?.name ? `Starting with: ${first.name}` : 'Open a scoped chat to explore these topics';
});

// When exactly one entity is selected, load its detail + relationships
watch(
  () => knowledgeStore.activeEntityId,
  async (ids) => {
    if (ids.length !== 1) {
      singleEntity.value = null;
      relationships.value = [];
      return;
    }
    const entity = knowledgeStore.selectedEntities[0];
    singleEntity.value = entity
      ? { id: entity.id!, name: entity.name!, type: entity.type! }
      : null;

    loadingRels.value = true;
    relationships.value = [];
    try {
      const resp = await knowledgeService.getEntityRelationships(ids[0]);
      if (singleEntity.value) {
        singleEntity.value.description = resp.data.entity.description;
      }
      relationships.value = resp.data.relationships;
    } catch (e) {
      console.error('[KnowledgeExplorer] Failed to load relationships', e);
    } finally {
      loadingRels.value = false;
    }
  },
  { immediate: true }
);

async function exploreInChat() {
  creating.value = true;
  try {
    const entityId = knowledgeStore.activeEntityId[0] ?? null;
    const docId = knowledgeStore.activeDocumentId[0] ?? null;
    const scopeType = entityId ? 'entity' : docId ? 'document' : 'all_library';
    const scopeId = entityId ?? docId ?? null;

    const firstName = knowledgeStore.selectedEntities[0]?.name
      ?? knowledgeStore.selectedDocuments[0]?.name
      ?? 'Knowledge Exploration';

    await chatStore.createSession(firstName, scopeType, scopeId);
    router.push({ name: 'chats', params: { id: chatStore.activeSession?.id } });
  } finally {
    creating.value = false;
  }
}
</script>

<style scoped>
.knowledge-explorer-view {
  height: calc(100vh - 70px);
  overflow-y: auto;
}
</style>
