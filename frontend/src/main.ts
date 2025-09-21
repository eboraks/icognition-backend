import { createApp, h } from 'vue';
import { createPinia } from 'pinia';
import App from '@/App.vue';
import router from './router/index.js';
import './assets/css/main.scss';

// PrimeVue and PrimeFlex
import PrimeVue from 'primevue/config';
import { definePreset } from '@primevue/themes';
import Lara from '@primevue/themes/lara';
// import "primevue/resources/themes/lara-light-blue/theme.css";
import 'primeflex/primeflex.css'
import 'primeicons/primeicons.css'

// PrimeVue Components
import AutoComplete from 'primevue/autocomplete';
import Breadcrumb from 'primevue/breadcrumb';
import Button from 'primevue/button';
import ButtonGroup from 'primevue/buttongroup';
import Card from 'primevue/card';
import Checkbox from 'primevue/checkbox';
import Column from 'primevue/column';
import DataTable from 'primevue/datatable';
import Dialog from 'primevue/dialog';
import DialogService from 'primevue/dialogservice';
import DynamicDialog from 'primevue/dynamicdialog';
import Fieldset from 'primevue/fieldset';
import FloatLabel from 'primevue/floatlabel';
import IconField from 'primevue/iconfield';
import InputIcon from 'primevue/inputicon';
import InputText from 'primevue/inputtext';
import Menu from 'primevue/menu';
import Message from 'primevue/message';
import MultiSelect from 'primevue/multiselect';
import Panel from 'primevue/panel';
import Popover from 'primevue/popover';
import ScrollPanel from 'primevue/scrollpanel';
import Select from 'primevue/select';
import SelectButton from 'primevue/selectbutton';
import Skeleton from 'primevue/skeleton';
import Splitter from 'primevue/splitter';
import SplitterPanel from 'primevue/splitterpanel';
import Tab from 'primevue/tab';
import TabList from 'primevue/tablist';
import TabPanel from 'primevue/tabpanel';
import TabPanels from 'primevue/tabpanels';
import Tabs from 'primevue/tabs';
import Tag from 'primevue/tag';
import Textarea from 'primevue/textarea';
import Toast from 'primevue/toast';
import ToastService from 'primevue/toastservice';
import Tree from 'primevue/tree';

// Firebase
import { auth } from './firebase/config.js'
import { onAuthStateChanged } from 'firebase/auth'

const pinia = createPinia();
const MyPreset = definePreset(Lara, {
    //Your customizations, see the following sections for examples
});
// Vue Composables
let app: any
onAuthStateChanged(auth, (user) => {
    render: ()=>h(app)
    if (!app) {
        app = createApp(App)
        app.component('AutoComplete', AutoComplete);
        app.component('Breadcrumb', Breadcrumb);
        app.component('Button', Button);
        app.component('ButtonGroup', ButtonGroup);
        app.component('Card', Card);
        app.component('Checkbox', Checkbox);
        app.component('Column', Column);
        app.component('DataTable', DataTable);
        app.component('Dialog', Dialog);
        app.component('DynamicDialog', DynamicDialog);
        app.component('Fieldset', Fieldset);
        app.component('FloatLabel', FloatLabel);
        app.component('IconField', IconField);
        app.component('InputIcon', InputIcon);
        app.component('InputText', InputText);
        app.component('Menu', Menu);
        app.component('Message', Message);
        app.component('MultiSelect', MultiSelect);
        app.component('Panel', Panel);
        app.component('Popover', Popover);
        app.component('ScrollPanel', ScrollPanel);
        app.component('Select', Select);
        app.component('SelectButton', SelectButton);
        app.component('Skeleton', Skeleton);
        app.component('Splitter', Splitter);
        app.component('SplitterPanel', SplitterPanel);
        app.component('Tab', Tab);
        app.component('TabList', TabList);
        app.component('TabPanel', TabPanel);
        app.component('TabPanels', TabPanels);
        app.component('Tabs', Tabs);
        app.component('Tag', Tag);
        app.component('Textarea', Textarea);
        app.component('Toast', Toast);
        app.component('ToastService', ToastService);
        app.component('Tree', Tree);
        app.use(pinia);
        app.use(DialogService);
        app.use(ToastService);
        app.use(router).use(PrimeVue, {
            theme: {
                preset: MyPreset,
                options: {
                    prefix: 'p',
                    darkModeSelector: '.p-dark',
                    cssLayer: true,
                }
            }
        }).mount('#app');
    }
})
