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
            <template v-else-if="message.commentOptions">
              <div class="comment-options">
                <div v-for="option in message.commentOptions" :key="option.label" class="comment-card">
                  <div class="comment-card-header">
                    <span class="comment-option-label">{{ option.label }}</span>
                    <Button
                      icon="pi pi-copy"
                      text
                      rounded
                      size="small"
                      severity="secondary"
                      class="copy-btn"
                      :class="{ copied: copiedLabel === option.label }"
                      @click="copyToClipboard(option.text, option.label)"
                    />
                  </div>
                  <p class="comment-card-text">{{ option.text }}</p>
                </div>
              </div>
            </template>
            <div v-else class="message-text" v-html="message.content"></div>
            <!-- Status text -->
            <div v-if="message.pending && message.statusText" class="message-status">
                <i class="pi pi-spin pi-spinner" style="font-size: 0.8rem; margin-right: 0.5rem"></i>
                {{ message.statusText }}
            </div>
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
      <div class="quick-actions-row">
        <Button
          label="Write Comment"
          icon="pi pi-pencil"
          outlined
          severity="secondary"
          size="small"
          class="quick-action-btn"
          :disabled="loading"
          @click="writeComment"
        />
      </div>
      <div class="input-row">
        <TypedChatInput
          v-model="inputMessage"
          placeholder="Ask a follow-up question..."
          :is-extension="false"
          :session-id="chatSessionId"
          :disabled="loading"
          @send="sendMessage"
          class="flex-1"
        />
        <Button
          icon="pi pi-send"
          rounded
          @click="sendMessage"
          :disabled="!inputMessage.trim() || loading"
        />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, nextTick } from 'vue';
import Button from 'primevue/button';
import TypedChatInput from './TypedChatInput.vue';
import ScrollPanel from 'primevue/scrollpanel';
import ProgressSpinner from 'primevue/progressspinner';
import { knowledgeService, type ContextualMessageResponse, type ActionResponse } from '@/services/knowledgeService.js';
import { useChatStore, type ChatMessage as ChatStoreMessage } from '@/stores/chat_store.js';
import { useAuthStore } from '@/stores/auth_store.js';

interface CommentOption {
  label: string;
  text: string;
}

interface ChatMessage {
  type: 'system' | 'user' | 'filter';
  content: string;
  actions?: Array<{ id: string; label: string }>;
  resources?: Array<{ id: number; title: string }>;
  pending?: boolean;
  statusText?: string;
  commentOptions?: CommentOption[] | null;
}

