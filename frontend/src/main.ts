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
import { definePreset } from '@primeuix/themes';
import Tooltip from 'primevue/tooltip';
import ToastService from 'primevue/toastservice';
import Toast from 'primevue/toast';
import ConfirmationService from 'primevue/confirmationservice';
import ConfirmDialog from 'primevue/confirmdialog';

// Warm neutral theme preset (stone palette)
const WarmAura = definePreset(Aura, {
    semantic: {
        primary: {
            50: '#fafaf9',
            100: '#f5f5f4',
            200: '#e7e5e4',
            300: '#d6d3d1',
            400: '#a8a29e',
            500: '#78716c',
            600: '#57534e',
            700: '#44403c',
            800: '#292524',
            900: '#1c1917',
            950: '#0c0a09'
        },
        colorScheme: {
            light: {
                primary: {
                    color: '#44403c',
                    inverseColor: '#ffffff',
                    hoverColor: '#292524',
                    activeColor: '#1c1917'
                },
                highlight: {
                    background: '#f5f5f4',
                    focusBackground: '#e7e5e4',
                    color: '#292524',
                    focusColor: '#1c1917'
                }
            }
        }
    }
});

// Firebase and Auth Store
import { useAuthStore } from './stores/auth_store.js';

const pinia = createPinia();
const app = createApp(App);

// Use plugins
app.use(pinia);
app.use(router);
app.use(PrimeVue as any, {
    theme: {
        preset: WarmAura,
        options: {
            darkModeSelector: false
        }
    },
    ripple: true
});

app.use(ToastService as any);
app.use(ConfirmationService as any);
app.component('Toast', Toast);
app.component('ConfirmDialog', ConfirmDialog);
app.directive('tooltip', Tooltip as any);

// Initialize auth store and mount app
const authStore = useAuthStore();
authStore.initAuth().then(() => {
    app.mount('#app');
});