<template>
  <div class="chat-panel-container">
    <ScrollPanel class="chat-messages" ref="messagesContainer">
      <div
        v-for="(message, index) in messages"
        :key="index"
        class="message-wrapper"
        :class="message.type"
      >
        <div v-if="message.type === 'system'" class="message system-message">
          <div class="message-icon">🤖</div>
          <div class="message-content">
            <p>{{ message.content }}</p>
            <div v-if="message.actions && message.actions.length > 0" class="action-buttons">
              <Button
                v-for="action in message.actions"
                :key="action.id"
                :label="action.label"
                outlined
                severity="secondary"
                class="action-button"
                @click="handleActionClick(action)"
              />
            </div>
            <div v-if="message.resources && message.resources.length > 0" class="resources-section">
              <details>
                <summary>Resources</summary>
                <ul>
                  <li v-for="resource in message.resources" :key="resource.id">
                    {{ resource.title }}
                  </li>
                </ul>
              </details>
            </div>
          </div>
        </div>
        <div v-else-if="message.type === 'filter'" class="message filter-message">
          <p>{{ message.content }}</p>
        </div>
        <div v-else-if="message.type === 'user'" class="message user-message">
          <p>{{ message.content }}</p>
        </div>
      </div>
    </ScrollPanel>
    <div class="chat-input-container">
      <InputText
        v-model="inputMessage"
        placeholder="Ask a follow-up question..."
        class="flex-1"
        @keyup.enter="sendMessage"
      />
      <Button
        icon="pi pi-send"
        rounded
        @click="sendMessage"
        :disabled="!inputMessage.trim() || loading"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, nextTick, onMounted } from 'vue';
import Button from 'primevue/button';
import InputText from 'primevue/inputtext';
import ScrollPanel from 'primevue/scrollpanel';
import { knowledgeService, type ContextualMessageResponse, type ActionResponse } from '@/services/knowledgeService';

interface ChatMessage {
  type: 'system' | 'user' | 'filter';
  content: string;
  actions?: Array<{ id: string; label: string }>;
  resources?: Array<{ id: number; title: string }>;
}

const props = defineProps<{
  selectedEntityId?: number | null;
  selectedDocumentId?: number | null;
}>();

const messages = ref<ChatMessage[]>([]);
const inputMessage = ref('');
const messagesContainer = ref<any>(null);
const loading = ref(false);

const scrollToBottom = () => {
  nextTick(() => {
    if (messagesContainer.value) {
      const scrollElement = messagesContainer.value.$el?.querySelector('.p-scrollpanel-content');
      if (scrollElement) {
        scrollElement.scrollTop = scrollElement.scrollHeight;
      }
    }
  });
};

const loadInitialMessage = async () => {
  try {
    loading.value = true;
    const response = await knowledgeService.getContextualMessage(
      props.selectedEntityId || undefined,
      props.selectedDocumentId || undefined
    );
    
    const contextualData: ContextualMessageResponse = response.data;
    
    // Add filter selection message if something is selected
    if (props.selectedEntityId || props.selectedDocumentId) {
      let filterMessage = '';
      if (props.selectedEntityId) {
        // We'll get the entity name from the contextual message
        filterMessage = `You filtered by ${contextualData.entity?.name || 'an entity'}`;
      } else if (props.selectedDocumentId) {
        filterMessage = `You filtered by ${contextualData.document?.title || 'a document'}`;
      }
      
      if (filterMessage) {
        messages.value.push({
          type: 'filter',
          content: filterMessage,
        });
      }
    }
    
    // Add the contextual message
    messages.value.push({
      type: 'system',
      content: contextualData.message,
      actions: contextualData.actions,
    });
    
    scrollToBottom();
  } catch (error) {
    console.error('Failed to load initial message:', error);
    messages.value.push({
      type: 'system',
      content: 'Hello! I\'m your knowledge exploration assistant. Use the filters on the left to navigate your knowledge graph, or ask me a question directly.',
      actions: [],
    });
  } finally {
    loading.value = false;
  }
};

const handleActionClick = async (action: { id: string; label: string }) => {
  // Add user message for the action
  messages.value.push({
    type: 'user',
    content: action.label,
  });
  
  scrollToBottom();
  
  try {
    loading.value = true;
    const response = await knowledgeService.handleAction(
      action.id,
      props.selectedEntityId || undefined,
      props.selectedDocumentId || undefined
    );
    
    const actionData: ActionResponse = response.data;
    
    // Add system response
    messages.value.push({
      type: 'system',
      content: actionData.message,
      resources: actionData.resources,
    });
    
    scrollToBottom();
  } catch (error) {
    console.error('Failed to handle action:', error);
    messages.value.push({
      type: 'system',
      content: 'Sorry, I encountered an error processing that action. Please try again.',
    });
  } finally {
    loading.value = false;
  }
};

