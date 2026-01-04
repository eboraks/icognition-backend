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
          <div class="message-icon">
            <img src="/src/assets/images/icog_action_icon_16x16.png" alt="AI Icon" style="width: 2.25rem; height: 2.25rem; object-fit: contain;" />
          </div>
          <div class="message-content">
            <div v-if="message.pending" class="message-spinner">
              <ProgressSpinner strokeWidth="4" style="width: 32px; height: 32px" />
            </div>
            <div v-else class="message-text" v-html="message.content"></div>
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
          <div class="message-text" v-html="message.content"></div>
        </div>
        <div v-else-if="message.type === 'user'" class="message user-message">
          <div class="message-text" v-html="message.content"></div>
        </div>
      </div>
    </ScrollPanel>
    <div class="chat-input-container">
      <InputText
        v-model="inputMessage"
        placeholder="Ask a follow-up question..."
        class="flex-1"
        @keydown.enter="sendMessage"
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
import { ref, watch, nextTick } from 'vue';
import Button from 'primevue/button';
import InputText from 'primevue/inputtext';
import ScrollPanel from 'primevue/scrollpanel';
import ProgressSpinner from 'primevue/progressspinner';
import { knowledgeService, type ContextualMessageResponse, type ActionResponse } from '@/services/knowledgeService';
import { useChatStore, type ChatMessage as ChatStoreMessage } from '@/stores/chat_store';
import { useAuthStore } from '@/stores/auth_store';

interface ChatMessage {
  type: 'system' | 'user' | 'filter';
  content: string;
  actions?: Array<{ id: string; label: string }>;
  resources?: Array<{ id: number; title: string }>;
  pending?: boolean;
}

const props = defineProps<{
  selectedEntityId?: number | null;
  selectedDocumentId?: number | null;
  chatSessionId: number; // New required prop
}>();

const escapeHtml = (unsafe: string) =>
  unsafe
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');

const toParagraphHtml = (content: string) => `<p>${escapeHtml(content)}</p>`;

const chatStore = useChatStore();
const authStore = useAuthStore();
const messages = ref<ChatMessage[]>([]);
const inputMessage = ref('');
const messagesContainer = ref<any>(null);
const loading = ref(false);
const isLoadingInitialMessage = ref(false); // Prevent duplicate calls

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
  // Prevent duplicate calls
  if (isLoadingInitialMessage.value) {
    return;
  }
  
  if (!authStore.currentUser) {
    messages.value = [{
      type: 'system',
      content: toParagraphHtml('Please log in to start exploring your knowledge graph and chat.'),
      actions: [],
    }];
    return;
  }

  isLoadingInitialMessage.value = true;
  
  try {
    // Switch chat store to the session provided by the prop
    await chatStore.switchActiveSession(props.chatSessionId);

    // After switching, populate local messages from the active session's messages
    if (chatStore.activeSession) {
      messages.value = chatStore.activeSession.messages.map(msg => ({
        type: msg.senderId === authStore.currentUser?.uid ? 'user' : 'system',
        content: msg.content,
        actions: (msg as any).actions,
        resources: (msg as any).resources,
        pending: (msg as any).pending ?? false,
      }));
    } else {
      messages.value = [];
    }

    // Check if we already have a contextual message in the loaded messages
    // (to avoid adding duplicate opening messages)
    const hasContextualMessage = messages.value.some(
      msg => msg.type === 'system' && 
      msg.content && 
      !msg.content.includes('Please log in') &&
      (msg.content.includes('recently bookmarked') || 
       msg.content.includes('Hello! I\'m your knowledge exploration assistant'))
    );

    // Add specific contextual message if no messages yet or selection changed
    // AND we don't already have a contextual message
    if (!hasContextualMessage && 
        (messages.value.length === 0 || chatStore.activeSession?.scope_id !== (props.selectedEntityId || props.selectedDocumentId))) {
      try {
        loading.value = true;
        const response = await knowledgeService.getContextualMessage(
          props.selectedEntityId || undefined,
          props.selectedDocumentId || undefined
        );
        
        const contextualData: ContextualMessageResponse = response.data;
        
        if (props.selectedEntityId || props.selectedDocumentId) {
          let filterMessage = '';
          if (props.selectedEntityId) {
            filterMessage = `You filtered by ${contextualData.entity?.name || 'an entity'}`;
          } else if (props.selectedDocumentId) {
            filterMessage = `You filtered by ${contextualData.document?.title || 'a document'}`;
          }
          
          if (filterMessage) {
            messages.value.push({
              type: 'filter',
              content: toParagraphHtml(filterMessage),
            });
          }
        }
        
        // Only add if we don't already have a similar message
        const messageExists = messages.value.some(
          msg => msg.type === 'system' && 
          msg.content === contextualData.message
        );
        
        if (!messageExists) {
          messages.value.push({
            type: 'system',
            content: contextualData.message,
            actions: contextualData.actions,
          });
        }
      } catch (error) {
        console.error('Failed to load contextual message:', error);
        // Only add fallback if we don't already have a message
        if (messages.value.length === 0) {
          messages.value.push({
            type: 'system',
            content: toParagraphHtml('Hello! I\'m your knowledge exploration assistant. Use the filters on the left to navigate your knowledge graph, or ask me a question directly.'),
            actions: [],
          });
        }
      } finally {
        loading.value = false;
      }
    }
  } finally {
    isLoadingInitialMessage.value = false;
  }
  
  scrollToBottom();
};

