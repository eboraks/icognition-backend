import { createApp } from 'vue';
import App from './App.vue';
import PrimeVue from 'primevue/config';
import Aura from '@primevue/themes/aura';
import { definePreset } from '@primevue/themes';
import 'primeicons/primeicons.css';
import 'primeflex/primeflex.css';

// Warm neutral theme preset (stone palette) — matches web app
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
        preset: WarmAura,
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
