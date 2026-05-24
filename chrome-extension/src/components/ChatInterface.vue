<template>
  <div class="chat-panel-container">
    <ScrollPanel
      class="chat-messages"
      ref="messagesContainer"
      @pointerover="handleMessagesPointerOver"
      @pointerout="handleMessagesPointerOut"
      @click="handleMessagesClick"
    >
      <div
        v-for="(message, index) in messages"
        :key="index"
        class="message-wrapper"
        :class="message.type"
      >
        <div v-if="message.type === 'system'" class="message system-message">
          <div v-if="message.id !== 'initial-summary'" class="message-icon">
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
              <div v-else class="message-text" v-html="renderAssistantContent(message.content, message.webCitations)"></div>
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
    <!-- Citation popover for inline source chips -->
    <div
      v-if="activeCitation"
      class="cite-popover"
      :style="{ left: citePopoverPos.left + 'px', top: citePopoverPos.top + 'px' }"
      @mouseenter="cancelCloseCitation"
      @mouseleave="closeCitation"
    >
      <a
        class="cite-popover-link"
        :href="activeCitation.url"
        target="_blank"
        rel="noopener noreferrer"
      >
        <div class="cite-popover-domain">
          <img
            v-if="activeCitation.domain"
            :src="`https://www.google.com/s2/favicons?domain=${activeCitation.domain}&sz=32`"
            class="cite-popover-favicon"
            alt=""
            @error="(e) => (e.target.style.display = 'none')"
          />
          <span>{{ activeCitation.domain || 'source' }}</span>
        </div>
        <div class="cite-popover-title">{{ activeCitation.title || activeCitation.url }}</div>
        <div v-if="activeCitation.snippet" class="cite-popover-snippet">{{ activeCitation.snippet }}</div>
      </a>
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
    default: '1.125rem'
  }
});

const emit = defineEmits(['session-invalid']);

const messages = ref([]);
const inputMessage = ref('');
const messagesContainer = ref(null);
const loading = ref(false);
const copiedLabel = ref(null);

