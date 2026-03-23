<template>
  <div class="layout-wrapper">
    <!-- Top Bar -->
    <div class="layout-topbar bg-primary-500">
      <div class="layout-topbar-left">
        <button v-if="hasSidebar" class="layout-menu-button p-link" @click="onMenuToggle">
          <i class="pi pi-bars"></i>
        </button>
        <div class="layout-topbar-logo">
          <img src="/src/assets/images/iCognitionLogo.png?format=1500w" alt="iCognition.ai" />
        </div>
      </div>
      
      <div class="layout-topbar-center">
        <div class="layout-topbar-menu">
          <router-link 
            to="/library" 
            class="layout-topbar-menu-item"
            :class="{ 'active': $route.name === 'library' }"
          >
            My Library
          </router-link>
          <router-link
            to="/chats"
            class="layout-topbar-menu-item"
            :class="{ 'active': $route.name === 'chats' }"
          >
            Chat
          </router-link>
          <router-link 
            to="/knowledge-explorer" 
            class="layout-topbar-menu-item"
            :class="{ 'active': $route.name === 'knowledge-explorer' }"
          >
            Knowledge Explorer
          </router-link>
        </div>
      </div>
      
      <div class="layout-topbar-right">
        <div v-if="authStore.isAuthenticated" class="layout-topbar-user" @click="toggleUserMenu">
          <img 
            v-if="authStore.currentUser?.photoURL" 
            :src="authStore.currentUser.photoURL" 
            alt="User Avatar" 
            class="user-avatar"
          />
          <div v-else class="user-avatar-placeholder">
            <i class="pi pi-user"></i>
          </div>
          <span class="user-name">{{ authStore.currentUser?.displayName || 'User' }}</span>
          <i class="pi pi-angle-down"></i>
        </div>
        <button v-else class="login-button" @click="handleGoogleLogin">
          <img src="/src/assets/images/web_neutral_rd_SI@2x.png" alt="Sign in with Google" class="google-signin-image" />
        </button>
        
        <Menu ref="userMenu" :model="userMenuItems" :popup="true" />
      </div>
    </div>

    <!-- Sidebar -->
    <div v-if="hasSidebar" class="layout-sidebar" :class="{ 'layout-sidebar-active': sidebarVisible }">
      <div class="layout-sidebar-content">
        <router-view name="sidebar" />
      </div>
    </div>

    <!-- Overlay for mobile -->
    <div 
      v-if="hasSidebar"
      class="layout-sidebar-overlay" 
      :class="{ 'layout-sidebar-overlay-active': sidebarVisible && isMobile }"
      @click="onMenuToggle"
    ></div>

    <!-- Main Content -->
    <div class="layout-content" :class="{ 'layout-content-sidebar-active': sidebarVisible && hasSidebar }">
      <div class="layout-content-container">
        <router-view />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { useAuthStore } from '@/stores/auth_store';
import Menu from 'primevue/menu';
import Button from 'primevue/button';

const route = useRoute();
const router = useRouter();
const authStore = useAuthStore();
const userMenu = ref();
const sidebarVisible = ref(true);
const isMobile = ref(false);

// Check if current route has a sidebar component
const hasSidebar = computed(() => {
  return route.matched.some(record => record.components?.sidebar);
});

const checkMobile = () => {
  isMobile.value = window.innerWidth < 992;
  if (isMobile.value) {
    sidebarVisible.value = false;
  }
};

onMounted(() => {
  checkMobile();
  window.addEventListener('resize', checkMobile);
});

onUnmounted(() => {
  window.removeEventListener('resize', checkMobile);
});

const onMenuToggle = () => {
  sidebarVisible.value = !sidebarVisible.value;
};

const toggleUserMenu = (event: Event) => {
  userMenu.value.toggle(event);
};

const handleLogout = async () => {
  try {
    await authStore.logout();
    router.push('/');
  } catch (error) {
    console.error('Logout error:', error);
  }
};

const handleGoogleLogin = async () => {
  try {
    await authStore.loginWithGoogle();
    router.push('/library'); // Redirect to library after successful login
  } catch (error) {
    console.error('Login failed using Google:', error);
  }
};

const userMenuItems = computed(() => {
  const items: any[] = [];
  
  items.push({
    label: 'Sign Out',
    icon: 'pi pi-sign-out',
    command: handleLogout
  });
  
  return items;
});
</script>

