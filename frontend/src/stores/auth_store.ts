import { defineStore } from 'pinia';
import { onAuthStateChanged } from 'firebase/auth';
import { auth } from '../firebase/config';
import { 
  registerUser, 
  loginUser, 
  signInWithGoogle, 
  signInWithGithub, 
  logoutUser,
  sendVerificationEmail 
} from '../firebase/auth';

interface User {
  uid: string;
  email: string | null;
  displayName: string | null;
  emailVerified: boolean;
  photoURL: string | null;
}

interface AuthState {
  user: User | null;
  loading: boolean;
  error: string | null;
  initialized: boolean;
}

export const useAuthStore = defineStore('auth', {
  state: (): AuthState => ({
    user: null,
    loading: true,
    error: null,
    initialized: false
  }),

  getters: {
    isAuthenticated: (state) => !!state.user,
    isVerified: (state) => state.user?.emailVerified ?? false,
    currentUser: (state) => state.user,
    isLoading: (state) => state.loading,
    authError: (state) => state.error
  },

  actions: {
    // Initialize authentication state observer
    initAuth() {
      return new Promise((resolve) => {
        onAuthStateChanged(auth, (firebaseUser) => {
          if (firebaseUser) {
            this.user = {
              uid: firebaseUser.uid,
              email: firebaseUser.email,
              displayName: firebaseUser.displayName,
              emailVerified: firebaseUser.emailVerified,
              photoURL: firebaseUser.photoURL
            };
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
