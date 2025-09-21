import { createRouter, createWebHistory } from 'vue-router'
import { RouteRecordRaw } from "vue-router";
import user_state from '@/composables/getUser.js';

// route guard
const requireAuth = (to: any, from: any, next: any) => {
  if (!user_state.user) {
    console.log('require auth: user not logged in. User: ', user_state.user)
    next({ name: 'home' })
  } else {
    next()
  }
};

const authenticated = (to: any, from: any, next: any) => {
  if (user_state.user) {
    console.log('authenticated: user logged in. From: ', from, ' To: ', to)
    next({ name: to })
  } else {
    next()
  }
};

const routes: Array<RouteRecordRaw> = [
  {
    path: '/',
    name: 'home',
    component: () => import("@/views/HomeView.vue"),
    beforeEnter: authenticated
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
    component: () => import("@/views/DocumentContainer.vue"),
    beforeEnter: requireAuth
  },
  {
    path: '/collections',
    name: 'collections',
    component: () => import("@/views/library/Collections.vue"),
    beforeEnter: requireAuth
  },
  {
    path: '/collectiondetails/:id',
    name: 'collectiondetails',
    component: () => import("@/views/library/CollectionDetails.vue"),
    beforeEnter: requireAuth,
    props: true
  },
  { 
    path: '/docxray/:id',
    name: 'docxray',
    component: () => import("@/views/library/DocXRayView.vue"),
    beforeEnter: requireAuth,
    props: true
  },
  { 
    path: '/privacy-policy',
    name: 'privacy-policy',
    component: () => import("@/components/PrivacyPolicy.vue"),
  },
  { 
    path: '/terms-of-use',
    name: 'terms-of-use',
    component: () => import("@/components/TermsOfUse.vue"),
  }
];

const router = createRouter({
  history: createWebHistory(),
  routes
});

export default router;