<style scoped>
.layout-wrapper {
  display: flex;
  flex-direction: column;
  height: 100vh;
  overflow: hidden;
}

/* Top Bar */
.layout-topbar {
  height: 4rem;
  /*background: var(--p-primary-color);*/
  border-bottom: 1px solid var(--p-content-border-color);
  display: flex;
  align-items: center;
  padding: 0 1.5rem;
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  z-index: 1000;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
}

.layout-topbar-left {
  display: flex;
  align-items: center;
  gap: 1rem;
  flex: 0 0 auto;
}

.layout-menu-button {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 2.5rem;
  height: 2.5rem;
  color: var(--p-primary-contrast-color);
  border-radius: var(--p-border-radius);
  transition: background-color 0.2s;
}

.layout-menu-button:hover {
  background: rgba(255, 255, 255, 0.1);
}

.layout-topbar-logo img {
  height: 2rem;
  max-width: 150px;
}

.layout-topbar-center {
  flex: 1;
  display: flex;
  justify-content: center;
  align-items: center;
}

.layout-topbar-menu {
  display: flex;
  gap: 1rem;
  align-items: center;
}

.layout-topbar-menu-item {
  padding: 0.5rem 1rem;
  color: var(--p-primary-contrast-color);
  text-decoration: none;
  border-radius: var(--p-border-radius);
  transition: background-color 0.2s;
  font-weight: 500;
}

.layout-topbar-menu-item:hover {
  background: rgba(255, 255, 255, 0.1);
}

.layout-topbar-menu-item.active {
  background: rgba(255, 255, 255, 0.2);
}

.layout-topbar-right {
  display: flex;
  align-items: center;
  gap: 1rem;
  flex: 0 0 auto;
}

.layout-topbar-user {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem;
  border-radius: var(--p-border-radius);
  cursor: pointer;
  transition: background-color 0.2s;
  color: var(--p-primary-contrast-color);
}

.layout-topbar-user:hover {
  background: rgba(255, 255, 255, 0.1);
}

.user-avatar,
.user-avatar-placeholder {
  width: 2rem;
  height: 2rem;
  border-radius: 50%;
  object-fit: cover;
}

.user-avatar-placeholder {
  background: rgba(255, 255, 255, 0.2);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--p-primary-contrast-color);
}

.user-name {
  font-weight: 500;
}

.login-button {
  padding: 0;
  background-color: transparent;
  border: none;
  cursor: pointer;
  display: inline-block;
  height: 40px; /* Adjust height as needed */
  width: 180px; /* Adjust width as needed to fit the image */
}

.google-signin-image {
  height: 100%;
  width: 100%;
  object-fit: cover;
}

.login-button:hover {
  background-color: transparent; /* No background change on hover for image button */
}

/* Sidebar */
.layout-sidebar {
  position: fixed;
  left: 0;
  top: 4rem;
  height: calc(100vh - 4rem);
  width: 20rem;
  background: var(--p-surface-card);
  border-right: 1px solid var(--p-content-border-color);
  transition: transform 0.3s;
  z-index: 999;
  overflow-y: auto;
}

.layout-sidebar-content {
  padding: 1rem;
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  min-height: 0;
}

@media (max-width: 991px) {
  .layout-sidebar {
    transform: translateX(-100%);
  }
  
  .layout-sidebar-active {
    transform: translateX(0);
  }
  
  .layout-sidebar-overlay {
    display: block;
    position: fixed;
    top: 4rem;
    left: 0;
    right: 0;
    bottom: 0;
    background: rgba(0, 0, 0, 0.4);
    z-index: 998;
    opacity: 0;
    visibility: hidden;
    transition: opacity 0.3s, visibility 0.3s;
  }
  
  .layout-sidebar-overlay-active {
    opacity: 1;
    visibility: visible;
  }
}

@media (min-width: 992px) {
  .layout-sidebar-overlay {
    display: none;
  }
}

/* Main Content */
.layout-content {
  margin-top: 4rem;
  margin-left: 0;
  transition: margin-left 0.3s;
  min-height: calc(100vh - 4rem);
  background: var(--p-surface-ground);
}

.layout-content-sidebar-active {
  margin-left: 20rem;
}

.layout-wrapper:has(.layout-sidebar) .layout-content-sidebar-active {
  margin-left: 20rem;
}

@media (max-width: 991px) {
  .layout-content-sidebar-active {
    margin-left: 0;
  }
}

.layout-content-container {
  padding: 1.5rem;
  height: 100%;
}
</style>