const handleActionClick = async (action: { id: string; label: string }) => {
  // Add user message for the action
  messages.value.push({
    type: 'user',
    content: toParagraphHtml(action.label),
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
    
    // Append response to chatStore messages as well for persistence
    // This will implicitly update local messages due to chatStore.messages watcher
    chatStore.addMessage({
      _id: Date.now().toString(),
      content: actionData.message,
      senderId: 'agent',
      timestamp: new Date().toLocaleTimeString(),
      date: new Date().toLocaleDateString(),
    });

    // Manually add resources/actions to the local message if chatStore doesn't handle them
    // (This part might not be needed if chatStore.addMessage handles resources/actions)
    if (chatStore.activeSession) {
      const lastMessage = chatStore.activeSession.messages[chatStore.activeSession.messages.length - 1];
      if (lastMessage && lastMessage.senderId === 'agent') {
        (lastMessage as any).resources = actionData.resources;
        (lastMessage as any).actions = actionData.actions;
      }
    }
    
    scrollToBottom();
  } catch (error) {
    console.error('Failed to handle action:', error);
    messages.value.push({
      type: 'system',
      content: toParagraphHtml('Sorry, I encountered an error processing that action. Please try again.'),
    });
  } finally {
    loading.value = false;
  }
};

const sendMessage = async () => {
  if (!inputMessage.value.trim() || loading.value) {
    return;
  }
  
  // Ensure we have an active session
  if (!chatStore.activeSession) {
    // Try to switch to the session if we have a sessionId prop
    if (props.chatSessionId) {
      try {
        await chatStore.switchActiveSession(props.chatSessionId);
      } catch (error) {
        console.error('Failed to switch to session:', error);
        messages.value.push({
          type: 'system',
          content: toParagraphHtml('Unable to connect to chat session. Please try refreshing the page.'),
        });
        return;
      }
    } else {
      console.error('No active session and no sessionId provided');
      return;
    }
  }
  
  const userMessageContent = inputMessage.value.trim();
  inputMessage.value = '';
  
  try {
    loading.value = true;
    // Send message via chatStore, which handles WebSocket and adds message to chatStore.messages
    // The watcher will sync it to local messages.value
    await chatStore.sendMessage(userMessageContent, props.chatSessionId);
  } catch (error) {
    console.error('Failed to send chat message:', error);
    if (chatStore.activeSession) {
        chatStore.activeSession.messages.pop(); // Remove the user message if sending failed
    }
    messages.value.push({
      type: 'system',
      content: toParagraphHtml('Sorry, I encountered an error sending your message. Please try again.'),
    });
  } finally {
    loading.value = false;
  }
  scrollToBottom();
};

// Watch chatStore.activeSession?.messages to sync new messages from WebSocket
watch(
  () => chatStore.activeSession?.messages,
  (newMessages) => {
    if (!authStore.currentUser || !chatStore.activeSession || !newMessages) return;
    
    // Only sync if we're on the active session that matches our prop
    if (chatStore.activeSession.id === props.chatSessionId) {
      // Convert chatStore messages to ChatPanel's local ChatMessage format
      const newMessagesFormatted: ChatMessage[] = newMessages.map(msg => ({
        type: (msg.senderId === authStore.currentUser?.uid ? 'user' : 'system') as 'user' | 'system',
        content: msg.content,
        actions: (msg as any).actions,
        resources: (msg as any).resources,
        pending: (msg as any).pending ?? false,
      }));
      
      // Only update if the length changed or content differs (to avoid unnecessary updates)
      if (messages.value.length !== newMessagesFormatted.length ||
          messages.value.some((msg, idx) => {
            const newMsg = newMessagesFormatted[idx];
            return (
              !newMsg ||
              msg.content !== newMsg.content ||
              msg.pending !== newMsg.pending
            );
          })) {
        messages.value = [...newMessagesFormatted];
        scrollToBottom();
      }
    }
  },
  { deep: true }
);

// Watch for selection changes with debouncing to prevent duplicate calls
let watchTimeout: ReturnType<typeof setTimeout> | null = null;
watch(
  () => [props.selectedEntityId, props.selectedDocumentId, props.chatSessionId],
  (newValues, oldValues) => {
    // Clear any pending timeout
    if (watchTimeout) {
      clearTimeout(watchTimeout);
    }
    
    // Debounce the call to prevent rapid multiple calls
    watchTimeout = setTimeout(() => {
      // Extract new and old values safely
      const [newEntityId, newDocumentId, newChatSessionId] = newValues;
      const [oldEntityId, oldDocumentId, oldChatSessionId] = oldValues || [undefined, undefined, undefined];

      // Only reload if the chat session itself changed, or if selections changed within the same session
      if (
        (oldValues === undefined) || // First run
        newChatSessionId !== oldChatSessionId ||
        (newChatSessionId === oldChatSessionId && (newEntityId !== oldEntityId || newDocumentId !== oldDocumentId))
      ) {
        messages.value = [];
        loadInitialMessage();
      }
    }, 100); // 100ms debounce
  },
  { immediate: true }
);

// The initial load is now handled by the 'watch' with immediate: true
// onMounted(() => {
//   loadInitialMessage();
// });
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
  max-width: min(640px, 70%);
  width: fit-content;
  padding: 0.9rem 1.1rem;
  border-radius: 14px;
  background: var(--p-surface-card);
  border: 1px solid var(--p-content-border-color);
  box-shadow: 0 8px 16px rgba(15, 23, 42, 0.08);
  word-break: break-word;
  overflow-wrap: anywhere;
}

.message-text {
  white-space: pre-wrap;
  line-height: 1.5;
}

.message-text p {
  margin: 0 0 0.75rem 0;
}

.message-text p:last-child {
  margin-bottom: 0;
}

.message-text ul {
  margin: 0.5rem 0 0.5rem 1.25rem;
  padding-left: 1.25rem;
  list-style-type: disc;
}

.message-text li {
  margin-bottom: 0.25rem;
}

.system-message {
  display: flex;
  gap: 0.85rem;
  align-items: flex-start;
  background: var(--blue-100); /* Light blue background */
  border-color: var(--blue-200); /* Slightly darker blue border */
}

.message-icon {
  font-size: 1.4rem;
  flex-shrink: 0;
  background: transparent; /* Remove background as image provides it */
  color: transparent; /* Remove color as image provides it */
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
  color: var(--p-text-color);
}

.message-content p:last-child {
  margin-bottom: 0;
}

.message-spinner {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 2rem;
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

