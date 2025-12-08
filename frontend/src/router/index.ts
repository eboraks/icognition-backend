import { createRouter, createWebHistory } from 'vue-router'
import { RouteRecordRaw } from "vue-router";
import { useAuthStore } from '../stores/auth_store.js';

// Route guard for protected routes (requires authentication)
const requireAuth = (to: any, from: any, next: any) => {
  const authStore = useAuthStore();
  
  if (!authStore.isAuthenticated) {
    console.log('Route guard: User not authenticated, redirecting to home');
    next({ name: 'home' });
  } else {
    console.log('Route guard: User authenticated, allowing access');
    next();
  }
};

// Route guard for guest-only routes (redirect if already authenticated)
const guestOnly = (to: any, from: any, next: any) => {
  const authStore = useAuthStore();
  
  console.log('Guest-only route guard - Auth status:', authStore.isAuthenticated, 'User:', authStore.currentUser);
  
  if (authStore.isAuthenticated) {
    console.log('Route guard: User already authenticated, redirecting to library');
    next({ name: 'library' });
  } else {
    console.log('Route guard: User not authenticated, allowing access to guest route');
    next();
  }
};

// Route guard for admin routes (requires sysadmin role)
const requireAdmin = async (to: any, from: any, next: any) => {
  const authStore = useAuthStore();
  
  // Wait for auth initialization if not already done
  if (!authStore.initialized) {
    await authStore.initAuth();
  }
  
  if (!authStore.isAuthenticated) {
    console.log('Admin route guard: User not authenticated, redirecting to home');
    next({ name: 'home' });
    return;
  }
  
  if (!authStore.isAdmin) {
    console.log('Admin route guard: User is not admin, redirecting to home');
    next({ name: 'home' });
    return;
  }
  
  console.log('Admin route guard: User is admin, allowing access');
  next();
};

const routes: Array<RouteRecordRaw> = [
  {
    path: '/',
    name: 'home',
    component: () => import("../views/HomeView.vue")
  },
  // {
  //   path: '/:pathMatch(.*)*',
  //   name: '404',
  //   component: () => import("@/views/NotFound.vue"),
  //   beforeEnter: authenticated
  // },
  {
    path: '/library',
    name: 'library',
    components: {
      default: () => import("../views/DocumentContainer.vue"),
      sidebar: () => import("@/components/library/LibrarySidebar.vue")
    }
  },
  {
    path: '/learning-qa',
    name: 'learning-qa',
    component: () => import("../views/library/LearningQA.vue")
  },
  {
    path: '/knowledge-explorer',
    name: 'knowledge-explorer',
    components: {
      default: () => import("../views/library/KnowledgeExplorer.vue"),
      sidebar: () => import("@/components/knowledge_explorer/FilterTree.vue")
    }
  },
  { 
    path: '/docxray/:id',
    name: 'docxray',
    component: () => import("../views/library/DocXRayView.vue"),
    props: true
  },
  { 
    path: '/privacy-policy',
    name: 'privacy-policy',
    component: () => import("../components/PrivacyPolicy.vue"),
  },
  { 
    path: '/terms-of-use',
    name: 'terms-of-use',
    component: () => import("../components/TermsOfUse.vue"),
  },
  {
    path: '/admin/prompts',
    name: 'admin-prompts',
    component: () => import("../views/AdminPromptsView.vue"),
    beforeEnter: requireAdmin
  }
];

const router = createRouter({
  history: createWebHistory(),
  routes
});

// Global navigation guard to ensure auth state is initialized and handle redirects
router.beforeEach(async (to, from, next) => {
  const authStore = useAuthStore();
  
  // Wait for auth initialization if not already done
  if (!authStore.initialized) {
    console.log('Router: Waiting for auth initialization...');
    await authStore.initAuth();
  }
  
  console.log('Global router guard - going to:', to.name, 'authenticated:', authStore.isAuthenticated);
  
  // Handle automatic redirects based on auth state
  const protectedRoutes = ['library', 'search', 'collections', 'document', 'analyze', 'profile', 'admin-prompts'];
  const guestRoutes = ['home'];
  
  if (authStore.isAuthenticated && guestRoutes.includes(to.name as string)) {
    console.log('Authenticated user accessing guest route, redirecting to library');
    next({ name: 'library' });
    return;
  }
  
  if (!authStore.isAuthenticated && protectedRoutes.includes(to.name as string)) {
    console.log('Unauthenticated user accessing protected route, redirecting to home');
    next({ name: 'home' });
    return;
  }
  
  next();
});

export default router;
