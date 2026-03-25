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
            <img src="/icons/icog_action_icon_32x32.png" alt="AI Icon" style="width: 2.25rem; height: 2.25rem; object-fit: contain;" />
          </div>
          <div class="message-content">
            <!-- Spinner: only while waiting before any content arrives -->
            <div v-if="message.pending && !message.content" class="message-spinner">
              <ProgressSpinner strokeWidth="4" style="width: 32px; height: 32px" />
            </div>
            <!-- Content: shown once we have any text (even mid-stream) -->
            <template v-if="!message.pending || message.content">
              <div v-if="message.commentOptions && !message.pending" class="comment-options">
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
                  <p class="comment-card-text" :style="{ fontSize: fontSize }">{{ option.text }}</p>
                </div>
              </div>
              <div v-else class="message-text" v-html="message.content"></div>
            </template>
            <!-- Status text: shown while pending (matches web app ChatPanel behaviour) -->
            <div v-if="message.pending && message.statusText" class="message-status">
                <i class="pi pi-spin pi-spinner" style="font-size: 0.8rem; margin-right: 0.5rem"></i>
                {{ message.statusText }}
            </div>
            <!-- Action suggestion buttons -->
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
            <!-- Referenced resources (collapsed by default) -->
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
        <div v-else-if="message.type === 'user'" class="message user-message">
          <div class="message-text" v-html="message.content"></div>
        </div>
      </div>
    </ScrollPanel>
    <div class="chat-input-container" v-if="sessionId">
      <div class="input-row">
        <TypedChatInput
          v-model="inputMessage"
          placeholder="Type / for skills, or ask a question..."
          :session-id="sessionId"
          :disabled="loading"
          :skill-commands="SKILL_COMMAND_LIST"
          :vocabulary="chatVocabulary"
          @send="sendMessage"
        />
        <Button
          icon="pi pi-send"
          rounded
          @click="sendMessage"
          :disabled="!inputMessage || !inputMessage.trim() || loading"
        />
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, nextTick, onMounted, onUnmounted } from 'vue';
import { marked } from 'marked';
import Button from 'primevue/button';
import TypedChatInput from './TypedChatInput.vue';
import ScrollPanel from 'primevue/scrollpanel';
import ProgressSpinner from 'primevue/progressspinner';

const props = defineProps({
  sessionId: {
    type: Number,
    required: true
  },
  initialSummary: {
    type: Object,
    default: null
  },
  fontSize: {
    type: String,
    default: '12px'
  }
});

const emit = defineEmits(['session-invalid']);

const messages = ref([]);
const inputMessage = ref('');
const messagesContainer = ref(null);
const loading = ref(false);
const copiedLabel = ref(null);

const decodeHtmlEntities = (text) => {
  const doc = new DOMParser().parseFromString(text, 'text/html');
  return doc.body.textContent || '';
};

const stripHtmlToText = (html) => {
  return decodeHtmlEntities(html.replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim());
};

const parseCommentOptions = (content) => {
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
};

