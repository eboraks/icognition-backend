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
          :is-extension="true"
          :session-id="sessionId"
          :disabled="loading"
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
import { ref, watch, nextTick, onMounted, onUnmounted } from 'vue';
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

const messages = ref([]);
const inputMessage = ref('');
const messagesContainer = ref(null);
const loading = ref(false);
const suggestions = ref([]);
const allVocabulary = ref([]);
const copiedLabel = ref(null);

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

const extractVocabulary = () => {
    if (!props.initialSummary) return;

    const textParts = [];
    if (props.initialSummary.summary) textParts.push(props.initialSummary.summary);
    if (props.initialSummary.markdown_content) textParts.push(props.initialSummary.markdown_content);

    // Join all text, remove Markdown/HTML-like chars if simple ones exist (mostly raw text expected)
    const text = textParts.join(' ').toLowerCase();
    
    // Simple regex for words >= 3 chars
    const words = text.match(/\b[a-z]{3,}\b/g) || [];
    
    // Basic stop words to filter out noise
    const stopWords = new Set(['the', 'and', 'for', 'that', 'this', 'with', 'you', 'are', 'not', 'have', 'from', 'but', 'can', 'will', 'what', 'all', 'one', 'has', 'more', 'about', 'they', 'our', 'out', 'key', 'points', 'summary', 'inc', 'ltd', 'com']);
    
    const uniqueWords = new Set();
    words.forEach(word => {
        if (!stopWords.has(word)) {
            uniqueWords.add(word);
        }
    });
    
    allVocabulary.value = Array.from(uniqueWords).sort();
};

const onSearch = (event) => {
    // If empty input, show nothing or all (let's show nothing to be cleaner)
    if (!event.query || !event.query.trim()) {
        suggestions.value = [];
        return;
    }

    const query = event.query.trim().toLowerCase();
    // Find the last word being typed
    const lastSpaceIndex = query.lastIndexOf(' ');
    let prefix = '';
    let term = query;
    
    if (lastSpaceIndex !== -1) {
        prefix = query.substring(0, lastSpaceIndex + 1);
        term = query.substring(lastSpaceIndex + 1);
    }
    
    // If the last term is empty (trailing space), we might want to show all vocabulary
    // OR show nothing until they start typing the next word.
    // Let's require at least 1 char for the current word to suggest
    if (!term) {
        suggestions.value = [];
        return;
    }
    
    term = term.toLowerCase();
    
    const matches = allVocabulary.value.filter(word => 
        word.toLowerCase().startsWith(term)
    );
    
    // Construct suggestions that preserve the user's typed prefix
    suggestions.value = matches.map(word => prefix + word);
};

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
        
        // Extract vocabulary for autocomplete
        extractVocabulary();

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

const writeComment = () => {
    inputMessage.value = 'Write a comment on this post: ';
};

const sendMessage = async () => {
    if (!inputMessage.value || !inputMessage.value.trim() || loading.value) return;

    const content = inputMessage.value.trim();
    
    // Clear input and suggestions
    inputMessage.value = '';
    suggestions.value = [];
    
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
             // Start streaming
             chrome.runtime.sendMessage({
                 name: 'stream-chat-response',
                 data: {
                     sessionId: props.sessionId,
                     messageId: messageId
                 }
             });
        } else {
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

.message {
  max-width: 90%; /* Increased from 85% */
  width: fit-content;
  padding: 0.5rem 0.75rem; /* Reduced from 0.75rem 1rem */
  border-radius: 8px; /* Slightly tighter corner */
  background: var(--surface-card);
  border: 1px solid var(--surface-border);
  box-shadow: 0 2px 4px rgba(0,0,0,0.05); /* Lighter shadow */
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
  gap: 0.5rem; /* Reduced from 0.75rem */
  align-items: flex-start;
  background: var(--surface-50); 
  border-color: var(--surface-200);
}

.message-icon {
  flex-shrink: 0;
  width: 2rem;
  height: 2rem;
  display: flex;
  align-items: center;
  justify-content: center;
}
.message-icon img {
    width: 100% !important;
    height: 100% !important;
}

.message-content {
  flex: 1;
  min-width: 0; /* Prevent overflow */
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
  background: var(--primary-color, #3497BE);
  color: #fff; /* Explicit white for user message text */
  border: none;
  margin-right: 1rem; /* Added padding/margin on the right */
}

:deep(.user-message .message-text), 
:deep(.user-message .message-text p) {
  color: #fff;
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

.quick-actions-row {
  display: flex;
  gap: 0.4rem;
}

:deep(.quick-action-btn) {
  border-radius: 999px;
  padding-inline: 0.75rem;
  padding-block: 0.25rem;
  font-size: 0.78rem;
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
