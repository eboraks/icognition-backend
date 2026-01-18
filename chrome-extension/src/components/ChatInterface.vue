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
            <div v-if="message.pending" class="message-spinner">
              <ProgressSpinner strokeWidth="4" style="width: 32px; height: 32px" />
            </div>
            <div v-else class="message-text" v-html="message.content"></div>
            <!-- Actions and Resources removed for MVP simplicity in extension, can be added later -->
          </div>
        </div>
        <div v-else-if="message.type === 'user'" class="message user-message">
          <div class="message-text" v-html="message.content"></div>
        </div>
      </div>
    </ScrollPanel>
    <div class="chat-input-container" v-if="sessionId">
      <AutoComplete
        v-model="inputMessage"
        :suggestions="suggestions"
        @complete="onSearch"
        placeholder="Ask a follow-up question..."
        class="flex-1 w-full"
        @keydown.enter="sendMessage"
        :disabled="loading"
        :delay="100"
        :minLength="1"
        forceSelection="false"
      >
        <template #option="slotProps">
            <div class="flex align-items-center">
                <div>{{ slotProps.option }}</div>
            </div>
        </template>
      </AutoComplete>
      <Button
        icon="pi pi-send"
        rounded
        @click="sendMessage"
        :disabled="!inputMessage || !inputMessage.trim() || loading"
      />
    </div>
  </div>
</template>

<script setup>
import { ref, watch, nextTick, onMounted, onUnmounted } from 'vue';
import Button from 'primevue/button';
import AutoComplete from 'primevue/autocomplete';
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

const extractVocabulary = () => {
    if (!props.initialSummary) return;

    const textParts = [];
    if (props.initialSummary.summary) textParts.push(props.initialSummary.summary);
    if (props.initialSummary.bullet_points) textParts.push(...props.initialSummary.bullet_points);

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
    if (newSummary && (newSummary.summary || (newSummary.bullet_points && newSummary.bullet_points.length > 0))) {
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
                // Assuming backend format, we might need adjustments
            }));
            
            messages.value = fetchedMessages;
        }
    } catch (error) {
        console.error('Failed to load messages:', error);
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
        if (props.initialSummary.title) {
            content += `<h3 class="text-lg font-bold mb-3 border-bottom-1 border-200 pb-2">${escapeHtml(props.initialSummary.title)}</h3>`;
        }
        
        if (props.initialSummary.summary) {
            content += `<h4 class="font-semibold mb-1">Summary</h4><p class="mb-2">${formatUrlsAsLinks(props.initialSummary.summary)}</p>`;
        }
        if (props.initialSummary.bullet_points && props.initialSummary.bullet_points.length > 0) {
            content += `<h4 class="font-semibold mb-1 mt-1">Key Points</h4><ul class="pl-3 mt-1 list-disc">`;
            props.initialSummary.bullet_points.forEach(point => {
                content += `<li class="mb-1">${formatUrlsAsLinks(point)}</li>`;
            });
            content += `</ul>`;
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
    
    // Find message with this ID or create placeholder if it's the first chunk
    let message = messages.value.find(m => m.id === message_id);
    
    if (type === 'stream_chunk') {
        if (!message) {
             // It might be the placeholder we created with a temporary ID?
             // Actually, for simplicity, let's just append chunks to the last system message if it is pending
             const lastMessage = messages.value[messages.value.length - 1];
             if (lastMessage && lastMessage.type === 'system' && lastMessage.pending) {
                 message = lastMessage;
                 message.id = message_id; // Update ID
                 message.content = ''; // Clear spinner/placeholder empty content
                 message.pending = false; // It's no longer just "pending start", it's streaming
                 message.streaming = true;
             }
        }
        
        if (message) {
            message.content += content || '';
            scrollToBottom();
        }
    } else if (type === 'end_stream') {
        // Handled by chat-stream-end event usually, but sometimes data packet has type end_stream
        if (message) {
            message.streaming = false;
        }
        loading.value = false;
    } else if (type === 'error') {
        if (message) {
            message.content += `\n[Error: ${content}]`;
            message.streaming = false;
        }
        loading.value = false;
    }
};

const handleStreamEnd = (data) => {
    loading.value = false;
    // Ensure last message is not pending
    const lastMessage = messages.value[messages.value.length - 1];
    if (lastMessage) {
        lastMessage.pending = false;
        lastMessage.streaming = false;
    }
};

const handleStreamError = (data) => {
    console.error('Stream error:', data.error);
    loading.value = false;
    const lastMessage = messages.value[messages.value.length - 1];
    if (lastMessage) {
        lastMessage.pending = false;
        lastMessage.content += `<p class="text-red-500">Error: ${data.error}</p>`;
    }
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
        console.error('Error sending message:', error);
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


.chat-input-container {
  display: flex;
  padding: 0.75rem;
  border-top: 1px solid var(--surface-border);
  gap: 0.5rem;
  align-items: center;
  background: var(--surface-card);
}

:deep(.chat-input-container .p-autocomplete) {
  width: 100%;
}

:deep(.chat-input-container .p-autocomplete-input) {
  width: 100%;
  border-radius: 999px;
  padding-left: 1rem;
  font-size: 0.95rem;
}
</style>