function parseCommentOptions(content: string): CommentOption[] | null {
  const stripped = content.replace(/<[^>]*>/g, ' ');
  if (!/Option A/i.test(stripped) || !/Option B/i.test(stripped) || !/Option C/i.test(stripped)) {
    return null;
  }

  // HTML mode: detect <strong>Option X...</strong> headers
  const htmlHeaders = [...content.matchAll(/<strong>(Option [ABC][^<]*)<\/strong>/gi)];
  if (htmlHeaders.length === 3) {
    const parts = content.split(/<strong>Option [ABC][^<]*<\/strong>/gi);
    return htmlHeaders.map((h, i) => ({
      label: h[1].trim(),
      text: parts[i + 1]
        .replace(/^[:\s–\-]+/, '')
        .replace(/<[^>]*>/g, ' ')
        .replace(/\s+/g, ' ')
        .trim(),
    }));
  }

  // Markdown mode: split on **Option X...** markers
  const mdParts = content.split(/\*{1,2}(Option [ABC][^*]*)\*{1,2}/i);
  if (mdParts.length >= 7) {
    return [
      { label: mdParts[1].trim(), text: mdParts[2].trim() },
      { label: mdParts[3].trim(), text: mdParts[4].trim() },
      { label: mdParts[5].trim(), text: mdParts[6].trim() },
    ];
  }

  return null;
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
const suggestions = ref<string[]>([]);
const allVocabulary = ref<string[]>([]);
const copiedLabel = ref<string | null>(null);

const copyToClipboard = async (text: string, label: string) => {
  try {
    await navigator.clipboard.writeText(text);
    copiedLabel.value = label;
    setTimeout(() => { copiedLabel.value = null; }, 2000);
  } catch {
    // Fallback for environments without clipboard API
    const el = document.createElement('textarea');
    el.value = text;
    document.body.appendChild(el);
    el.select();
    document.execCommand('copy');
    document.body.removeChild(el);
    copiedLabel.value = label;
    setTimeout(() => { copiedLabel.value = null; }, 2000);
  }
};

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

const extractVocabulary = (contextualData: ContextualMessageResponse) => {
    const textParts: string[] = [];
    if (contextualData.message) {
        // Simple HTML tag removal
        const cleanMsg = contextualData.message.replace(/<[^>]*>?/gm, ' ');
        textParts.push(cleanMsg);
    }
    if (contextualData.entity?.name) textParts.push(contextualData.entity.name);
    if (contextualData.document?.title) textParts.push(contextualData.document.title);

    const text = textParts.join(' ').toLowerCase();
    
    // Simple regex for words >= 3 chars
    const words = text.match(/\b[a-z]{3,}\b/g) || [];
    
    // Basic stop words to filter out noise
    const stopWords = new Set(['the', 'and', 'for', 'that', 'this', 'with', 'you', 'are', 'not', 'have', 'from', 'but', 'can', 'will', 'what', 'all', 'one', 'has', 'more', 'about', 'they', 'our', 'out', 'key', 'points', 'summary', 'inc', 'ltd', 'com']);
    
    const uniqueWords = new Set<string>();
    words.forEach(word => {
        if (!stopWords.has(word)) {
            uniqueWords.add(word);
        }
    });
    
    allVocabulary.value = Array.from(uniqueWords).sort();
};

const search = (event: { query: string }) => {
    if (!event.query || !event.query.trim()) {
        suggestions.value = [];
        return;
    }

    const query = event.query;
    const lastSpaceIndex = query.lastIndexOf(' ');
    let prefix = '';
    let term = query;
    
    if (lastSpaceIndex !== -1) {
        prefix = query.substring(0, lastSpaceIndex + 1);
        term = query.substring(lastSpaceIndex + 1);
    }
    
    if (!term) {
        suggestions.value = [];
        return;
    }
    
    const lowerTerm = term.toLowerCase();
    const matches = allVocabulary.value.filter(word => 
        word.toLowerCase().startsWith(lowerTerm)
    );
    
    suggestions.value = matches.map(word => prefix + word);
};

const loadInitialMessage = async () => {
  // Prevent duplicate calls
  if (isLoadingInitialMessage.value) {
    return;
  }
  
  if (!authStore.currentUser && !authStore.isAuthDisabled) {
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
      messages.value = chatStore.activeSession.messages.map(msg => {
        const isPending = (msg as any).pending ?? false;
        return {
          type: msg.senderId === authStore.currentUser?.uid ? 'user' : 'system',
          content: msg.content,
          actions: (msg as any).actions,
          resources: (msg as any).resources,
          pending: isPending,
          commentOptions: !isPending ? parseCommentOptions(msg.content) : null,
        };
      });
    } else {
      messages.value = [];
    }

    // Only show an opening message if this session has no messages yet
    if (messages.value.length === 0) {
      if (props.selectedEntityId || props.selectedDocumentId) {
        // Scoped session: show a context-aware greeting
        let scopeType = 'all_library';
        let scopeId: number | null = null;
        let filterMessage = '';

        if (props.selectedEntityId) {
          scopeType = 'entity';
          scopeId = props.selectedEntityId;
          filterMessage = 'Entity context active. How can I help you explore this topic?';
        } else if (props.selectedDocumentId) {
          scopeType = 'document';
          scopeId = props.selectedDocumentId;
          filterMessage = 'Document context active. How can I help you explore this document?';
        }

        // Sync backend session scope
        if (chatStore.activeSession &&
            (chatStore.activeSession.scope_type !== scopeType || chatStore.activeSession.scope_id !== scopeId)) {
          await chatStore.updateSessionScope(props.chatSessionId, scopeType, scopeId);
        }

        messages.value.push({
          type: 'system',
          content: toParagraphHtml(filterMessage),
          actions: [],
        });
      } else {
        // Reset to all_library scope if no selection
        if (chatStore.activeSession && chatStore.activeSession.scope_type !== 'all_library') {
          await chatStore.updateSessionScope(props.chatSessionId, 'all_library', null);
        }

        // Simple greeting — no external API call
        messages.value.push({
          type: 'system',
          content: toParagraphHtml('How can I help you today?'),
          actions: [],
        });
      }
    }
  } finally {
    isLoadingInitialMessage.value = false;
  }
  
  scrollToBottom();
};

