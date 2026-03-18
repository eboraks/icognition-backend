<template>
  <div class="typed-chat-input-wrapper">
    <!-- Slash-command dropdown -->
    <div v-if="showSlashMenu" class="slash-menu">
      <div
        v-for="(cmd, index) in filteredCommands"
        :key="cmd.command"
        class="slash-menu-item"
        :class="{ active: index === selectedCommandIndex }"
        @mousedown.prevent="selectCommand(cmd)"
        @mouseenter="selectedCommandIndex = index"
      >
        <span class="slash-cmd">{{ cmd.command }}</span>
        <span class="slash-desc">{{ cmd.description }}</span>
      </div>
    </div>
    <div class="layers-container">
      <!-- Ghost Layer (Background) -->
      <div class="layer ghost-layer" ref="ghostLayer">
        <span class="invisible-content">{{ internalValue }}</span><span v-if="suggestion" class="suggestion-content">{{ suggestion }}</span>
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
import { ref, computed, watch, onMounted, nextTick } from 'vue';

const props = defineProps({
  modelValue: String,
  placeholder: String,
  disabled: Boolean,
  sessionId: [Number, String],
  skillCommands: {
    type: Array,
    default: () => []
  },
  vocabulary: {
    type: Array,
    default: () => []
  }
});

const emit = defineEmits(['update:modelValue', 'send']);

const internalValue = ref(props.modelValue);
const suggestion = ref('');
const inputField = ref(null);
const ghostLayer = ref(null);
const selectedCommandIndex = ref(0);

// Slash-command menu logic
const showSlashMenu = computed(() => {
  if (!internalValue.value || !props.skillCommands.length) return false;
  return internalValue.value.startsWith('/') && !internalValue.value.includes(' ');
});

const filteredCommands = computed(() => {
  if (!showSlashMenu.value) return [];
  const typed = internalValue.value.toLowerCase();
  return props.skillCommands.filter(cmd =>
    cmd.command.toLowerCase().startsWith(typed)
  );
});

const selectCommand = (cmd) => {
  internalValue.value = cmd.command + ' ';
  selectedCommandIndex.value = 0;
  nextTick(() => {
    inputField.value?.focus();
    autoResize();
    syncScroll();
  });
};

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

const getWordCompletion = () => {
  const text = internalValue.value || '';
  if (!text || showSlashMenu.value || !props.vocabulary.length) {
    suggestion.value = '';
    return;
  }

  // Find the current word being typed (after last space)
  const lastSpaceIdx = text.lastIndexOf(' ');
  const currentWord = lastSpaceIdx === -1 ? text : text.substring(lastSpaceIdx + 1);

  // Need at least 3 chars in the current word to suggest
  if (currentWord.length < 3 || currentWord.startsWith('/')) {
    suggestion.value = '';
    return;
  }

  const lower = currentWord.toLowerCase();

  // Find first matching word from vocabulary (case-insensitive prefix match)
  const match = props.vocabulary.find(w =>
    w.toLowerCase().startsWith(lower) && w.toLowerCase() !== lower
  );

  if (match) {
    // Show only the remaining suffix of the matched word
    suggestion.value = match.substring(currentWord.length);
  } else {
    suggestion.value = '';
  }
};

const onInput = () => {
  suggestion.value = '';
  selectedCommandIndex.value = 0;

  getWordCompletion();

  autoResize();
  syncScroll();
};

const onKeydown = (e) => {
  // Slash-command menu navigation
  if (showSlashMenu.value && filteredCommands.value.length > 0) {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      selectedCommandIndex.value = (selectedCommandIndex.value + 1) % filteredCommands.value.length;
      return;
    }
    if (e.key === 'ArrowUp') {
      e.preventDefault();
      selectedCommandIndex.value = (selectedCommandIndex.value - 1 + filteredCommands.value.length) % filteredCommands.value.length;
      return;
    }
    if (e.key === 'Enter' || e.key === 'Tab') {
      e.preventDefault();
      selectCommand(filteredCommands.value[selectedCommandIndex.value]);
      return;
    }
    if (e.key === 'Escape') {
      e.preventDefault();
      internalValue.value = '';
      return;
    }
  }

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
    const scrollHeight = el.scrollHeight;
    const maxHeight = 120;
    const newHeight = Math.min(scrollHeight, maxHeight);
    el.style.height = newHeight + 'px';

    // Only show scrollbar if we've reached maxHeight and there's more content
    if (scrollHeight > maxHeight) {
      el.style.overflowY = 'auto';
    } else {
      el.style.overflowY = 'hidden';
    }

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
  flex-direction: column;
  background: var(--surface-card);
}

/* Slash-command menu */
.slash-menu {
  position: absolute;
  bottom: 100%;
  left: 0;
  right: 0;
  background: var(--surface-card, #fff);
  border: 1px solid var(--surface-border, #d1d5db);
  border-radius: 8px;
  box-shadow: 0 -4px 16px rgba(0, 0, 0, 0.12);
  margin-bottom: 4px;
  max-height: 180px;
  overflow-y: auto;
  z-index: 10;
}

.slash-menu-item {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.4rem 0.6rem;
  cursor: pointer;
  transition: background 0.1s;
}

.slash-menu-item:first-child {
  border-radius: 8px 8px 0 0;
}

.slash-menu-item:last-child {
  border-radius: 0 0 8px 8px;
}

.slash-menu-item.active {
  background: var(--primary-50, #eff6ff);
}

.slash-cmd {
  font-family: 'Roboto Mono', monospace;
  font-size: 0.82rem;
  font-weight: 600;
  color: var(--primary-color, #3b82f6);
  white-space: nowrap;
}

.slash-desc {
  font-size: 0.78rem;
  color: var(--text-color-secondary, #6b7280);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
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
  overflow-y: hidden;
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
