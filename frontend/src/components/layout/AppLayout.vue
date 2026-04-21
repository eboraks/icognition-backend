<template>
  <div class="layout-wrapper">
    <!-- Top Bar -->
    <div class="layout-topbar bg-primary-800">
      <div class="layout-topbar-left">
        <div class="layout-topbar-logo">
          <img src="/src/assets/images/iCognitionLogo.png?format=1500w" alt="iCognition.ai" />
        </div>
      </div>
      
      <div class="layout-topbar-center">
        <!-- Unified view — no tab navigation needed -->
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

    <!-- Main Content -->
    <div class="layout-content">
      <div class="layout-content-container">
        <router-view />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue';
import { useRouter } from 'vue-router';
import { useAuthStore } from '@/stores/auth_store';
import Menu from 'primevue/menu';

const router = useRouter();
const authStore = useAuthStore();
const userMenu = ref();

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

/* Main Content */
.layout-content {
  margin-top: 4rem;
  min-height: calc(100vh - 4rem);
  background: var(--p-surface-ground);
}

.layout-content-container {
  height: 100%;
}
</style>

