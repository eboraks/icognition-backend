<template>
  <div class="chat-panel-container">
    <div class="chat-messages-wrapper">
    <ScrollPanel class="chat-messages" ref="messagesContainer">
      <div
        v-for="(message, index) in messages"
        :key="index"
        class="message-wrapper"
        :class="message.type"
      >
        <div v-if="message.type === 'system'" class="message system-message">
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
    <!-- Scroll-to-bottom FAB -->
    <Transition name="fade">
      <button
        v-if="showScrollToBottom"
        class="scroll-to-bottom-btn"
        @click="scrollToBottom"
        aria-label="Scroll to bottom"
      >
        <i class="pi pi-arrow-down" />
      </button>
    </Transition>
    </div>
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
import { ref, computed, watch, nextTick, onMounted, onBeforeUnmount } from 'vue';
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

function renderMarkdown(text: string): string {
  if (!text) return ''
  // Strip <p> wrapper tags that the backend adds — they prevent marked from
  // parsing markdown inside them (e.g., <p>## Heading</p> stays as-is).
  // Convert <p>...</p> to plain text blocks separated by double newlines.
  let cleaned = text
    .replace(/<p>/gi, '')
    .replace(/<\/p>/gi, '\n\n')
    .trim()
  return marked.parse(cleaned, { async: false }) as string
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
  '/write_post': 'write_social_media_post',
  '/write_social_media_post': 'write_social_media_post',
  '/write_comment': 'write_social_media_comment',
  '/write_social_media_comment': 'write_social_media_comment',
  '/fact_check': 'fact_check',
  '/email': 'email_draft',
  '/email_draft': 'email_draft',
  '/summary': 'summary',
  '/summarize': 'summary',
};

// Skill commands for the autocomplete dropdown
const SKILL_COMMAND_LIST = [
  { command: '/write_post', description: 'Write a social media post from this article' },
  { command: '/write_comment', description: 'Write a comment on this social media post' },
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
const showScrollToBottom = ref(false);

function checkScrollPosition() {
  if (!messagesContainer.value) return;
  const scrollElement = messagesContainer.value.$el?.querySelector('.p-scrollpanel-content');
  if (!scrollElement) return;
  const threshold = 100;
  const distanceFromBottom = scrollElement.scrollHeight - scrollElement.scrollTop - scrollElement.clientHeight;
  showScrollToBottom.value = distanceFromBottom > threshold;
}

let scrollListener: (() => void) | null = null;

function attachScrollListener() {
  nextTick(() => {
    const scrollElement = messagesContainer.value?.$el?.querySelector('.p-scrollpanel-content');
    if (scrollElement && !scrollListener) {
      scrollListener = () => checkScrollPosition();
      scrollElement.addEventListener('scroll', scrollListener);
    }
  });
}

onMounted(() => {
  attachScrollListener();
});

onBeforeUnmount(() => {
  if (scrollListener) {
    const scrollElement = messagesContainer.value?.$el?.querySelector('.p-scrollpanel-content');
    if (scrollElement) {
      scrollElement.removeEventListener('scroll', scrollListener);
    }
  }
});

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
        checkScrollPosition();
      }
    }
  });
};

const scrollToTop = () => {
  nextTick(() => {
    if (messagesContainer.value) {
      const scrollElement = messagesContainer.value.$el?.querySelector('.p-scrollpanel-content');
      if (scrollElement) {
        scrollElement.scrollTop = 0;
        checkScrollPosition();
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
        const isUser = msg.senderId === authStore.currentUser?.uid;
        return {
          type: isUser ? 'user' : 'system',
          content: isUser ? msg.content : renderMarkdown(msg.content),
          actions: (msg as any).actions,
          resources: (msg as any).resources,
          pending: isPending,
          commentOptions: !isPending && !isUser ? parseCommentOptions(msg.content) : null,
        };
      });
    } else {
      messages.value = [];
    }

    // Show a greeting if no messages yet
    if (messages.value.length === 0) {
      messages.value.push({
        type: 'system',
        content: toParagraphHtml('How can I help you explore your knowledge?'),
        actions: [],
      });
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
        const isUser = msg.senderId === authStore.currentUser?.uid;
        return {
          type: (isUser ? 'user' : 'system') as 'user' | 'system',
          content: isUser ? msg.content : renderMarkdown(msg.content),
          actions: (msg as any).actions,
          resources: (msg as any).resources,
          pending: isPending,
          statusText: (msg as any).statusText,
          commentOptions: !isPending && !isUser ? parseCommentOptions(msg.content) : null,
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
        isLoadingInitialMessage.value = false;  // Reset guard so new session can load
        loadInitialMessage();
      }
    }, 100); // 100ms debounce
  },
  { immediate: true }
);

// Handle clicks on source info buttons (event delegation)
function onMessagesClick(event: Event) {
  const target = event.target as HTMLElement;
  const btn = target.closest('.source-info-btn') as HTMLElement | null;
  if (!btn) return;

  event.preventDefault();
  const docId = btn.dataset.docId;
  const docTitle = btn.dataset.docTitle;
  if (!docId || !docTitle) return;

  // Send a contextual follow-up question about this source
  inputMessage.value = `Tell me more about the source "${docTitle}" and how it relates to our conversation.`;
  sendMessage();
}

