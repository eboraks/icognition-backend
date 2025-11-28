<template>
  <div class="knowledge-explorer-view">
    <div class="tab-header">
      <div class="tab-buttons">
        <button
          v-for="tab in knowledgeStore.chatTabs"
          :key="tab.id"
          :class="['tab-button', { active: tab.id === knowledgeStore.activeChatTabId }]"
          type="button"
          @click="knowledgeStore.setActiveChatTab(tab.id)"
        >
          <i class="pi pi-comments" />
          <span>{{ tab.title }}</span>
        </button>
      </div>
      <button class="tab-add-button" type="button" @click="handleAddTab">
        <i class="pi pi-plus" />
      </button>
    </div>
    <div class="workspace">
          <ChatPanel
            :key="knowledgeStore.activeChatTabId"
            :selected-entity-id="knowledgeStore.activeEntityId.length > 0 ? knowledgeStore.activeEntityId[0] : null"
            :selected-document-id="knowledgeStore.activeDocumentId.length > 0 ? knowledgeStore.activeDocumentId[0] : null"
            :chat-session-id="knowledgeStore.activeChatTabId"
          />
    </div>
  </div>
</template>

<script setup lang="ts">
import ChatPanel from '@/components/knowledge_explorer/ChatPanel.vue';
import { useKnowledgeExplorerStore } from '@/stores/knowledgeExplorerStore';

const knowledgeStore = useKnowledgeExplorerStore();
knowledgeStore.ensureActiveChatTab();

const handleAddTab = () => {
  knowledgeStore.addChatTab();
};
</script>

<style scoped>
.knowledge-explorer-view {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}

.workspace {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
}

.tab-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 1rem 1.5rem;
  background: var(--p-surface-0);
  border-bottom: 1px solid var(--p-content-border-color);
  flex-shrink: 0;
}

.tab-buttons {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.tab-button {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.75rem 1.5rem;
  border-radius: 0.85rem;
  background: var(--p-surface-100);
  border: 1px solid transparent;
  font-weight: 600;
  color: var(--p-text-muted-color);
  box-shadow: inset 0 -2px 0 rgba(15, 23, 42, 0.08);
  transition: all 0.2s ease;
  cursor: pointer;
}

.tab-button i {
  font-size: 1rem;
}

.tab-button:hover {
  background: var(--p-surface-200);
  color: var(--p-text-color);
}

.tab-button.active {
  background: var(--p-primary-50);
  border-color: var(--p-primary-200);
  color: var(--p-primary-700);
  box-shadow: inset 0 -2px 0 var(--p-primary-300);
}

.tab-add-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 2.25rem;
  height: 2.25rem;
  border-radius: 0.75rem;
  border: 1px dashed var(--p-content-border-color);
  background: var(--p-surface-0);
  color: var(--p-text-muted-color);
  transition: all 0.2s ease;
  cursor: pointer;
}

.tab-add-button:hover {
  border-color: var(--p-primary-400);
  color: var(--p-primary-500);
  background: var(--p-primary-50);
  box-shadow: 0 4px 12px rgba(45, 122, 138, 0.15);
}
</style>

