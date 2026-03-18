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
      <div class="input-row">
        <TypedChatInput
          v-model="inputMessage"
          placeholder="Type / for skills, or ask a question..."
          :session-id="chatSessionId"
          :disabled="loading"
          :skill-commands="SKILL_COMMAND_LIST"
          :vocabulary="chatVocabulary"
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
import { ref, computed, watch, nextTick } from 'vue';
import Button from 'primevue/button';
import TypedChatInput from './TypedChatInput.vue';
import ScrollPanel from 'primevue/scrollpanel';
import ProgressSpinner from 'primevue/progressspinner';
import { marked } from 'marked';
import { knowledgeService, type ContextualMessageResponse, type ActionResponse } from '@/services/knowledgeService.js';
import { useChatStore, type ChatMessage as ChatStoreMessage } from '@/stores/chat_store.js';
import { useAuthStore } from '@/stores/auth_store.js';
import { documentService } from '@/services/DocumentService.js';

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

function decodeHtmlEntities(text: string): string {
  const doc = new DOMParser().parseFromString(text, 'text/html');
  return doc.body.textContent || '';
}

function stripHtmlToText(html: string): string {
  return decodeHtmlEntities(html.replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim());
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
      label: decodeHtmlEntities(h[1].trim()),
      text: stripHtmlToText(parts[i + 1].replace(/^[:\s–\-]+/, '')),
    }));
  }

  // Markdown mode: split on **Option X...** markers
  const mdParts = content.split(/\*{1,2}(Option [ABC][^*]*)\*{1,2}/i);
  if (mdParts.length >= 7) {
    return [
      { label: mdParts[1].trim(), text: decodeHtmlEntities(mdParts[2].trim()) },
      { label: mdParts[3].trim(), text: decodeHtmlEntities(mdParts[4].trim()) },
      { label: mdParts[5].trim(), text: decodeHtmlEntities(mdParts[6].trim()) },
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

// Slash-command → skill key mapping
const SKILL_SHORTCUTS: Record<string, string> = {
  '/social_post': 'social_post',
  '/write_comment': 'social_post',
  '/fact_check': 'fact_check',
  '/email': 'email_draft',
  '/email_draft': 'email_draft',
  '/summary': 'summary',
  '/summarize': 'summary',
};

// Skill commands for the autocomplete dropdown
const SKILL_COMMAND_LIST = [
  { command: '/social_post', description: 'Write a social media comment' },
  { command: '/fact_check', description: 'Fact check claims in this article' },
  { command: '/summary', description: 'Summarize this document' },
  { command: '/email_draft', description: 'Draft an email about this' },
];

const chatStore = useChatStore();
const authStore = useAuthStore();
const messages = ref<ChatMessage[]>([]);
const inputMessage = ref('');
const messagesContainer = ref<any>(null);
const loading = ref(false);
const isLoadingInitialMessage = ref(false); // Prevent duplicate calls
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

const STOP_WORDS = new Set(['the', 'and', 'for', 'that', 'this', 'with', 'you', 'are', 'not', 'have', 'from', 'but', 'can', 'will', 'what', 'all', 'one', 'has', 'more', 'about', 'they', 'our', 'out', 'was', 'were', 'been', 'being', 'would', 'could', 'should', 'also', 'into', 'than', 'then', 'when', 'where', 'which', 'while', 'how', 'each', 'other', 'there', 'their', 'these', 'those', 'some', 'such', 'just', 'only', 'very', 'most']);

function extractWordsFromText(text: string): string[] {
  // Strip HTML tags and entities
  const clean = text.replace(/<[^>]*>/g, ' ').replace(/&[^;]+;/g, ' ');
  // Match words with 4+ alpha chars (preserves original casing)
  const words = clean.match(/\b[a-zA-Z]{4,}\b/g) || [];
  return words.filter(w => !STOP_WORDS.has(w.toLowerCase()));
}

const vocabularyCache = ref<string[]>([]);
let lastVocabMessageCount = 0;

function rebuildVocabulary() {
  const wordSet = new Map<string, string>(); // lowercase -> original case
  for (const msg of messages.value) {
    if (msg.pending) continue; // skip streaming messages
    for (const word of extractWordsFromText(msg.content)) {
      const lower = word.toLowerCase();
      if (!wordSet.has(lower)) wordSet.set(lower, word);
      if (wordSet.size >= 2000) break; // cap vocabulary size
    }
    if (wordSet.size >= 2000) break;
  }
  vocabularyCache.value = Array.from(wordSet.values()).sort((a, b) => a.toLowerCase().localeCompare(b.toLowerCase()));
  lastVocabMessageCount = messages.value.filter(m => !m.pending).length;
}

const chatVocabulary = computed(() => {
  const finalized = messages.value.filter(m => !m.pending).length;
  if (finalized !== lastVocabMessageCount) {
    rebuildVocabulary();
  }
  return vocabularyCache.value;
});

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
    // Ensure store is on the correct session (no-op if already there)
    if (chatStore.activeSession?.id !== props.chatSessionId) {
      await chatStore.switchActiveSession(props.chatSessionId);
    }

    // Populate local messages from the active session's messages
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

    // Determine the effective document scope — from props or from the session itself
    const effectiveDocumentId = props.selectedDocumentId
      || (chatStore.activeSession?.scope_type === 'document' ? chatStore.activeSession.scope_id : null);

    // For document-scoped sessions, always prepend the document summary as the first message
    if (effectiveDocumentId) {
      try {
        const doc = await documentService.getDocument(effectiveDocumentId);
        if (doc && doc.ai_markdown_content) {
          const titleHtml = doc.title ? `<h3>${escapeHtml(doc.title)}</h3>` : '';
          const urlHtml = doc.url ? `<p style="font-size:0.85rem;color:#64748b;"><a href="${doc.url}" target="_blank" rel="noopener noreferrer">${doc.url}</a></p>` : '';
          const contentHtml = marked.parse(doc.ai_markdown_content) as string;
          messages.value.unshift({
            type: 'system',
            content: `${titleHtml}${urlHtml}${contentHtml}`,
          });
        }
      } catch (err) {
        console.warn('Failed to load document summary for chat:', err);
      }

      // Sync backend session scope if needed
      if (chatStore.activeSession &&
          (chatStore.activeSession.scope_type !== 'document' || chatStore.activeSession.scope_id !== effectiveDocumentId)) {
        await chatStore.updateSessionScope(props.chatSessionId, 'document', effectiveDocumentId);
      }
    }

    // Only show a greeting if there are no messages at all (no chat history, no document summary)
    if (messages.value.length === 0) {
      if (props.selectedEntityId) {
        messages.value.push({
          type: 'system',
          content: toParagraphHtml('Entity context active. How can I help you explore this topic?'),
          actions: [],
        });
      } else {
        // General chat — no document scope
        if (chatStore.activeSession && chatStore.activeSession.scope_type !== 'all_library') {
          await chatStore.updateSessionScope(props.chatSessionId, 'all_library', null);
        }
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
  
  let userMessageContent = inputMessage.value.trim();
  inputMessage.value = '';

  // Check for slash command at the start of the message
  let skill: string | undefined;
  const match = userMessageContent.match(/^(\/\w+)\s*/);
  if (match) {
    const cmd = match[1].toLowerCase();
    if (SKILL_SHORTCUTS[cmd]) {
      skill = SKILL_SHORTCUTS[cmd];
    }
  }

  try {
    loading.value = true;
    await chatStore.sendMessage(userMessageContent, props.chatSessionId, skill);
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
  padding: 1rem 1.5rem;
  display: flex;
  flex-direction: column;
  gap: 0.6rem;
  max-width: 900px;
  margin: 0 auto;
  width: 100%;
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
  padding: 0.7rem 1rem;
  border-radius: 14px;
  background: #ffffff;
  border: 1px solid #e2e8f0;
  box-shadow: 0 4px 8px rgba(15, 23, 42, 0.06);
  word-break: break-word;
  overflow-wrap: anywhere;
}

.message-text {
  white-space: normal;
  line-height: 1.45;
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  color: #334155;
  font-size: 0.92rem;
}

.message-text p {
  margin: 0 0 0.6rem 0;
}

.message-text p:last-child {
  margin-bottom: 0;
}

.message-text h3 {
  margin: 0 0 0.4rem 0;
}

.message-text h4 {
  margin: 0.5rem 0 0.25rem 0;
}

.message-text ul {
  margin: 0.4rem 0 0.4rem 1.25rem;
  padding-left: 1.25rem;
  list-style-type: disc;
}

.message-text li {
  margin-bottom: 0.3rem;
}

.system-message {
  display: flex;
  gap: 0.85rem;
  align-items: flex-start;
  background: var(--blue-100);
  border-color: var(--blue-200);
}

/* Document summary messages should use full width */
.message-wrapper.system:first-child .message {
  max-width: 100%;
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
  margin: 0 0 0.6rem 0;
  line-height: 1.5;
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
  max-width: 900px;
  margin: 0 auto;
  width: 100%;
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
}

:deep(.chat-input-container .p-autocomplete-input::placeholder) {
  color: #64748b;
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