// Make the scroll content focusable so arrow keys work after clicking
onMounted(() => {
  nextTick(() => {
    const el = messagesContainer.value?.$el?.querySelector('.p-scrollpanel-content');
    if (el) {
      el.setAttribute('tabindex', '0');
      el.addEventListener('click', onMessagesClick);
    }
  });
});

onBeforeUnmount(() => {
  const el = messagesContainer.value?.$el?.querySelector('.p-scrollpanel-content');
  if (el) {
    el.removeEventListener('click', onMessagesClick);
  }
});
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
  height: 100%;
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
  outline: none;
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

/* Subtle separator between conversation turns */
.message-wrapper.system + .message-wrapper.user,
.message-wrapper.user + .message-wrapper.system {
  margin-top: 0.5rem;
  padding-top: 0.75rem;
  border-top: 1px solid #f1f5f9;
}

.message {
  max-width: min(640px, 85%);
  width: fit-content;
  padding: 0.7rem 1rem;
  border-radius: 14px;
  background: #ffffff;
  border: 1px solid #e2e8f0;
  box-shadow: 0 2px 6px rgba(15, 23, 42, 0.04);
  word-break: break-word;
  overflow-wrap: anywhere;
}

.message-text {
  white-space: normal;
  line-height: 1.7;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', sans-serif;
  color: #1e293b;
  font-size: var(--app-font-size, 15px);
  letter-spacing: -0.01em;
}

.message-text :deep(p) {
  margin: 0 0 1em 0;
}

.message-text :deep(p:last-child) {
  margin-bottom: 0;
}

.message-text :deep(h2) {
  font-size: 1.2em;
  font-weight: 700;
  margin: 1.5em 0 0.5em 0;
}

.message-text :deep(h3) {
  font-size: 1.1em;
  font-weight: 700;
  margin: 1.25em 0 0.4em 0;
}

.message-text :deep(h4) {
  font-size: 1.05em;
  font-weight: 600;
  margin: 1em 0 0.3em 0;
}

.message-text :deep(ul),
.message-text :deep(ol) {
  margin: 0.5em 0 1em 0;
  padding-left: 1.5em;
}

.message-text :deep(ul) {
  list-style-type: disc;
}

.message-text :deep(li) {
  margin-bottom: 0.4em;
  line-height: 1.65;
}

.message-text :deep(strong) {
  font-weight: 600;
}

.message-text :deep(a) {
  color: #2563eb;
  text-decoration: underline;
  text-decoration-color: rgba(37, 99, 235, 0.3);
}

.message-text :deep(a:hover) {
  text-decoration-color: rgba(37, 99, 235, 0.8);
}

.message-text :deep(code) {
  background: #f1f5f9;
  padding: 0.15em 0.35em;
  border-radius: 4px;
  font-size: 0.9em;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}

.message-text :deep(blockquote) {
  border-left: 3px solid #cbd5e1;
  padding-left: 1em;
  margin: 0.75em 0;
  color: #475569;
}

.system-message {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  align-items: flex-start;
  background: transparent;
  border: none;
  box-shadow: none;
  max-width: 100%;
  padding: 0.5rem 0;
  border-radius: 0;
  overflow-wrap: anywhere;
  word-break: break-word;
}

/* Document summary messages should use full width */
.message-wrapper.system:first-child .message {
  max-width: 100%;
}

.message-icon {
  flex-shrink: 0;
  width: 1.5rem;
  height: 1.5rem;
  display: flex;
  align-items: center;
  justify-content: center;
  opacity: 0.6;
}

.message-content {
  flex: 1;
  min-width: 0;
}

.message-content :deep(p) {
  margin: 0 0 1em 0;
  line-height: 1.7;
  color: #1e293b;
  font-size: inherit;
  letter-spacing: -0.01em;
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
  background: #f1f5f9;
  color: #1e293b;
  border: 1px solid #e2e8f0;
  box-shadow: none;
  border-radius: 18px 18px 4px 18px;
}

.user-message p {
  margin: 0;
  color: #1e293b;
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

/* Title link styling */
.message-text h3 a:hover {
  text-decoration: underline !important;
  color: #2563EB !important;
}

/* Source reference with info button */
:deep(.source-ref) {
  white-space: normal;
  display: inline;
}

:deep(.source-info-btn) {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 1.2rem;
  height: 1.2rem;
  margin-left: 0.2rem;
  padding: 0;
  border: none;
  border-radius: 50%;
  background: #e0f2fe;
  color: #0284c7;
  cursor: pointer;
  vertical-align: middle;
  transition: background 0.15s, color 0.15s;
  font-size: 0.75rem;
}

:deep(.source-info-btn:hover) {
  background: #0284c7;
  color: #ffffff;
}

:deep(.source-info-btn i) {
  font-size: 0.7rem;
}

/* Scroll-to-bottom button */
.chat-messages-wrapper {
  position: relative;
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

.scroll-to-bottom-btn {
  position: absolute;
  bottom: 1rem;
  left: 50%;
  transform: translateX(-50%);
  z-index: 10;
  width: 2.25rem;
  height: 2.25rem;
  border-radius: 50%;
  border: 1px solid #e2e8f0;
  background: #ffffff;
  box-shadow: 0 2px 8px rgba(15, 23, 42, 0.12);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #64748b;
  transition: all 0.2s;
}

.scroll-to-bottom-btn:hover {
  background: #f1f5f9;
  color: #334155;
  box-shadow: 0 4px 12px rgba(15, 23, 42, 0.18);
}

.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>

