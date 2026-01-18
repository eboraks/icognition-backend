<template>
  <div class="typed-chat-input-wrapper">
    <div class="layers-container">
      <!-- Ghost Layer (Background) -->
      <div class="layer ghost-layer" ref="ghostLayer">
        <span class="invisible-content">{{ internalValue }}</span><span v-if="internalValue && internalValue.length >= 3" class="suggestion-content">{{ suggestion }}</span>
      </div>

      <!-- Input Layer (Foreground) -->
      <textarea
        ref="inputField"
        v-model="internalValue"
        :placeholder="placeholder"
        :disabled="disabled"
        @input="onInput"
        @keydown="onKeydown"
        @scroll="syncScroll"
        class="layer input-layer"
        spellcheck="false"
        rows="1"
      ></textarea>
    </div>
  </div>
</template>

<script setup>
import { ref, watch, onMounted, nextTick } from 'vue';

const props = defineProps({
  modelValue: String,
  placeholder: String,
  disabled: Boolean,
  isExtension: {
    type: Boolean,
    default: false
  },
  sessionId: [Number, String],
  context: String
});

const emit = defineEmits(['update:modelValue', 'send']);

const internalValue = ref(props.modelValue);
const suggestion = ref('');
const inputField = ref(null);
const ghostLayer = ref(null);
let debounceTimer = null;

// Keep internal value in sync with modelValue
watch(() => props.modelValue, (newVal) => {
  if (newVal !== internalValue.value) {
    internalValue.value = newVal;
    nextTick(() => {
        autoResize();
        syncScroll();
    });
  }
});

watch(internalValue, (newVal) => {
  emit('update:modelValue', newVal);
});

const onInput = () => {
  suggestion.value = '';
  clearTimeout(debounceTimer);

  if (internalValue.value.length >= 3 && props.sessionId) {
    debounceTimer = setTimeout(() => {
      fetchSuggestion();
    }, 400);
  }
  
  autoResize();
  syncScroll();
};

const fetchSuggestion = async () => {
  if (!internalValue.value || internalValue.value.length < 3) return;
  
  try {
    if (props.isExtension && typeof chrome !== 'undefined' && chrome.runtime) {
      chrome.runtime.sendMessage(
        { 
          name: 'get-chat-suggestion', 
          data: { 
            text: internalValue.value, 
            sessionId: props.sessionId,
            context: props.context
          } 
        },
        (response) => {
          if (response && response.success) {
            // Check if input still justifies a suggestion to prevent race conditions
            if (internalValue.value && internalValue.value.length >= 3) {
                suggestion.value = response.data.prediction;
                nextTick(syncScroll);
            }
          }
        }
      );
    } else {
        // Web app path
        const response = await fetch(`/api/v1/chat/sessions/${props.sessionId}/suggest`, {
            method: 'POST',
            headers: { 
                'Content-Type': 'application/json',
                // Authorization header might be needed if not handled by cookies/session
            },
            body: JSON.stringify({ 
                text: internalValue.value, 
                session_id: props.sessionId,
                context: props.context
            })
        });
        if (response.ok) {
            const data = await response.json();
            // Check if input still justifies a suggestion to prevent race conditions
            if (internalValue.value && internalValue.value.length >= 3) {
                suggestion.value = data.prediction;
                nextTick(syncScroll);
            }
        }
    }
  } catch (err) {
    console.error("Type-ahead error:", err);
  }
};

const onKeydown = (e) => {
  if (e.key === 'Tab') {
    if (suggestion.value) {
      e.preventDefault();
      acceptSuggestion();
    }
  } else if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    emit('send');
    suggestion.value = '';
  }
};

const acceptSuggestion = () => {
  if (suggestion.value) {
    internalValue.value += suggestion.value;
    suggestion.value = '';
    nextTick(() => {
      autoResize();
      syncScroll();
      // Keep focus
      inputField.value.focus();
    });
  }
};

const syncScroll = () => {
  if (inputField.value && ghostLayer.value) {
    ghostLayer.value.scrollTop = inputField.value.scrollTop;
  }
};

const autoResize = () => {
  const el = inputField.value;
  if (el) {
    el.style.height = 'auto';
    const newHeight = Math.min(el.scrollHeight, 120); // Max height 120px
    el.style.height = newHeight + 'px';
    if (ghostLayer.value) {
        ghostLayer.value.style.height = newHeight + 'px';
    }
  }
};

onMounted(() => {
  autoResize();
});
</script>

<style scoped>
.typed-chat-input-wrapper {
  width: 100%;
  position: relative;
  display: flex;
  background: var(--surface-card);
}

.layers-container {
  position: relative;
  width: 100%;
  display: flex;
  align-items: flex-start;
}

.layer {
  width: 100%;
  padding: 8px 16px;
  font-family: 'Roboto Mono', monospace;
  font-size: 0.95rem;
  line-height: 1.5;
  box-sizing: border-box;
  margin: 0;
  white-space: pre-wrap;
  word-wrap: break-word;
}

.input-layer {
  background: transparent;
  border: 1px solid var(--surface-border, #d1d5db);
  border-radius: 20px;
  color: var(--text-color, #374151);
  z-index: 2;
  position: relative;
  resize: none;
  min-height: 38px;
  overflow-y: auto;
  transition: border-color 0.2s, box-shadow 0.2s;
}

.input-layer:focus {
  outline: none;
  border-color: var(--primary-color, #3b82f6);
  box-shadow: 0 0 0 1px var(--primary-color, #3b82f6);
}

.input-layer:disabled {
  background: var(--surface-100, #f3f4f6);
  cursor: not-allowed;
}

.ghost-layer {
  position: absolute;
  top: 0;
  left: 0;
  color: transparent;
  z-index: 1;
  pointer-events: none;
  border: 1px solid transparent;
  overflow-y: hidden;
  /* Match scroll behavior */
}

.invisible-content {
  color: transparent;
  /* Zero opacity can sometimes cause issues with text measurement in some browsers */
  /* but here we just need it to take up space */
}

.suggestion-content {
  color: var(--text-color-secondary, #9ca3af);
  opacity: 0.7;
}

/* Scrollbar styling for high-end feel */
.input-layer::-webkit-scrollbar {
  width: 4px;
}
.input-layer::-webkit-scrollbar-track {
  background: transparent;
}
.input-layer::-webkit-scrollbar-thumb {
  background: var(--surface-300, #d1d5db);
  border-radius: 10px;
}
</style>
