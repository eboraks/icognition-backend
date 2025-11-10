<template>
  <div id="body-knowledge-explorer" class="grid nested-grid grid-nogutter col-12 surface-100" style="height: calc(100% - 4.5em - 5.25em);">
    <div class="col-12 bg-white border-round border-300 border-2 p-0 h-full">
      <Splitter class="h-full border-round border-noround-right">
        <SplitterPanel :class="{ 'splitter-panel-container-small': !buttonToggleSplitterPanelLeft }" class="p-2 border-round bg-primary-500 border-noround-right" :size="25" :minSize="1">
          <div class="grid h-full">
            <div class="col-6">
              <Button v-if="!buttonToggleSplitterPanelLeft" class="bg-transparent border-transparent border-0 text-white ml-1" icon="pi pi-filter" @click="buttonToggleSplitterPanelLeft = !buttonToggleSplitterPanelLeft" rounded aria-label="Expand Panel"/>
              <h4 v-if="buttonToggleSplitterPanelLeft" class="font-semibold pt-2 text-white">Knowledge Explorer</h4>
            </div>
            <div class="col-6 text-right">
              <Button v-if="buttonToggleSplitterPanelLeft" class="bg-transparent border-transparent border-0 text-white" icon="pi pi-filter-slash" @click="buttonToggleSplitterPanelLeft = !buttonToggleSplitterPanelLeft" rounded aria-label="Collapse Panel"/>
            </div>
            <div class="w-full" style="height: calc(100% - 3.75em);" v-if="buttonToggleSplitterPanelLeft">
              <FilterTree />
            </div>
          </div>
        </SplitterPanel>
        <SplitterPanel :class="{ 'splitter-panel-container-big': !buttonToggleSplitterPanelLeft }" class="p-0 bg-white flex flex-column" :size="75">
          <div class="flex flex-column h-full">
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
              />
            </div>
          </div>
        </SplitterPanel>
      </Splitter>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import Splitter from 'primevue/splitter';
import SplitterPanel from 'primevue/splitterpanel';
import Button from 'primevue/button';
import FilterTree from '@/components/knowledge_explorer/FilterTree.vue';
import ChatPanel from '@/components/knowledge_explorer/ChatPanel.vue';
import { useKnowledgeExplorerStore } from '@/stores/knowledgeExplorerStore';

const buttonToggleSplitterPanelLeft = ref(true);
const knowledgeStore = useKnowledgeExplorerStore();
knowledgeStore.ensureActiveChatTab();

const handleAddTab = () => {
  knowledgeStore.addChatTab();
};
</script>

<style scoped>
.workspace {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.tab-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 1rem 1.5rem 0.5rem;
  background: var(--p-surface-0);
  border-bottom: 1px solid var(--p-content-border-color);
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
}

.tab-add-button:hover {
  border-color: var(--p-primary-400);
  color: var(--p-primary-500);
  background: var(--p-primary-50);
  box-shadow: 0 4px 12px rgba(45, 122, 138, 0.15);
}

.splitter-panel-container-small {
  width: 42px !important;
  transition: width 0.5s ease;
}

.splitter-panel-container-big {
  width: calc(100% - 42px) !important;
  transition: width 0.5s ease;
}

:deep(.p-splitter-panel) {
  overflow: hidden;
}
</style>