const copyToClipboard = async (text, label) => {
  try {
    await navigator.clipboard.writeText(text);
    copiedLabel.value = label;
    setTimeout(() => { copiedLabel.value = null; }, 2000);
  } catch {
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

const STOP_WORDS = new Set(['the', 'and', 'for', 'that', 'this', 'with', 'you', 'are', 'not', 'have', 'from', 'but', 'can', 'will', 'what', 'all', 'one', 'has', 'more', 'about', 'they', 'our', 'out', 'was', 'were', 'been', 'being', 'would', 'could', 'should', 'also', 'into', 'than', 'then', 'when', 'where', 'which', 'while', 'how', 'each', 'other', 'there', 'their', 'these', 'those', 'some', 'such', 'just', 'only', 'very', 'most']);

function extractWordsFromText(text) {
  const clean = text.replace(/<[^>]*>/g, ' ').replace(/&[^;]+;/g, ' ');
  const words = clean.match(/\b[a-zA-Z]{4,}\b/g) || [];
  return words.filter(w => !STOP_WORDS.has(w.toLowerCase()));
}

const vocabularyCache = ref([]);
let lastVocabKey = '';

function rebuildVocabulary() {
  const wordSet = new Map(); // lowercase -> original case
  // Extract from initial summary
  if (props.initialSummary) {
    const parts = [props.initialSummary.summary, props.initialSummary.markdown_content, props.initialSummary.title].filter(Boolean);
    for (const part of parts) {
      for (const word of extractWordsFromText(part)) {
        const lower = word.toLowerCase();
        if (!wordSet.has(lower)) wordSet.set(lower, word);
      }
      if (wordSet.size >= 2000) break;
    }
  }
  // Extract from finalized chat messages only
  for (const msg of messages.value) {
    if (msg.pending || !msg.content) continue;
    for (const word of extractWordsFromText(msg.content)) {
      const lower = word.toLowerCase();
      if (!wordSet.has(lower)) wordSet.set(lower, word);
      if (wordSet.size >= 2000) break;
    }
    if (wordSet.size >= 2000) break;
  }
  vocabularyCache.value = Array.from(wordSet.values()).sort((a, b) => a.toLowerCase().localeCompare(b.toLowerCase()));
}

const chatVocabulary = computed(() => {
  const finalizedCount = messages.value.filter(m => !m.pending).length;
  const key = `${finalizedCount}-${!!props.initialSummary}`;
  if (key !== lastVocabKey) {
    lastVocabKey = key;
    rebuildVocabulary();
  }
  return vocabularyCache.value;
});

const escapeHtml = (unsafe) =>
  unsafe
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');

const toParagraphHtml = (content) => `<p>${escapeHtml(content)}</p>`;

const formatUrlsAsLinks = (text) => {
    if (!text) return text;
    // Simple URL regex - verify if this is sufficient or if we should import utility
    const urlRegex = /(https?:\/\/[^\s]+)/g;
    return text.replace(urlRegex, (url) => {
        return `<a href="${url}" target="_blank" class="text-primary-600 hover:underline">${url}</a>`;
    });
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

onMounted(() => {
    console.log('ChatInterface: mounted with sessionId:', props.sessionId, 'initialSummary:', props.initialSummary);
    loadMessages();
    
    // Listen for SSE messages from background
    chrome.runtime.onMessage.addListener(handleBackgroundMessage);
});

// Watch for sessionId changes to reload chat without unmounting/remounting
watch(() => props.sessionId, (newId, oldId) => {
    if (newId && newId !== oldId) {
        console.log('ChatInterface: sessionId changed, reloading messages:', newId);
        messages.value = [];
        loadMessages();
    }
});

// Watch for summary updates to inject content if it was previously empty
watch(() => props.initialSummary, (newSummary) => {
    if (newSummary && (newSummary.summary || newSummary.markdown_content)) {
        const hasSummary = messages.value.some(m => m.id === 'initial-summary');
        const summaryMsg = messages.value.find(m => m.id === 'initial-summary');
        
        // If we don't have a summary, or it's currently showing nothing,
        // or it's only showing the title but we now have full content
        const isPlaceholder = summaryMsg && !summaryMsg.content.includes('Summary') && !summaryMsg.content.includes('Key Points');
        
        if (!hasSummary || isPlaceholder) {
            console.log('ChatInterface: initialSummary refined or populated (from placeholder), updating message list');
            messages.value = messages.value.filter(m => m.id !== 'initial-summary');
            initChat();
        }
    }
}, { deep: true });

const loadMessages = async () => {
    console.log('ChatInterface: loadMessages for sessionId:', props.sessionId);
    loading.value = true;
    try {
        const response = await chrome.runtime.sendMessage({
            name: 'get-chat-messages',
            data: { sessionId: props.sessionId }
        });

        if (response && response.success) {
            console.log('ChatInterface: loaded', response.data.length, 'messages');
            const fetchedMessages = response.data.map(msg => ({
                id: msg.id,
                content: msg.content,
                type: msg.role === 'user' ? 'user' : 'system',
                statusText: '',
                commentOptions: msg.role !== 'user' ? parseCommentOptions(msg.content) : null,
            }));

            messages.value = fetchedMessages;
        } else if (response && !response.success) {
            // Session not found or not owned — tell parent to re-create
            console.log('ChatInterface: session invalid or not found, requesting re-creation');
            emit('session-invalid', props.sessionId);
        }
    } catch (error) {
        console.log('[ERROR]', 'Failed to load messages:', error);
    } finally {
        loading.value = false;
        // Always add summary as the very first message context
        initChat();
        scrollToBottom();
    }
};

// Initialize with summary
const initChat = () => {
    console.log('ChatInterface: initChat called, summary status:', !!props.initialSummary);
    if (props.initialSummary) {
        let content = '';
        // Always add title if available as a header to prevent blank state
        if (props.initialSummary.title && props.initialSummary.title.trim()) {
            content += `<h3 class="text-lg font-bold mb-3 border-bottom-1 border-200 pb-2">${escapeHtml(props.initialSummary.title)}</h3>`;
        }
        
        if (props.initialSummary.markdown_content) {
            content += `<h4 class="font-semibold mb-1 mt-1">Content</h4><div class="mt-1">${marked.parse(props.initialSummary.markdown_content)}</div>`;
        }
        
        if (content) {
             const summaryMsg = {
                type: 'system',
                content: content,
                id: 'initial-summary'
            };
            console.log('ChatInterface: injecting summary message');
            // Prepend summary
            messages.value.unshift(summaryMsg);
        } else {
             console.log('ChatInterface: summary content empty, skipping injection');
        }
    }
};

onUnmounted(() => {
    chrome.runtime.onMessage.removeListener(handleBackgroundMessage);
});

const handleBackgroundMessage = (request, sender, sendResponse) => {
    if (request.data && request.data.sessionId === props.sessionId) {
        if (request.name === 'chat-stream-chunk') {
            handleStreamChunk(request.data);
        } else if (request.name === 'chat-stream-end') {
            handleStreamEnd(request.data);
        } else if (request.name === 'chat-stream-error') {
            handleStreamError(request.data);
        }
    }
};

const handleStreamChunk = (data) => {
    const { type, content, message_id } = data;

    // Find message with this ID or fall back to the last pending system message
    let message = messages.value.find(m => m.id === message_id);

    if (type === 'stream_chunk') {
        if (!message) {
            const lastMessage = messages.value[messages.value.length - 1];
            if (lastMessage && lastMessage.type === 'system' && lastMessage.pending) {
                message = lastMessage;
                message.id = message_id;
                message.content = '';
                // Keep pending=true while streaming so status text keeps showing
                // (matches the web app ChatPanel where pending covers the whole wait)
            }
        }
        if (message) {
            message.content += content || '';
            scrollToBottom();
        }
    } else if (type === 'end_stream') {
        if (message) {
            message.pending = false;
            message.commentOptions = parseCommentOptions(message.content);
        }
        loading.value = false;
    } else if (type === 'error') {
        if (message) {
            message.content += `\n[Error: ${content}]`;
            message.pending = false;
        }
        loading.value = false;
    } else if (type === 'agent_status') {
        if (message) {
            message.statusText = content || '';
        }
    }
};

const handleStreamEnd = (data) => {
    loading.value = false;
    const lastMessage = messages.value[messages.value.length - 1];
    if (lastMessage) {
        lastMessage.pending = false;
    }
};

const handleStreamError = (data) => {
    console.log('[ERROR]', 'Stream error:', data.error);
    loading.value = false;
    const lastMessage = messages.value[messages.value.length - 1];
    if (lastMessage) {
        lastMessage.pending = false;
        lastMessage.content += `<p class="text-red-500">Error: ${data.error}</p>`;
    }
};

const handleActionClick = (action) => {
    if (!action.label || loading.value) return;
    inputMessage.value = action.label;
    sendMessage();
};

// Slash-command → skill key mapping
const SKILL_SHORTCUTS = {
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

const sendMessage = async () => {
    if (!inputMessage.value || !inputMessage.value.trim() || loading.value) return;

    let content = inputMessage.value.trim();

    // Check for slash command at the start of the message
    let skill = null;
    const match = content.match(/^(\/\w+)\s*/);
    if (match) {
        const cmd = match[1].toLowerCase();
        if (SKILL_SHORTCUTS[cmd]) {
            skill = SKILL_SHORTCUTS[cmd];
        }
    }

    // Clear input
    inputMessage.value = '';

    // Add user message
    messages.value.push({
        type: 'user',
        content: toParagraphHtml(content),
        id: Date.now().toString()
    });

    // Add placeholder for AI response
    messages.value.push({
        type: 'system',
        content: '',
        pending: true,
        id: 'temp-' + Date.now()
    });

    loading.value = true;
    scrollToBottom();

    try {
        const response = await chrome.runtime.sendMessage({
            name: 'send-chat-message',
            data: {
                sessionId: props.sessionId,
                content: content
            }
        });

        if (response && response.success) {
            const messageId = response.data.id || response.data.data.id;
             // Start streaming (with optional skill override)
             chrome.runtime.sendMessage({
                 name: 'stream-chat-response',
                 data: {
                     sessionId: props.sessionId,
                     messageId: messageId,
                     skill: skill
                 }
             });
        } else {
             // Check if session is invalid (404 from backend)
             if (response.error && (response.error.includes('404') || response.error.includes('not found') || response.error.includes('Not Found'))) {
                 console.log('ChatInterface: session not found on send, requesting re-creation');
                 emit('session-invalid', props.sessionId);
                 return;
             }
             throw new Error(response.error || 'Failed to send message');
        }
    } catch (error) {
        console.log('[ERROR]', 'Error sending message:', error);
        loading.value = false;
        // Update placeholder with error
        const lastMessage = messages.value[messages.value.length - 1];
        if (lastMessage) {
            lastMessage.pending = false;
            lastMessage.content = `<p class="text-red-500">Error: ${error.message}</p>`;
        }
    }
};

</script>

<style scoped>
.chat-panel-container {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  overflow: hidden;
  background: var(--surface-0);
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
  padding: 0.5rem;
  display: flex;
  flex-direction: column;
  gap: 0.5rem; /* Reduced from 1rem */
}

.message-wrapper {
  display: flex;
  width: 100%;
}

.message-wrapper.user {
  justify-content: flex-end;
}

.message-wrapper.system {
  justify-content: flex-start;
}

.message-wrapper.system + .message-wrapper.user,
.message-wrapper.user + .message-wrapper.system {
  margin-top: 0.35rem;
  padding-top: 0.5rem;
  border-top: 1px solid var(--surface-border);
}

.message {
  max-width: 90%;
  width: fit-content;
  padding: 0.5rem 0.75rem;
  border-radius: 8px;
  background: var(--surface-card);
  border: 1px solid var(--surface-border);
  box-shadow: 0 1px 3px rgba(0,0,0,0.04);
  word-break: break-word;
  overflow-wrap: anywhere;
}

.message-text {
  /* Dynamic font size applied via root variable or inline style */
  line-height: 1.4;
  font-size: v-bind(fontSize); /* Bound to prop */
  font-family: 'Roboto Mono', monospace;
}

:deep(.message-text h4) {
    margin-top: 0;
    margin-bottom: 0.5rem;
    color: var(--text-color);
}
:deep(.message-text p) {
    margin: 0 0 0.5rem 0;
}
:deep(.message-text p:last-child) {
    margin-bottom: 0;
}
:deep(.message-text ul) {
    margin: 0.5rem 0 0.5rem 1.25rem;
    padding-left: 0;
    list-style-type: disc;
}
:deep(.message-text li) {
    margin-bottom: 0.25rem;
}
:deep(.message-text a) {
    color: var(--primary-600);
    text-decoration: underline;
}


.system-message {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
  align-items: flex-start;
  background: transparent;
  border: none;
  box-shadow: none;
  max-width: 100%;
  padding: 0.4rem 0;
  border-radius: 0;
}

.message-icon {
  flex-shrink: 0;
  width: 1.25rem;
  height: 1.25rem;
  display: flex;
  align-items: center;
  justify-content: center;
  opacity: 0.5;
}
.message-icon img {
    width: 100% !important;
    height: 100% !important;
}

.message-content {
  flex: 1;
  min-width: 0;
}

.message-spinner {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 2rem;
}

.message-status {
    font-size: 0.8rem;
    color: var(--text-color-secondary);
    margin-top: 0.5rem;
    display: flex;
    align-items: center;
    font-style: italic;
}

.user-message {
  background: #f1f5f9;
  color: #1e293b;
  border: 1px solid #e2e8f0;
  border-radius: 12px 12px 2px 12px;
  box-shadow: none;
}

:deep(.user-message .message-text),
:deep(.user-message .message-text p) {
  color: #1e293b;
}


.action-buttons {
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem;
  margin-top: 0.6rem;
}

:deep(.action-button) {
  border-radius: 999px;
  padding-inline: 0.9rem;
  padding-block: 0.3rem;
  font-size: 0.8rem;
}

.resources-section {
  margin-top: 0.6rem;
  font-size: 0.8rem;
  background: var(--surface-100, var(--surface-ground));
  border: 1px dashed var(--surface-border);
  border-radius: 0.6rem;
  padding: 0.5rem 0.75rem;
}

.resources-section details {
  cursor: pointer;
}

.resources-section summary {
  font-weight: 600;
  color: var(--text-color);
}

.resources-section ul {
  list-style: none;
  padding-left: 0;
  margin: 0.4rem 0 0 0;
}

.resources-section li {
  padding: 0.2rem 0;
  color: var(--text-color-secondary);
}

.chat-input-container {
  display: flex;
  flex-direction: column;
  padding: 0.75rem;
  border-top: 1px solid var(--surface-border);
  gap: 0.4rem;
  background: var(--surface-card);
}

.input-row {
  display: flex;
  gap: 0.5rem;
  align-items: center;
}

:deep(.chat-input-container .p-autocomplete) {
  width: 100%;
}

:deep(.chat-input-container .p-autocomplete-input) {
  width: 100%;
  border-radius: 999px;
  padding-left: 1rem;
  font-size: 0.95rem;
  font-family: 'Roboto Mono', monospace;
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
  width: 1.1rem;
  height: 1.1rem;
  margin-left: 0.15rem;
  padding: 0;
  border: none;
  border-radius: 50%;
  background: #e0f2fe;
  color: #0284c7;
  cursor: pointer;
  vertical-align: middle;
  transition: background 0.15s;
  font-size: 0.7rem;
}

:deep(.source-info-btn:hover) {
  background: #0284c7;
  color: #ffffff;
}

:deep(.source-info-btn i) {
  font-size: 0.65rem;
}

/* Comment option cards (Phase 6.2) */
.comment-options {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  width: 100%;
}

.comment-card {
  background: var(--surface-0);
  border: 1px solid var(--surface-border);
  border-radius: 8px;
  padding: 0.5rem 0.75rem;
  transition: box-shadow 0.15s;
}

.comment-card:hover {
  box-shadow: 0 2px 6px rgba(15, 23, 42, 0.1);
}

.comment-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 0.35rem;
}

.comment-option-label {
  font-weight: 600;
  font-size: 0.82rem;
  color: var(--primary-600, var(--primary-color));
}

.copy-btn {
  flex-shrink: 0;
  opacity: 0.6;
  transition: opacity 0.15s;
}

.copy-btn:hover {
  opacity: 1;
}

.copy-btn.copied {
  opacity: 1;
}

:deep(.copy-btn.copied .p-button-icon) {
  color: #22c55e !important;
}

.comment-card-text {
  line-height: 1.5;
  color: var(--text-color);
  margin: 0;
  font-family: 'Roboto Mono', monospace;
  white-space: pre-wrap;
}
</style>
