import { createApp } from 'vue';
import App from './App.vue';
import PrimeVue from 'primevue/config';
import 'primevue/resources/themes/lara-light-blue/theme.css'; // Import Lara theme CSS
import 'primevue/resources/primevue.min.css'; // Import PrimeVue CSS
import 'primeicons/primeicons.css'; // Import PrimeIcons CSS
import 'primeflex/primeflex.css'; // Import PrimeFlex CSS
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


console.log('main.js loaded');

const app = createApp(App);
app.use(PrimeVue);
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
