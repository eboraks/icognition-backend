<template>
  <div class="chat-container">
    <vue-advanced-chat
      height="calc(100vh - 120px)"
      style="width: 100%"
      :current-user-id="currentUserId"
      :rooms="roomsString"
      :room-actions="JSON.stringify(roomActions)"
      :menu-actions="JSON.stringify(menuActions)"
      :room-id="activeRoomId"
      :messages="messagesString"
      :rooms-loaded="true"
      :messages-loaded="true"
      :show-new-messages-divider="false"
      @send-message="handleSendMessage($event.detail[0])"
      @add-room="handleCreateSession"
      @fetch-messages="handleFetchMessages($event.detail[0])"
      @room-action-handler="onRoomAction($event.detail[0])"
      @menu-action-handler="onMenuAction($event.detail[0])"
      @toggle-rooms-list="noop">
      <div slot="spinner-icon-rooms"></div>
      <div slot="spinner-icon-infinite-rooms"></div>
      <div slot="spinner-icon-messages"></div>
      <div slot="spinner-icon-infinite-messages"></div>
    </vue-advanced-chat>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch, computed, nextTick } from 'vue';
import { useChatStore } from '@/stores/chat_store';
import type { ChatSession } from '@/stores/chat_store';
import { useAuthStore } from '@/stores/auth_store';
import { register } from 'vue-advanced-chat';
// Register web components so <vue-advanced-chat/> works in the template
register();

const chatStore = useChatStore();
const authStore = useAuthStore();

const currentUserId = ref(authStore.currentUser?.uid || 'guest');

// Keep current user id in sync (auth initializes async, including DISABLE_AUTH mode)
watch(
  () => authStore.currentUser?.uid,
  (uid) => {
    if (uid) currentUserId.value = uid;
  },
  { immediate: true }
);

type RoomUser = { _id: string; username: string };
type Room = {
  roomId: string;
  roomName: string;
  users: RoomUser[];
  lastMessage?: any;
};

const rooms = ref<Room[]>([]);
const activeRoomId = ref<string | null>(null);

type ChatMessagePayload = { content: string };

// Computed property to always generate fresh stringified rooms for the component
const roomsString = computed(() => {
  console.log('Rooms string computed, rooms count:', rooms.value.length);
  return JSON.stringify(rooms.value);
});

const messagesString = computed(() => {
  // Messages are stored per-session in the chat store
  return JSON.stringify(chatStore.activeSession?.messages || []);
});

// Keep rooms list in sync with store sessions
watch(
  () => chatStore.sessions,
  (sessions) => {
    console.log('Sessions watcher triggered, sessions count:', sessions?.length || 0);
    // Always update rooms to ensure vue-advanced-chat gets the latest data
    const newRooms = (sessions || []).map((s) => ({
      roomId: s.id.toString(),
      roomName: s.title,
      users: [
        { _id: currentUserId.value, username: 'You' },
        { _id: 'agent', username: 'Agent' }
      ],
    }));
    
    console.log('Updating rooms from', rooms.value.length, 'to', newRooms.length);
    rooms.value = newRooms;
    
    // Ensure an active room selection exists for display
    // But only auto-select if there's no active session AND there are sessions
    if (!chatStore.activeSession && sessions && sessions.length > 0 && sessions[0]) {
      const firstSessionId = sessions[0].id;
      chatStore.switchActiveSession(firstSessionId);
      activeRoomId.value = String(firstSessionId);
    } else if (chatStore.activeSession) {
      // Check if the active session still exists
      const sessionExists = sessions?.some(s => s.id === chatStore.activeSession!.id);
      if (sessionExists) {
        activeRoomId.value = String(chatStore.activeSession.id);
      } else {
        // Active session was deleted, clear it and select first if available
        console.log('Active session was deleted, clearing and selecting new one');
        chatStore.activeSession = null;
        if (sessions && sessions.length > 0 && sessions[0]) {
          const firstSessionId = sessions[0].id;
          chatStore.switchActiveSession(firstSessionId);
          activeRoomId.value = String(firstSessionId);
        } else {
          activeRoomId.value = null;
        }
      }
    } else if (sessions && sessions.length === 0) {
      // No sessions, clear activeRoomId
      activeRoomId.value = null;
    }
  },
  { immediate: true, deep: true }
);


onMounted(() => {
  if (authStore.currentUser) {
    chatStore.loadSessions();
  }
});

const handleCreateSession = () => {
  if (authStore.currentUser) {
    chatStore.createSession('New Chat');
  }
};

const handleSendMessage = (message: ChatMessagePayload) => {
  chatStore.sendMessage(message.content);
};

const handleFetchMessages = (options: any) => {
  console.log('handleFetchMessages triggered with options:', options);
  const id = Number(options?.room?.roomId);
  if (!isNaN(id)) {
    console.log('Switching to session:', id);
    chatStore.switchActiveSession(id);
    activeRoomId.value = String(id);
  } else {
    // This case can happen when the last chat is deleted.
    // The library tries to fetch messages for a non-existent room.
    // It's safe to ignore this event as the store handles state clearing.
    console.warn('Could not get a valid room ID from fetch-messages event.', options);
  }
};

const noop = () => {};

// Room actions (dropdown in room list sidebar)
const roomActions = [
  { name: 'deleteRoom', title: 'Delete Chat' }
];

// Menu actions (three dots menu in room header)
const menuActions = [
  { name: 'deleteRoom', title: 'Delete Chat' }
];

const onRoomAction = async (eventData: any) => {
  console.log('Room action triggered:', eventData);
  // Handle both direct object and event detail formats
  const { roomId, action } = eventData || {};
  
  if (!action || action.name !== 'deleteRoom') {
    console.log('Action not deleteRoom, ignoring', { action });
    return;
  }
  
  const id = Number(roomId);
  if (isNaN(id)) {
    console.error('Invalid roomId:', roomId);
    return;
  }
  
  try {
    console.log('Deleting session:', id);
    const wasActive = chatStore.activeSession?.id === id;
    
    // Delete the session (this already removes it from sessions.value and clears activeSession if needed)
    await chatStore.deleteSession(id);
    console.log('Session deleted successfully, remaining sessions:', chatStore.sessions.length);
    
    // The watcher will automatically update rooms when sessions change
    // Just ensure activeRoomId is cleared if this was the active session
    if (wasActive) {
      activeRoomId.value = null;
      // The watcher will select the first session if available
      await nextTick();
    }
    
    console.log('Final rooms count:', rooms.value.length);
  } catch (error) {
    console.error('Failed to delete session:', error);
    // On error, reload sessions to sync with backend
    await chatStore.loadSessions();
  }
};

const onMenuAction = async (eventData: any) => {
  // Same handler for menu actions
  console.log('Menu action triggered:', eventData);
  await onRoomAction(eventData);
};
</script>

<style scoped>
.chat-container {
  display: flex;
  height: calc(100vh - 70px); /* Adjust based on your header height */
}
</style>