const sendMessage = async () => {
  if (!inputMessage.value.trim() || loading.value) {
    return;
  }
  
  const userMessage = inputMessage.value.trim();
  inputMessage.value = '';
  
  // Add user message
  messages.value.push({
    type: 'user',
    content: userMessage,
  });
  
  scrollToBottom();
  
  // For now, just echo back. In the future, this could call a chat endpoint
  setTimeout(() => {
    messages.value.push({
      type: 'system',
      content: 'I received your message. Direct question handling will be available soon.',
    });
    scrollToBottom();
  }, 500);
};

// Watch for selection changes
watch(
  () => [props.selectedEntityId, props.selectedDocumentId],
  () => {
    // Clear messages and load new contextual message when selection changes
    messages.value = [];
    loadInitialMessage();
  },
  { immediate: true }
);

onMounted(() => {
  loadInitialMessage();
});
</script>

<style scoped>
.chat-panel-container {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  overflow: hidden;
  background: var(--p-surface-0);
}

.chat-messages {
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

:deep(.p-scrollpanel) {
  height: 100%;
}

:deep(.p-scrollpanel-wrapper) {
  height: 100%;
}

:deep(.p-scrollpanel-content) {
  padding: 1.5rem;
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.message-wrapper {
  display: flex;
  width: 100%;
}

.message-wrapper.user {
  justify-content: flex-end;
}

.message-wrapper.system,
.message-wrapper.filter {
  justify-content: flex-start;
}

.message {
  max-width: 70%;
  padding: 0.9rem 1.1rem;
  border-radius: 14px;
  word-wrap: break-word;
  background: var(--p-surface-card);
  border: 1px solid var(--p-content-border-color);
  box-shadow: 0 8px 16px rgba(15, 23, 42, 0.08);
}

.system-message {
  display: flex;
  gap: 0.85rem;
  align-items: flex-start;
  background: var(--p-primary-50);
  border-color: var(--p-primary-200);
}

.message-icon {
  font-size: 1.4rem;
  flex-shrink: 0;
  background: var(--p-primary-500);
  color: var(--p-primary-contrast-color);
  width: 2.25rem;
  height: 2.25rem;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
}

.message-content {
  flex: 1;
}

.message-content p {
  margin: 0 0 0.75rem 0;
  line-height: 1.6;
  color: var(--p-text-color);
  font-size: 0.95rem;
}

.system-message .message-content p {
  color: var(--p-primary-800);
}

.message-content p:last-child {
  margin-bottom: 0;
}

.filter-message {
  background: var(--p-primary-50);
  border: 1px solid var(--p-primary-200);
  color: var(--p-primary-700);
  text-align: center;
  margin: 0 auto;
  font-size: 0.85rem;
  padding: 0.55rem 1.2rem;
  border-radius: 999px;
  box-shadow: none;
}

.user-message {
  background: var(--p-primary-500);
  color: var(--p-primary-contrast-color);
  border: none;
  box-shadow: 0 8px 16px rgba(45, 122, 138, 0.25);
}

.user-message p {
  margin: 0;
  color: var(--p-primary-contrast-color);
}

.action-buttons {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin-top: 0.75rem;
}

.action-button {
  border-radius: 999px;
  padding-inline: 1.25rem;
  padding-block: 0.45rem;
  font-weight: 500;
}

.resources-section {
  margin-top: 0.75rem;
  font-size: 0.9rem;
  background: var(--p-surface-100);
  border: 1px dashed var(--p-content-border-color);
  border-radius: 0.9rem;
  padding: 0.7rem 1rem;
}

.resources-section details {
  cursor: pointer;
}

.resources-section summary {
  font-weight: 600;
  margin-bottom: 0.5rem;
  color: var(--p-text-color);
}

.resources-section ul {
  list-style: none;
  padding-left: 0;
  margin: 0.5rem 0 0 0;
}

.resources-section li {
  padding: 0.3rem 0;
  color: var(--p-text-muted-color);
}

.chat-input-container {
  display: flex;
  padding: 1.1rem 1.4rem;
  border-top: 1px solid var(--p-content-border-color);
  gap: 0.75rem;
  align-items: center;
  background: var(--p-surface-card);
}

:deep(.chat-input-container .p-inputtext) {
  border-radius: 0.8rem;
  padding-block: 0.8rem;
  background: var(--p-surface-0);
  border: 1px solid var(--p-content-border-color);
  color: var(--p-text-muted-color);
}

:deep(.chat-input-container .p-inputtext::placeholder) {
  color: var(--p-text-muted-color);
}
</style>