// HTML attribute escape — used by the chip substitution below.
// Collapse ALL whitespace FIRST: a newline inside an attribute value breaks
// marked.js's HTML tokenizer mid-tag and the whole <span> renders as text.
const escAttr = (value) =>
  (value || '')
    .replace(/\s+/g, ' ')
    .replace(/&/g, '&amp;')
    .replace(/"/g, '&quot;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .trim();

// Replace <source web_id="cite-X"/> markers (any whitespace/closing variant)
// with a styled chip span. data-* attrs carry everything the popover needs;
// while citations are still streaming the chip renders in a loading state.
const renderCiteMarkers = (text, citations) => {
  if (!text) return '';
  const byId = {};
  for (const c of citations || []) byId[c.id] = c;
  return text.replace(
    /<source\s+web_id=["']([^"']+)["']\s*\/?>(\s*<\/source>)?/gi,
    (_m, citeId) => {
      const c = byId[citeId];
      const label = c?.domain || 'source';
      const loading = c ? '' : ' cite-chip--loading';
      return (
        `<span class="cite-chip${loading}" tabindex="0"` +
        ` data-cite-id="${escAttr(citeId)}"` +
        ` data-title="${escAttr(c?.title || '')}"` +
        ` data-url="${escAttr(c?.url || '')}"` +
        ` data-domain="${escAttr(c?.domain || '')}"` +
        ` data-snippet="${escAttr(c?.snippet || '')}">${escAttr(label)}</span>`
      );
    }
  );
};

// Render assistant markdown through marked. Legacy stored messages were
// saved as mixed HTML (<p>...</p><ul>...), so first strip the <p> wrappers
// the same way the web app does — otherwise marked treats the block as raw
// HTML and swallows any following markdown (e.g. ### headings after </ul>).
const renderAssistantContent = (text, citations) => {
  if (!text) return '';
  let cleaned = text
    .replace(/<p>/gi, '')
    .replace(/<\/p>/gi, '\n\n')
    .trim();
  // Substitute cite markers BEFORE markdown parsing so marked doesn't try
  // to interpret the attribute content as anything special.
  cleaned = renderCiteMarkers(cleaned, citations);
  return marked.parse(cleaned, { async: false });
};

// --- Citation chip popover (event-delegated) --------------------------------
const activeCitation = ref(null);
const citePopoverPos = ref({ left: 0, top: 0 });
let citeCloseTimer = null;

const findCitationById = (citeId) => {
  for (const m of messages.value) {
    const found = m.webCitations?.find((c) => c.id === citeId);
    if (found) return found;
  }
  return null;
};

const openCitationFor = (el) => {
  if (citeCloseTimer != null) {
    clearTimeout(citeCloseTimer);
    citeCloseTimer = null;
  }
  const id = el.getAttribute('data-cite-id') || '';
  const fromMap = findCitationById(id);
  const c = fromMap || {
    id,
    title: el.getAttribute('data-title') || '',
    url: el.getAttribute('data-url') || '',
    domain: el.getAttribute('data-domain') || '',
    snippet: el.getAttribute('data-snippet') || '',
  };
  if (!c.url && !c.title) return;
  const rect = el.getBoundingClientRect();
  const POPOVER_WIDTH = 288;
  const margin = 8;
  const left = Math.min(
    Math.max(margin, rect.left),
    window.innerWidth - POPOVER_WIDTH - margin,
  );
  citePopoverPos.value = { left, top: rect.bottom + 6 };
  activeCitation.value = c;
};

const closeCitation = () => {
  if (citeCloseTimer != null) clearTimeout(citeCloseTimer);
  citeCloseTimer = setTimeout(() => {
    activeCitation.value = null;
    citeCloseTimer = null;
  }, 120);
};

const cancelCloseCitation = () => {
  if (citeCloseTimer != null) {
    clearTimeout(citeCloseTimer);
    citeCloseTimer = null;
  }
};

const handleMessagesPointerOver = (e) => {
  const target = e.target?.closest?.('.cite-chip');
  if (target) openCitationFor(target);
};

const handleMessagesPointerOut = (e) => {
  const related = e.relatedTarget;
  if (related && related.closest?.('.cite-popover, .cite-chip')) return;
  closeCitation();
};

const handleMessagesClick = (e) => {
  const target = e.target?.closest?.('.cite-chip');
  if (target) {
    e.preventDefault();
    openCitationFor(target);
  }
};

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
        // Title is rendered by the parent panel header — don't repeat it here.

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

    const adoptPlaceholder = () => {
        if (message) return;
        const lastMessage = messages.value[messages.value.length - 1];
        if (lastMessage && lastMessage.type === 'system' && lastMessage.pending) {
            message = lastMessage;
            message.id = message_id;
            message.content = '';
        }
    };

    if (type === 'token') {
        adoptPlaceholder();
        if (message) {
            message.content += content || '';
            scrollToBottom();
        }
    } else if (type === 'content') {
        // Research path one-shot — replace content rather than append.
        adoptPlaceholder();
        if (message) {
            message.content = content || '';
            scrollToBottom();
        }
    } else if (type === 'draft_replace') {
        if (message) {
            message.content = '';
            message.statusText = 'Refining response...';
        }
        scrollToBottom();
    } else if (type === 'status') {
        if (message) {
            message.statusText = content || '';
        }
    } else if (type === 'done') {
        // End-of-stream + final {entity_ids, document_ids, web_citations}.
        if (message) {
            message.pending = false;
            message.commentOptions = parseCommentOptions(message.content);
            message.webCitations = data.web_citations || [];
        }
        loading.value = false;
    } else if (type === 'error') {
        if (message) {
            message.content += `\n[Error: ${content}]`;
            message.pending = false;
        }
        loading.value = false;
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
    '/social_post': 'write_social_media_post',
    '/write_post': 'write_social_media_post',
    '/write_social_media_post': 'write_social_media_post',
    '/write_comment': 'write_social_media_comment',
    '/write_social_media_comment': 'write_social_media_comment',
    '/fact_check': 'fact_check',
    '/email': 'email_draft',
    '/email_draft': 'email_draft',
    '/summary': 'summary',
    '/summarize': 'summary',
    '/research': 'research',
};

// Skill commands for the autocomplete dropdown
const SKILL_COMMAND_LIST = [
    { command: '/research', description: 'Multi-agent web research (saves sources to your library)' },
    { command: '/write_post', description: 'Write a social media post from this article' },
    { command: '/write_comment', description: 'Write a comment on this social media post' },
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
  padding: 0.5rem 1.75rem;
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

/* System messages render long markdown (bullet lists, paragraphs) and
   were running visually flush with the right edge despite the parent's
   28px padding. Cap them tighter so the bubble itself stops well short
   of the panel edge, regardless of panel width. */
.message-wrapper.system .message {
  max-width: 82%;
}

.message-text {
  line-height: 1.7;
  font-size: 22px;
  font-family: 'Source Sans 3', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  color: #292524;
  letter-spacing: 0.01em;
}

:deep(.message-text h2) {
    font-size: 1.4em;
    font-weight: 700;
    margin: 1.5em 0 0.5em 0;
    color: #1c1917;
}
:deep(.message-text h3) {
    font-size: 1.25em;
    font-weight: 700;
    margin: 1.25em 0 0.4em 0;
    color: #1c1917;
}
:deep(.message-text h4) {
    font-size: 1.125em;
    font-weight: 600;
    margin: 1em 0 0.3em 0;
    color: #1c1917;
}
:deep(.message-text p) {
    margin: 0 0 1em 0;
    line-height: 1.7;
}
:deep(.message-text p:last-child) {
    margin-bottom: 0;
}
:deep(.message-text ul),
:deep(.message-text ol) {
    margin: 0.5em 0 1em 0;
    padding-left: 1.5em;
}
:deep(.message-text ul) {
    list-style-type: disc;
}
:deep(.message-text li) {
    margin-bottom: 0.5em;
    line-height: 1.65;
}
:deep(.message-text strong) {
    font-weight: 700;
}
:deep(.message-text a) {
    color: #b45309;
    text-decoration: underline;
    text-decoration-color: rgba(180, 83, 9, 0.3);
}
:deep(.message-text a:hover) {
    text-decoration-color: rgba(180, 83, 9, 0.8);
}
:deep(.message-text code) {
    background: #f5f5f4;
    padding: 0.15em 0.35em;
    border-radius: 4px;
    font-size: 0.9em;
    font-family: 'Roboto Mono', ui-monospace, SFMono-Regular, Menlo, monospace;
}
:deep(.message-text blockquote) {
    border-left: 3px solid #d6d3d1;
    padding-left: 1em;
    margin: 0.75em 0;
    color: #57534e;
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

/* --- Web citation chips (inline source pills) ------------------------------ */
.message-content :deep(.cite-chip) {
  display: inline-flex;
  align-items: center;
  padding: 0 0.45rem;
  margin: 0 0.15rem;
  font-size: 0.72rem;
  line-height: 1.2;
  height: 1.25rem;
  border-radius: 999px;
  background: #eef2ff;
  color: #3730a3;
  border: 1px solid #c7d2fe;
  vertical-align: baseline;
  cursor: pointer;
  white-space: nowrap;
  max-width: 12rem;
  overflow: hidden;
  text-overflow: ellipsis;
  transition: background 0.15s, border-color 0.15s;
}

.message-content :deep(.cite-chip:hover),
.message-content :deep(.cite-chip:focus) {
  background: #e0e7ff;
  border-color: #a5b4fc;
  outline: none;
}

.message-content :deep(.cite-chip--loading) {
  background: #f1f5f9;
  color: #64748b;
  border-color: #e2e8f0;
}

.cite-popover {
  position: fixed;
  z-index: 1000;
  width: 18rem;
  max-width: 90vw;
  background: #ffffff;
  border: 1px solid #e2e8f0;
  border-radius: 0.5rem;
  box-shadow: 0 8px 24px rgba(15, 23, 42, 0.12);
  padding: 0.625rem 0.75rem;
  font-size: 0.8rem;
  color: #0f172a;
}

.cite-popover-link {
  color: inherit;
  text-decoration: none;
  display: block;
}

.cite-popover-domain {
  display: flex;
  align-items: center;
  gap: 0.375rem;
  font-size: 0.7rem;
  color: #64748b;
  margin-bottom: 0.25rem;
}

.cite-popover-favicon {
  width: 14px;
  height: 14px;
  border-radius: 3px;
}

.cite-popover-title {
  font-weight: 500;
  line-height: 1.3;
  margin-bottom: 0.25rem;
}

.cite-popover-snippet {
  color: #475569;
  font-size: 0.72rem;
  line-height: 1.4;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
</style>
