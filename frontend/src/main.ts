import { createApp } from 'vue';
import { createPinia } from 'pinia';
import App from './App.vue';
import router from './router/index.js';
import './assets/css/main.scss';

// PrimeVue CSS only
import 'primeicons/primeicons.css';
import 'primeflex/primeflex.css';

import PrimeVue from 'primevue/config';
import Aura from '@primeuix/themes/aura';
import Tooltip from 'primevue/tooltip';
import ToastService from 'primevue/toastservice';
import Toast from 'primevue/toast';

// Firebase and Auth Store
import { useAuthStore } from './stores/auth_store.js';

const pinia = createPinia();
const app = createApp(App);

// Use plugins
app.use(pinia);
app.use(router);
app.use(PrimeVue as any, { 
    theme: {
        preset: Aura,
        options: {
            darkModeSelector: false
        }
    },
    ripple: true 
});

app.use(ToastService as any);
app.component('Toast', Toast);
app.directive('tooltip', Tooltip as any);

// Initialize auth store and mount app
const authStore = useAuthStore();
authStore.initAuth().then(() => {
    app.mount('#app');
});