const writeComment = () => {
  inputMessage.value = 'Write a comment on this post: ';
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
  suggestions.value = [];
  
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
      const newMessagesFormatted: ChatMessage[] = newMessages.map(msg => {
        const isPending = (msg as any).pending ?? false;
        return {
          type: (msg.senderId === authStore.currentUser?.uid ? 'user' : 'system') as 'user' | 'system',
          content: msg.content,
          actions: (msg as any).actions,
          resources: (msg as any).resources,
          pending: isPending,
          statusText: (msg as any).statusText,
          commentOptions: !isPending ? parseCommentOptions(msg.content) : null,
        };
      });
      
      // Only update if the length changed or content differs (to avoid unnecessary updates)
      if (messages.value.length !== newMessagesFormatted.length ||
          messages.value.some((msg, idx) => {
            const newMsg = newMessagesFormatted[idx];
            return (
              !newMsg ||
              msg.content !== newMsg.content ||
              msg.pending !== newMsg.pending ||
              msg.statusText !== newMsg.statusText
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
  background: #ffffff;
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
  background: #ffffff;
  border: 1px solid #e2e8f0;
  box-shadow: 0 8px 16px rgba(15, 23, 42, 0.08);
  word-break: break-word;
  overflow-wrap: anywhere;
}

.message-text {
  white-space: pre-wrap;
  line-height: 1.5;
  font-family: 'Roboto Mono', monospace;
  color: #334155;
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
  color: #334155;
  font-size: 0.95rem;
}

.system-message .message-content p {
  color: #334155;
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

.message-status {
    font-size: 0.8rem;
    color: #64748b;
    margin-top: 0.5rem;
    display: flex;
    align-items: center;
    font-style: italic;
}

.filter-message {
  background: #ecfdf5;
  border: 1px solid #a7f3d0;
  color: #047857;
  text-align: center;
  margin: 0 auto;
  font-size: 0.85rem;
  padding: 0.55rem 1.2rem;
  border-radius: 999px;
  box-shadow: none;
  font-family: 'Roboto Mono', monospace;
}

.user-message {
  background: #10b981;
  color: #ffffff;
  border: none;
  box-shadow: 0 8px 16px rgba(45, 122, 138, 0.25);
}

.user-message p {
  margin: 0;
  color: #ffffff;
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
  background: #f1f5f9;
  border: 1px dashed #e2e8f0;
  border-radius: 0.9rem;
  padding: 0.7rem 1rem;
}

.resources-section details {
  cursor: pointer;
}

.resources-section summary {
  font-weight: 600;
  margin-bottom: 0.5rem;
  color: #334155;
}

.resources-section ul {
  list-style: none;
  padding-left: 0;
  margin: 0.5rem 0 0 0;
}

.resources-section li {
  padding: 0.3rem 0;
  color: #64748b;
}

.chat-input-container {
  display: flex;
  flex-direction: column;
  padding: 1.1rem 1.4rem;
  border-top: 1px solid #e2e8f0;
  gap: 0.5rem;
  background: #ffffff;
}

.quick-actions-row {
  display: flex;
  gap: 0.5rem;
}

.quick-action-btn {
  border-radius: 999px;
  padding-inline: 1rem;
  padding-block: 0.35rem;
  font-size: 0.82rem;
  font-weight: 500;
}

.input-row {
  display: flex;
  gap: 0.75rem;
  align-items: center;
}

:deep(.chat-input-container .p-autocomplete) {
  width: 100%;
}

:deep(.chat-input-container .p-autocomplete-input) {
  width: 100%;
  border-radius: 0.8rem;
  padding-block: 0.8rem;
  background: #ffffff;
  border: 1px solid #e2e8f0;
  color: #64748b;
  padding-left: 1rem;
  font-family: 'Roboto Mono', monospace;
}

:deep(.chat-input-container .p-autocomplete-input::placeholder) {
  color: #64748b;
  font-family: 'Roboto Mono', monospace;
}

/* Comment option cards (Phase 6.2) */
.message:has(.comment-options) {
  max-width: min(700px, 88%);
}

.comment-options {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  width: 100%;
}

.comment-card {
  background: #ffffff;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  padding: 0.75rem 1rem;
  transition: box-shadow 0.15s;
}

.comment-card:hover {
  box-shadow: 0 2px 8px rgba(15, 23, 42, 0.1);
}

.comment-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 0.5rem;
}

.comment-option-label {
  font-weight: 600;
  font-size: 0.88rem;
  color: #059669;
}

.copy-btn {
  flex-shrink: 0;
  opacity: 0.6;
  transition: opacity 0.15s, color 0.15s;
}

.copy-btn:hover {
  opacity: 1;
}

:deep(.copy-btn.copied .p-button-icon) {
  color: #22c55e !important;
}

.copy-btn.copied {
  opacity: 1;
}

.comment-card-text {
  font-size: 0.9rem;
  line-height: 1.55;
  color: #334155;
  margin: 0;
  font-family: 'Roboto Mono', monospace;
  white-space: pre-wrap;
}
</style>

