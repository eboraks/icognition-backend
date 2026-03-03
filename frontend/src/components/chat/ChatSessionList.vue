<template>
  <div class="flex flex-column h-full chat-session-list">
    <!-- New Chat button -->
    <div class="p-2 border-bottom-1 surface-border">
      <Button
        label="New Chat"
        icon="pi pi-plus"
        size="small"
        class="w-full"
        @click="$emit('create')"
      />
    </div>

    <!-- Session list -->
    <div class="flex-1 overflow-y-auto">
      <div
        v-for="session in sessions"
        :key="session.id"
        class="session-row flex align-items-center gap-2 p-2 cursor-pointer border-bottom-1 surface-border"
        :class="{ 'surface-100': session.id === activeSessionId }"
        @click="$emit('select', session.id)"
      >
        <!-- Scope badge -->
        <span class="scope-badge text-sm flex-shrink-0" :title="getScopeBadgeTitle(session.scope_type)">
          {{ getScopeBadge(session.scope_type) }}
        </span>

        <!-- Session title -->
        <span class="flex-1 text-sm text-overflow-ellipsis overflow-hidden white-space-nowrap" :title="session.title">
          {{ session.title || 'New Chat' }}
        </span>

        <!-- Delete button (visible on hover) -->
        <Button
          icon="pi pi-trash"
          size="small"
          text
          severity="secondary"
          class="delete-btn flex-shrink-0 p-0"
          style="width: 1.5rem; height: 1.5rem;"
          @click.stop="$emit('delete', session.id)"
        />
      </div>

      <div v-if="sessions.length === 0" class="p-3 text-center text-600 text-sm">
        No conversations yet
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import Button from 'primevue/button';
import type { ChatSession } from '@/stores/chat_store.js';

defineProps<{
  sessions: ChatSession[];
  activeSessionId?: number | null;
}>();

defineEmits<{
  select: [sessionId: number];
  delete: [sessionId: number];
  create: [];
}>();

const getScopeBadge = (scopeType?: string): string => {
  switch (scopeType) {
    case 'document': return '📄';
    case 'entity': return '🏷️';
    default: return '🌐';
  }
};

const getScopeBadgeTitle = (scopeType?: string): string => {
  switch (scopeType) {
    case 'document': return 'Document scope';
    case 'entity': return 'Entity scope';
    default: return 'All library';
  }
};
</script>

<style scoped>
.session-row {
  transition: background-color 0.15s;
}

.session-row:hover {
  background-color: var(--surface-hover);
}

.session-row:hover .delete-btn {
  opacity: 1;
}

.delete-btn {
  opacity: 0;
  transition: opacity 0.15s;
}
</style>
