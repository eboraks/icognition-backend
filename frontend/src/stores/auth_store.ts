import { defineStore } from 'pinia';
import { onAuthStateChanged } from 'firebase/auth';
import { auth } from '../firebase/config.js';
import {
  registerUser,
  loginUser,
  signInWithGoogle,
  signInWithGithub,
  logoutUser,
  sendVerificationEmail
} from '../firebase/auth.js';
import { userService } from '../services/UserService.js';
import { systemService } from '../services/systemService.js';

interface User {
  uid: string;
  email: string | null;
  displayName: string | null;
  emailVerified: boolean;
  photoURL: string | null;
  role?: string;
}

interface AuthState {
  user: User | null;
  loading: boolean;
  error: string | null;
  initialized: boolean;
  isAuthDisabled: boolean;
}

export const useAuthStore = defineStore('auth', {
  state: (): AuthState => ({
    user: null,
    loading: true,
    error: null,
    initialized: false,
    isAuthDisabled: false
  }),

  getters: {
    isAuthenticated: (state) => !!state.user || state.isAuthDisabled,
    isVerified: (state) => state.user?.emailVerified ?? false,
    isAdmin: (state) => state.user?.role === 'sysadmin',
    currentUser: (state) => state.user,
    isLoading: (state) => state.loading,
    authError: (state) => state.error
  },

  actions: {
    // Initialize authentication state observer
    async initAuth() {
      // Check if auth is disabled on the backend
      try {
        const status = await systemService.getAuthStatus();
        this.isAuthDisabled = status.disable_auth;
        if (this.isAuthDisabled) {
          console.log('Auth store: Backend reported DISABLE_AUTH=true, skipping Firebase initialization');
          this.user = {
            uid: 'no-auth-user',
            email: 'no-auth@example.com',
            displayName: 'No-Auth Developer',
            emailVerified: true,
            photoURL: null,
            role: 'sysadmin'
          };
          this.loading = false;
          this.initialized = true;
          return Promise.resolve(null);
        }
      } catch (error) {
        console.warn('Auth store: Failed to check auth status, proceeding with Firebase:', error);
      }

      return new Promise((resolve) => {
        onAuthStateChanged(auth, async (firebaseUser) => {
          if (firebaseUser) {
            // Fetch user profile from backend to get role
            try {
              const profile = await userService.getUserProfile();
              this.user = {
                uid: firebaseUser.uid,
                email: firebaseUser.email,
                displayName: firebaseUser.displayName || profile.display_name || null,
                emailVerified: firebaseUser.emailVerified,
                photoURL: firebaseUser.photoURL || profile.photo_url || null,
                role: profile.role
              };
            } catch (error) {
              // If profile fetch fails, use Firebase user data only
              console.warn('Failed to fetch user profile:', error);
              this.user = {
                uid: firebaseUser.uid,
                email: firebaseUser.email,
                displayName: firebaseUser.displayName,
                emailVerified: firebaseUser.emailVerified,
                photoURL: firebaseUser.photoURL
              };
            }
          } else {
            this.user = null;
          }
          this.loading = false;
          this.initialized = true;
          resolve(firebaseUser);
        });
      });
    },

    // Register new user
    async register(email: string, password: string, displayName: string) {
      this.loading = true;
      this.error = null;
      try {
        const firebaseUser = await registerUser(email, password, displayName);
        // User state will be updated by the auth observer
        return firebaseUser;
      } catch (error: any) {
        this.error = error.message;
        throw error;
      } finally {
        this.loading = false;
      }
    },

    // Login user
    async login(email: string, password: string) {
      this.loading = true;
      this.error = null;
      try {
        const firebaseUser = await loginUser(email, password);
        // User state will be updated by the auth observer
        return firebaseUser;
      } catch (error: any) {
        this.error = error.message;
        throw error;
      } finally {
        this.loading = false;
      }
    },

    // Google login
    async loginWithGoogle() {
      this.loading = true;
      this.error = null;
      try {
        const firebaseUser = await signInWithGoogle();
        // User state will be updated by the auth observer
        return firebaseUser;
      } catch (error: any) {
        this.error = error.message;
        throw error;
      } finally {
        this.loading = false;
      }
    },

    // GitHub login
    async loginWithGithub() {
      this.loading = true;
      this.error = null;
      try {
        const firebaseUser = await signInWithGithub();
        // User state will be updated by the auth observer
        return firebaseUser;
      } catch (error: any) {
        this.error = error.message;
        throw error;
      } finally {
        this.loading = false;
      }
    },

    // Logout user
    async logout() {
      console.log('Auth store: Starting logout...');
      this.loading = true;
      this.error = null;
      try {
        await logoutUser();
        console.log('Auth store: Firebase logout successful');
        // User state will be updated by the auth observer
      } catch (error: any) {
        console.error('Auth store: Logout error:', error);
        this.error = error.message;
        throw error;
      } finally {
        this.loading = false;
        console.log('Auth store: Logout process completed');
      }
    },

    // Send email verification
    async sendEmailVerification() {
      if (!this.user) {
        throw new Error('No user logged in');
      }
      this.loading = true;
      this.error = null;
      try {
        await sendVerificationEmail(auth.currentUser);
        return true;
      } catch (error: any) {
        this.error = error.message;
        throw error;
      } finally {
        this.loading = false;
      }
    },

    // Clear error
    clearError() {
      this.error = null;
    }
  }
});
