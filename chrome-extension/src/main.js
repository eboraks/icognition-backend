import { createApp } from 'vue';
import App from './App.vue';
import PrimeVue from 'primevue/config';
import Aura from '@primevue/themes/aura';
import { definePreset } from '@primevue/themes';
import 'primeicons/primeicons.css';
import 'primeflex/primeflex.css';

// Define custom preset with web app's primary color
const CustomAura = definePreset(Aura, {
    semantic: {
        primary: {
            50: '{cyan.50}',
            100: '{cyan.100}',
            200: '{cyan.200}',
            300: '{cyan.300}',
            400: '{cyan.400}',
            500: '{cyan.500}',
            600: '{cyan.600}',
            700: '{cyan.700}',
            800: '{cyan.800}',
            900: '{cyan.900}',
            950: '{cyan.950}'
        }
    }
});
import Button from 'primevue/button';
import ProgressBar from 'primevue/progressbar';
import Skeleton from 'primevue/skeleton';
import Card from 'primevue/card';
import InputText from 'primevue/inputtext';
import ScrollPanel from 'primevue/scrollpanel';
import Avatar from 'primevue/avatar';
import Message from 'primevue/message';
import AutoComplete from 'primevue/autocomplete';
import ProgressSpinner from 'primevue/progressspinner';
import Divider from 'primevue/divider';
import Select from 'primevue/select';


console.log('main.js loaded');

const app = createApp(App);
app.use(PrimeVue, {
    theme: {
        preset: CustomAura,
        options: {
            darkModeSelector: false
        }
    },
    ripple: true
});
app.component('Button', Button);
app.component('ProgressBar', ProgressBar);
app.component('Skeleton', Skeleton);
app.component('Card', Card);
app.component('InputText', InputText);
app.component('ScrollPanel', ScrollPanel);
app.component('Avatar', Avatar);
app.component('Message', Message);
app.component('AutoComplete', AutoComplete);
app.component('ProgressSpinner', ProgressSpinner);
app.component('Divider', Divider);
app.component('Select', Select);
// Set up tab change listeners
chrome.tabs.onActivated.addListener(async (activeInfo) => {
    console.log('Tab activated event fired with tabId:', activeInfo.tabId);
    const tab = await chrome.tabs.get(activeInfo.tabId);
    if (tab && tab.url) {
        console.log('Dispatching tab-changed event for URL:', tab.url);
        window.dispatchEvent(new CustomEvent('tab-changed', { detail: tab }));
    }
});

chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
    console.log('Tab updated event fired:', { tabId, changeInfo });
    if (changeInfo.status === 'complete' && tab.url) {
        console.log('Tab load complete, dispatching tab-changed event for URL:', tab.url);
        window.dispatchEvent(new CustomEvent('tab-changed', { detail: tab }));
    }
});

// Initial load - get current tab
chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
    console.log('Initial tab query result:', tabs);
    if (tabs && tabs[0]) {
        console.log('Dispatching initial tab-changed event for URL:', tabs[0].url);
        window.dispatchEvent(new CustomEvent('tab-changed', { detail: tabs[0] }));
    }
});

app.mount('#app');
