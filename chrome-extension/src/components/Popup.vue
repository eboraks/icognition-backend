<template>
    <div class="side-panel-container" tabindex="-1">        
        <div class="header w-full h-20" tabindex="-1">
            <div class="flex justify-content-between align-items-center" tabindex="-1">
                <a tabindex="6" :href="library_url" target="_blank">
                    <img src="/icons/iCognitionLogo.png" alt="iCognition Logo" width="150px" class="m-2"/>
                </a>
                <div class="flex align-items-center gap-3 mr-4">
                    <template v-if="user">
                        <Button 
                            @click="handleQuickBookmark" 
                            label="Quick Save" 
                            icon="pi pi-bookmark" 
                            tabindex="4"
                            class="p-button-sm p-button-outlined"
                            :loading="isQuickSaving"
                            :disabled="isQuickSaving || !active_tab || !active_tab.url"
                            title="Quick Save (LinkPresentation Style) - Testing Only"
                            style="font-size: 0.75rem; padding: 0.25rem 0.5rem;"></Button>
                        <i tabindex="5" class="pi pi-cog text-white cursor-pointer" @click="showSettings = true" title="Settings" style="font-size: 1.2rem;"></i>
                        <i tabindex="6" class="pi pi-sign-out text-white cursor-pointer" @click="handleSignOut" title="Sign Out" style="font-size: 1.2rem;"></i>
                    </template>
                </div>
            </div>
        </div>
        
        <div class="flex flex-column" tabindex="-1">
            <div v-if="status.state === AppStatusEnum.INITIALIZING.state" class="m-2 p-2" tabindex="-1">
                <ProgressBar mode="indeterminate"></ProgressBar>
                <p>{{ statusMessage }}</p>
            </div>
            
            <div v-if="status.state === AppStatusEnum.PROCESSING.state && progressPercent > 0 && progressPercent < 100" class="message_container flex align-items-center justify-content-center p-2 m-2" tabindex="-1">
                <div class="w-full px-3" tabindex="-1">
                    <ProgressBar :value="progressPercent" class="mb-2"></ProgressBar>
                    <p class="text-center">{{ AppStatusEnum.PROCESSING.message }}</p>
                    <div class="flex justify-content-center mt-3">
                        <Button 
                            label="Cancel" 
                            icon="pi pi-times" 
                            class="p-button-danger p-button-sm"
                            @click="handleCancelProcessing"
                            tabindex="0"
                        />
                    </div>
                </div>
            </div>
           
            <div v-if="status.state === AppStatusEnum.CONNECTION_ERROR.state" class="message_container flex flex-column align-items-center justify-content-center m-2 p-4" tabindex="-1">
                <Message severity="error" :closable="false" class="w-full mb-3">
                    <p class="m-0">{{ connectionErrorMessage }}</p>
                </Message>
                <Button 
                    label="Try to Connect" 
                    icon="pi pi-refresh" 
                    class="p-button-primary"
                    @click="handleRetryConnection"
                    :loading="isRetryingConnection"
                    tabindex="0"
                />
            </div>

            <div v-if="status.state === AppStatusEnum.UNAUTHENTICATED.state" class="button_container flex align-items-center justify-content-center m-2 p-2" tabindex="-1">
                <GoogleLoginButton tabindex="4"></GoogleLoginButton>
            </div>

            <div v-if="status.state === AppStatusEnum.SERVER_READY.state && !document_summary" class="flex flex-column align-items-center justify-content-center m-2 p-4" tabindex="-1">
                <div v-if="isSearchingBookmark" class="flex flex-column align-items-center" tabindex="-1">
                    <ProgressSpinner style="width:50px;height:50px" strokeWidth="3" fill="var(--surface-ground)" animationDuration="2s"/>
                    <p class="text-center mt-2">Checking for existing analysis...</p>
                </div>
                <div v-else tabindex="-1">
                <p class="text-center mb-2">No analysis found for this page</p>
                    <Button @click="handleBookmark" 
                           label="Analyze This Page" 
                           icon="pi pi-search" 
                           ref="analyzeButton"
                           id="analyze-button"
                           tabindex="3"
                           :class="['p-button-primary', { 'button-has-focus': buttonHasFocus }]"
                           @keydown.enter="handleBookmark"
                           @keydown.space="handleBookmark"
                           @focus="buttonHasFocus = true"
                           @blur="buttonHasFocus = false"></Button>
                </div>
            </div>
        </div>

        <!-- Document summary interface container (Replaced with Chat Interface) -->
        <div v-if="document_summary" class="document-interface-container h-full flex flex-column custom-chat-height" tabindex="-1">
            <div class="page-info p-2 bg-primary-50 flex-none" tabindex="-1">
                <div class="flex align-items-center justify-content-between" tabindex="-1">
                    <span class="text-sm text-primary-800 white-space-nowrap overflow-hidden text-overflow-ellipsis mr-2" :title="getCurrentPageTitle()">{{ getCurrentPageTitle() }}</span>
                    <Button tabindex="2" @click="clearCurrentChat" icon="pi pi-trash" class="p-button-text p-button-sm p-button-danger flex-none"></Button>
                </div>
            </div>
            
            <div v-if="currentChatSessionId" class="chat-container flex-grow-1 overflow-hidden" tabindex="-1">
                <ChatInterface :key="currentChatSessionId" :sessionId="currentChatSessionId" :initialSummary="document_summary" />
            </div>
            <div v-else-if="isCreatingChatSession" class="flex align-items-center justify-content-center p-4">
                 <ProgressSpinner style="width:40px;height:40px" strokeWidth="4" />
                 <span class="ml-2 text-sm text-600">Starting chat...</span>
            </div>
            <!-- Fallback if chat fails to start but summary exists -->
            <div v-else class="summary-container p-3" tabindex="-1">
                <div class="document-title mb-2" tabindex="-1">
                    <h3 class="text-lg font-bold">{{ document_summary.title }}</h3>
                </div>
                <div v-if="document_summary.summary" class="document-summary mb-3" tabindex="-1">
                    <h4 class="text-md font-semibold mb-1">Summary</h4>
                    <p class="text-sm" v-html="formatUrlsAsLinks(document_summary.summary)"></p>
                </div>
                 <div class="text-center mt-3">
                    <Button label="Start Chat" @click="initializeChatSession(cleanUrl(active_tab.url), documentIdsByUrl[cleanUrl(active_tab.url)])" class="p-button-sm" />
                </div>
            </div>
        </div>

        <div v-if="status.severity === AppStatusEnum.ERROR.severity" class="m-2 p-2 flex align-items-center justify-content-center">
            <Message id="status-message" 
                    :severity="status.severity" 
                    class="w-full" 
                    :closable="false">
                {{ status.message }}
            </Message>
        </div>
        
        <div tabindex="-1" v-if="debug_mode" class="debug surface-ground p-2 border-top-1 border-primary-100">
            <span class="debug-toggle" @click="toggleDebugSize">{{ debugExpanded ? 'Collapse' : 'Expand' }}</span>
            <p class="text-sm text-600 mb-1">Status: {{ status.state }}</p>
            <p class="text-sm text-600 mb-1">Status Message: {{ statusMessage }}</p>
            <p class="text-sm text-600 mb-1">Document ID: {{ doc?.id }}</p>
            <p class="text-sm text-600 mb-1">Document ID (URL Cache): {{ active_tab?.url ? documentIdsByUrl[cleanUrl(active_tab.url)] : 'No active tab' }}</p>
            <p class="text-sm text-600 mb-1">User: {{ user?.uid }}</p>
            <p class="text-sm text-600">Progress Percent: {{ progressPercent }}</p>
            <p class="text-sm text-600 mt-2 font-bold">
                <span class="mr-2">Keyboard Logger:</span>
                <Button @click="toggleKeyboardLogger" 
                        :class="keyboardLoggerActive ? 'p-button-success' : 'p-button-secondary'" 
                        :label="keyboardLoggerActive ? 'Active' : 'Inactive'" 
                        size="small" />
                <span v-if="lastKeyboardShortcut" class="ml-3">Last: <span class="text-primary-600 font-bold">{{ lastKeyboardShortcut }}</span></span>
                <Button @click="fetchGlobalShortcuts" 
                        class="p-button-text p-button-sm ml-2"
                        icon="pi pi-sync" />
                <Button @click="clearShortcuts" 
                        class="p-button-text p-button-sm p-button-danger ml-1"
                        icon="pi pi-trash" 
                        title="Clear shortcut history"/>
            </p>
            
            <!-- Enhanced Global shortcuts section -->
            <div v-if="globalShortcuts.length > 0" class="global-shortcuts-section">
                <p class="text-sm text-600 font-bold p-2">Global Shortcuts Detected: ({{ globalShortcuts.length }})</p>
                <ul class="m-0 p-0 text-sm">
                    <li v-for="(shortcut, index) in globalShortcuts" :key="index" class="shortcut-item">
                        <span class="shortcut-command">{{ shortcut.command }}</span>
                        <span class="shortcut-time">{{ formatTimestamp(shortcut.timestamp) }}</span>
                    </li>
                </ul>
            </div>
        </div>
    </div>

    <!-- Settings Dialog -->
    <Dialog v-model:visible="showSettings" modal header="Settings" :style="{ width: '450px' }">
        <div class="flex flex-column gap-3 p-3">
            <h4 class="m-0 mb-2">Backend Environment</h4>
            <p class="text-sm text-600 mt-0 mb-3">Choose which backend server to connect to. Changes take effect immediately.</p>
            
            <div v-for="option in environmentOptions" :key="option.value" class="environment-option flex align-items-center gap-3 p-3 mb-2 border-round">
                <RadioButton 
                    v-model="selectedEnvironment" 
                    :inputId="option.value" 
                    :value="option.value" 
                />
                <label :for="option.value" class="cursor-pointer flex-1">
                    <div class="font-semibold text-lg">{{ option.label }}</div>
                    <div class="text-sm text-600">{{ option.url }}</div>
                </label>
            </div>
            
            <div class="flex align-items-center gap-2 mt-2 p-2 bg-primary-50 border-round">
                <i class="pi pi-info-circle text-primary-500"></i>
                <span class="text-sm text-primary-800">Current: {{ selectedEnvironment === 'staging' ? 'Staging' : 'Development' }}</span>
            </div>
        </div>
        
        <template #footer>
            <Button label="Cancel" text @click="showSettings = false" />
            <Button label="Save & Apply" icon="pi pi-check" @click="saveEnvironmentPreference" />
        </template>
    </Dialog>

    <!-- URL Warning Dialog -->
    <Dialog v-model:visible="showUrlWarning" modal header="Content Extraction Warning" :style="{ width: '500px' }">
        <div class="flex flex-column gap-3 p-3">
            <div class="flex align-items-center gap-2 mb-2">
                <i class="pi pi-exclamation-triangle text-orange-500" style="font-size: 1.5rem;"></i>
                <h4 class="m-0">Potential Content Extraction Issues</h4>
            </div>
            
            <p class="text-sm text-600 mt-0 mb-3">
                This page may have issues that prevent successful content extraction:
            </p>
            
            <div v-if="urlWarningData" class="flex flex-column gap-2">
                <div v-for="(warning, index) in urlWarningData.warnings" :key="index" 
                     class="flex align-items-start gap-2 p-2 bg-orange-50 border-round">
                    <i class="pi pi-info-circle text-orange-500 mt-1"></i>
                    <span class="text-sm text-700">{{ warning }}</span>
                </div>
            </div>
            
            <div class="flex align-items-center gap-2 mt-2 p-2 bg-blue-50 border-round">
                <i class="pi pi-info-circle text-blue-500"></i>
                <span class="text-sm text-blue-800">
                    You can still proceed, but the extracted content may be incomplete or contain placeholder text.
                </span>
            </div>
        </div>
        
        <template #footer>
            <Button label="Cancel" text @click="showUrlWarning = false; proceedWithBookmark = false" />
            <Button label="Proceed Anyway" icon="pi pi-check" @click="confirmProceedWithBookmark" />
        </template>
    </Dialog>
</template>
<script setup>
import { ref, onMounted, watch, nextTick, onUnmounted } from 'vue'
import { cleanUrl, CommunicationEnum, formatUrlsAsLinks, detectPageType } from '../composables/utils.js';
import Button from 'primevue/button';
import DocSummary from './DocSummary.vue';
import ChatInterface from './ChatInterface.vue';
import GoogleLoginButton from './GoogleLoginButton.vue';
import ProgressBar from 'primevue/progressbar';
import Message from 'primevue/message';
import useAuth from '../composables/useAuth.js';
import Textarea from 'primevue/textarea';
import ProgressSpinner from 'primevue/progressspinner';
import Dialog from 'primevue/dialog';
import RadioButton from 'primevue/radiobutton';

const { handleSignOut, handleSignIn } = useAuth()

const AppStatusEnum = {
    INITIALIZING: {
        state: 'initializing',
        message: 'Starting service...',
        severity: 'info'
    },
    SERVER_DOWN: {
        state: 'server_down',
        message: 'Error connecting to server',
        severity: 'error'
    },
    CONNECTION_ERROR: {
        state: 'connection_error',
        message: 'Unable to connect to server',
        severity: 'error'
    },
    UNAUTHENTICATED: {
        state: 'unauthenticated',
        message: null,
        severity: 'info'
    },
    SERVER_READY: {
        state: 'server_ready',
        message: 'Ready to analyze'
    },
    PROCESSING: {
        state: 'processing',
        message: 'Processing document...',
        severity: 'info'
    },
    ERROR: {
        state: 'error',
        message: null,
        severity: 'error'
    },
    DOCUMENT_READY: {
        state: 'document_ready',
        message: null,
        severity: 'success'
    }
}

const status = ref(AppStatusEnum.INITIALIZING)
const statusMessage = ref(AppStatusEnum.INITIALIZING.message)
const bookmark = ref(null)
const bookmarks = ref([])
const active_tab = ref(null)
const doc = ref(null)
const document_summary = ref(null) // Store document summary and bullet points
const debug_mode = ref(false) // TODO: Remove this before production
const library_url = ref(import.meta.env.VITE_ICOGNITION_APP_URL || 'https://app.icognition.ai')
const progressPercent = ref(5)
const user = ref(null)
const connectionErrorMessage = ref('Unable to connect to server. Please try again.')
const isRetryingConnection = ref(false)
const connectionRetryCount = ref(0)
const suggestedQuestions = ref( [])
const selectedQuestion = ref('')
const filteredQuestions = ref([])

// Store document summaries by URL
const summariesByUrl = ref({});
// Store bookmarks by URL
const bookmarksByUrl = ref({});
// Store document IDs by URL
const documentIdsByUrl = ref({});
// Store chat session IDs by URL
const chatSessionsByUrl = ref({});
const currentChatSessionId = ref(null);
const isCreatingChatSession = ref(false);

// Add these new refs for autocomplete functionality
const showAutocomplete = ref(false);
const activeIndex = ref(-1);
const allowBlurToHide = ref(true);
const questionTextarea = ref(null);

// Add this ref to track search state
const isSearchingBookmark = ref(false);
const analyzeButton = ref(null);

// Add refs for keyboard logger
const keyboardLoggerActive = ref(true);
const lastKeyboardShortcut = ref('');

// Add ref for global shortcuts
const globalShortcuts = ref([]);

// Add ref for debug panel expansion
const debugExpanded = ref(true); // Default to expanded for better visibility

// Add ref for button focus state
const buttonHasFocus = ref(false);

// Add refs for settings dialog
const showSettings = ref(false);
const selectedEnvironment = ref('development');

// Add refs for URL warning dialog
const showUrlWarning = ref(false);
const urlWarningData = ref(null);
const proceedWithBookmark = ref(false);
const isQuickSaving = ref(false);

// Backend environment options
const environmentOptions = [
    { label: 'Staging', value: 'staging', url: 'https://stg.api.icognition.ai' },
    { label: 'Development', value: 'development', url: 'http://localhost:8000' }
];

// Load environment preference from storage
const loadEnvironmentPreference = async () => {
    try {
        const result = await chrome.storage.local.get(['backendEnvironment']);
        if (result.backendEnvironment) {
            selectedEnvironment.value = result.backendEnvironment;
            console.log('Loaded environment preference:', selectedEnvironment.value);
        }
    } catch (error) {
        console.error('Error loading environment preference:', error);
    }
};

// Save environment preference and reload
const saveEnvironmentPreference = async () => {
    try {
        await chrome.storage.local.set({ backendEnvironment: selectedEnvironment.value });
        console.log('Saved environment preference:', selectedEnvironment.value);
        
        // Show success message
        status.value = {
            ...AppStatusEnum.SERVER_READY,
            message: `Switched to ${selectedEnvironment.value === 'staging' ? 'Staging' : 'Development'} environment`
        };
        
        // Close dialog
        showSettings.value = false;
        
        // Notify background script to update base URL
        chrome.runtime.sendMessage({
            name: 'update-environment',
            environment: selectedEnvironment.value
        });
        
        // Clear cached data and reconnect
        summariesByUrl.value = {};
        bookmarksByUrl.value = {};
        documentIdsByUrl.value = {};
        
        // Refresh current page data
        if (active_tab.value && active_tab.value.url) {
            handleTabChange(active_tab.value);
        }
    } catch (error) {
        console.error('Error saving environment preference:', error);
        handleError('Failed to save environment preference');
    }
};

onMounted(() => {
    console.log('SidePanel component mounted');
    
    // Load environment preference
    loadEnvironmentPreference();
    
    // Establish connection with background script to indicate side panel is open
    const port = chrome.runtime.connect({ name: 'sidepanel' });
    
    // Check if server is running
    chrome.runtime.sendMessage({ name: 'server-is' }).then((response) => {
        console.log('Status -> server-is', response)
        if (response.status === 'up') {
            // If server is up, check user state
            chrome.storage.session.get(["session_user"]).then((session) => {
                // Validate that session_user exists AND has valid authentication data
                if (session.session_user && session.session_user.stsTokenManager && session.session_user.uid) {
                    status.value = AppStatusEnum.SERVER_READY
                    statusMessage.value = AppStatusEnum.SERVER_READY.message
                    user.value = session.session_user
                    console.log('User authenticated, status:', status.value.state);
                } else {
                    // Invalid or incomplete user data, clear it and show login
                    if (session.session_user) {
                        console.log('Invalid user data found, clearing session_user');
                        chrome.storage.session.remove('session_user');
                    }
                    status.value = AppStatusEnum.UNAUTHENTICATED
                    statusMessage.value = AppStatusEnum.UNAUTHENTICATED.message
                    console.log('User not authenticated, status:', status.value.state);
                }
            })
        } else {
            status.value = AppStatusEnum.SERVER_DOWN
            console.log('Server is down, status:', status.value.state);
        }
    })

    // Set up tab change listeners - use a single source of truth
    chrome.tabs.onActivated.addListener(async (activeInfo) => {
        console.log('Tab activated event fired with tabId:', activeInfo.tabId);
        const tab = await chrome.tabs.get(activeInfo.tabId);
        console.log('Retrieved tab info:', tab);
        if (tab && tab.url) {
            handleTabChange(tab);
        }
    });
    
    chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
        console.log('Tab updated event fired:', { tabId, changeInfo, url: tab.url });
        if (changeInfo.status === 'complete' && tab.url) {
            handleTabChange(tab);
        }
    });
    
    // Initial load - get current tab
    chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
        console.log('Initial tab query result:', tabs);
        if (tabs && tabs[0]) {
            console.log('Setting initial tab:', tabs[0]);
            handleTabChange(tabs[0]);
        }
    });

    // Add event listener for keyboard navigation
    document.addEventListener('keydown', handleKeyDown);

    // Add keyboard shortcut logger
    document.addEventListener('keydown', logKeyboardShortcut);

    // Add listener for global shortcuts coming from background
    chrome.runtime.onMessage.addListener((request) => {
        if (request.name === 'shortcut-logged' && request.shortcut) {
            if (globalShortcuts.value.length >= 20) {
                globalShortcuts.value.pop();
            }
            globalShortcuts.value.unshift(request.shortcut);
        }
    });
    
    // Fetch any existing shortcuts
    fetchGlobalShortcuts();

    // After the panel is fully mounted, run a one-time initialization
    nextTick(() => {
        // Wait for any potential UI rendering to complete
        setTimeout(() => {
            // Check for URL parameters to see if this was opened via keyboard shortcut
            const url = new URL(window.location.href);
            const fromShortcut = url.searchParams.get('from_shortcut');
            
            if (fromShortcut === 'true') {
                console.log('Panel was opened via keyboard shortcut, checking focus targets');
                
                // Wait a bit longer for all elements to fully initialize
                setTimeout(() => {
                    if (status.value.state === AppStatusEnum.SERVER_READY.state && 
                        (!chat_messages.value || chat_messages.value.length === 0) &&
                        !isSearchingBookmark.value) {
                        
                        console.log('Auto-focusing analyze button on initial mount');
                        focusAnalyzeButton();
                    } else if (chat_messages.value && chat_messages.value.length > 0) {
                        console.log('Auto-focusing question input on initial mount');
                        focusQuestionInput();
                    }
                }, 500);
            }
        }, 100);
    });
});

onUnmounted(() => {
    document.removeEventListener('keydown', handleKeyDown);
    // Remove keyboard shortcut logger when component unmounts
    document.removeEventListener('keydown', logKeyboardShortcut);
    // Remove the chat scroll keyboard listener when component unmounts
    // document.removeEventListener('keydown', handleScrollKeyEvents);
});

// Add the handleTabChange function
const handleTabChange = (tab) => {
    // Prevent duplicate processing if the URL hasn't changed
    if (active_tab.value?.url === tab.url) {
        console.log('Tab URL unchanged, skipping processing');
        return;
    }

    console.log('handleTabChange called with tab:', tab);
    
    if (!tab || !tab.url) {
        console.log('handleTabChange: Invalid tab or missing URL');
        return;
    }
    
    console.log('Current status before tab change:', status.value.state);
    console.log('Current active_tab:', active_tab.value?.url);
    
    // Save current document summary if it exists
    if (active_tab.value && active_tab.value.url && document_summary.value) {
        const cleanedUrl = cleanUrl(active_tab.value.url);
        console.log('Saving document summary for URL:', cleanedUrl);
        summariesByUrl.value[cleanedUrl] = {...document_summary.value};
        
        if (bookmark.value) {
            bookmarksByUrl.value[cleanedUrl] = {...bookmark.value};
            console.log('Saving bookmark for URL:', cleanedUrl);
        }
        
        if (doc.value) {
            documentIdsByUrl.value[cleanedUrl] = doc.value.id;
            console.log('Saving document ID for URL:', cleanedUrl);
        }
    }
    
    // Update active tab
    active_tab.value = tab;
    const currentUrl = cleanUrl(tab.url);
    console.log('New active tab URL (cleaned):', currentUrl);
    
    // Reset all states
    document_summary.value = null;
    bookmark.value = null;
    doc.value = null;
    progressPercent.value = 5;
    console.log('Reset summary, bookmark, and doc');
    
    // Check if we have a saved summary for this URL
    if (summariesByUrl.value[currentUrl]) {
        console.log('Found saved summary for URL:', currentUrl);
        document_summary.value = summariesByUrl.value[currentUrl];
        bookmark.value = bookmarksByUrl.value[currentUrl] || null;
        
        if (documentIdsByUrl.value[currentUrl]) {
            status.value = AppStatusEnum.DOCUMENT_READY;
            console.log('Setting status to DOCUMENT_READY');
            initializeChatSession(currentUrl, documentIdsByUrl.value[currentUrl]);
        }
    } else if (user.value) {
        // If no saved chat but user is logged in, check for bookmarks
        // Don't set status here, let searchBookmarksByUrl handle it
        isSearchingBookmark.value = true;
        console.log('No saved chat, user logged in, searching bookmarks');
        console.log('Searching bookmarks for URL:', currentUrl);
        searchBookmarksByUrl(currentUrl);
    } else {
        // If no user is logged in, set status to UNAUTHENTICATED
        status.value = AppStatusEnum.UNAUTHENTICATED;
        console.log('No user logged in, setting status to UNAUTHENTICATED');
    }
    
    // Attempt to initialize chat session if we have a document ID
    if (documentIdsByUrl.value[currentUrl]) {
        initializeChatSession(currentUrl, documentIdsByUrl.value[currentUrl]);
    }

    console.log('Final status after tab change:', status.value.state);
};

watch(user, (after, before) => {
    if (after) {
        console.log('User logged in! ', user.value)
        status.value = AppStatusEnum.SERVER_READY
        if (active_tab.value) {
            searchBookmarksByUrl(active_tab.value.url);
        }
    } else {
        console.log('User logged out!')
        status.value = AppStatusEnum.UNAUTHENTICATED
        chrome.storage.local.remove('bookmarks')
        bookmarks.value = []
        // Clear all saved summaries when user logs out
        summariesByUrl.value = {};
        bookmarksByUrl.value = {};
        bookmarksByUrl.value = {};
        documentIdsByUrl.value = {};
        chatSessionsByUrl.value = {};
        currentChatSessionId.value = null;
    }
});

const searchBookmarksByUrl = async (url) => {
    console.log('searchBookmarksByUrl called with URL:', url);
    
    if (!url) {
        console.log('searchBookmarksByUrl -> url is null')
        isSearchingBookmark.value = false;
        return;
    }
    
    if (!user.value) {
        console.log('searchBookmarksByUrl -> user not authenticated')
        isSearchingBookmark.value = false;
        status.value = AppStatusEnum.UNAUTHENTICATED;
        return;
    }

    const cleanedUrl = cleanUrl(url);
    console.log('searchBookmarksByUrl cleaned URL:', cleanedUrl);
    
    try {
        // Check if we already have a summary for this URL in memory
        if (summariesByUrl.value[cleanedUrl]) {
            console.log('Found summary in memory for URL:', cleanedUrl);
            document_summary.value = summariesByUrl.value[cleanedUrl];
            bookmark.value = bookmarksByUrl.value[cleanedUrl] || null;
            status.value = AppStatusEnum.DOCUMENT_READY;
            console.log('Setting status to DOCUMENT_READY (found summary in memory)');
            isSearchingBookmark.value = false;
            return;
        }

        // Check local storage first
        const value = await chrome.storage.local.get(["bookmarks"]);
        console.log('Got bookmarks from storage:', value.bookmarks ? value.bookmarks.length : 0);

        if (value.bookmarks) {
            value.bookmarks = value.bookmarks.filter(bookmark => bookmark != null && bookmark !== undefined);
            console.log('Filtered bookmarks count:', value.bookmarks.length);
            
            const found = value.bookmarks.find(bookmark => bookmark.url === cleanedUrl);
            if (found) {
                console.log('Found bookmark in local storage:', found);
                bookmark.value = found;
                status.value = AppStatusEnum.SERVER_READY;
                isSearchingBookmark.value = false;
                
                // Try to fetch the document details from server
                try {
                    console.log('Fetching document details for bookmark:', found.id);
                    const response = await chrome.runtime.sendMessage({
                        name: 'fetch-bookmark-document',
                        bookmarkId: found.id
                    });
                    
                    if (response && response.success && response.document) {
                        console.log('Got document from server:', response.document);
                        document_summary.value = {
                            title: response.document.title,
                            summary: response.document.ai_is_about,
                            bullet_points: response.document.ai_bullet_points
                        };
                        doc.value = response.document;
                        status.value = AppStatusEnum.DOCUMENT_READY;
                        
                        // Cache the summary
                        summariesByUrl.value[cleanedUrl] = {...document_summary.value};
                        bookmarksByUrl.value[cleanedUrl] = {...bookmark.value};
                        documentIdsByUrl.value[cleanedUrl] = response.document.id;
                        
                        // Initialize chat session
                        initializeChatSession(cleanedUrl, response.document.id);
                    } else {
                        // Use the freshest bookmark data if available, otherwise original local one
                        const currentBookmark = (response && response.bookmark) ? response.bookmark : found;
                        const docId = currentBookmark?.document_id || found?.document_id;

                        if (docId) {
                            console.log('Using cached document ID to initialize chat');
                            doc.value = { id: docId, title: currentBookmark.title || found.title };
                            status.value = AppStatusEnum.DOCUMENT_READY;
                            
                            const bookmarkToSave = {...currentBookmark};
                            if (!bookmarkToSave.document_id && docId) {
                                bookmarkToSave.document_id = docId;
                            }
                            bookmarksByUrl.value[cleanedUrl] = bookmarkToSave;
                            
                            documentIdsByUrl.value[cleanedUrl] = docId;
                            initializeChatSession(cleanedUrl, docId);
                        } else {
                            status.value = AppStatusEnum.SERVER_READY;
                        }
                    }
                } catch (error) {
                    console.error('Error fetching document from server:', error);
                    // Still show the bookmark but without document summary
                }
                return;
            }
        }

        // If we reach here, no bookmark was found locally
        console.log('No bookmarks found in local storage, checking server via background...');
        
        try {
            const response = await chrome.runtime.sendMessage({ 
                name: 'check-for-bookmarks',
                tab: { url: url, id: active_tab.value?.id }
            });
            
            if (response && response.bookmark) {
                console.log('Found bookmark on server:', response.bookmark);
                bookmark.value = response.bookmark;
                
                // Fetch document details for this server-found bookmark
                console.log('Fetching document details for server bookmark:', response.bookmark.id);
                const docResponse = await chrome.runtime.sendMessage({
                    name: 'fetch-bookmark-document',
                    bookmarkId: response.bookmark.id
                });
                
                if (docResponse && docResponse.success && docResponse.document) {
                    console.log('Got document from server:', docResponse.document);
                    document_summary.value = {
                        title: docResponse.document.title,
                        summary: docResponse.document.ai_is_about,
                        bullet_points: docResponse.document.ai_bullet_points
                    };
                    doc.value = docResponse.document;
                    status.value = AppStatusEnum.DOCUMENT_READY;
                    
                    // Cache the summary
                    summariesByUrl.value[cleanedUrl] = {...document_summary.value};
                    bookmarksByUrl.value[cleanedUrl] = {...bookmark.value}; 
                    documentIdsByUrl.value[cleanedUrl] = docResponse.document.id;
                    
                    // Initialize chat session
                    initializeChatSession(cleanedUrl, docResponse.document.id);
                } else {
                     // Use the freshest bookmark data if available, otherwise original
                     const currentBookmark = (docResponse && docResponse.bookmark) ? docResponse.bookmark : response.bookmark;
                     
                     if (currentBookmark && currentBookmark.document_id) {
                         console.log('Using bookmark document ID fallback');
                         doc.value = { id: currentBookmark.document_id, title: currentBookmark.title };
                         status.value = AppStatusEnum.DOCUMENT_READY;
                         
                         bookmarksByUrl.value[cleanedUrl] = {...currentBookmark};
                         documentIdsByUrl.value[cleanedUrl] = currentBookmark.document_id;
                         initializeChatSession(cleanedUrl, currentBookmark.document_id);
                     } else {
                         status.value = AppStatusEnum.SERVER_READY;
                     }
                }
            } else {
                console.log('No bookmark found on server');
                status.value = AppStatusEnum.SERVER_READY;
            }
        } catch (err) {
            console.error('Error checking server for bookmarks:', err);
            status.value = AppStatusEnum.SERVER_READY;
        }

        } catch (error) {
            console.error('Error searching bookmarks by URL:', error);
            // Check if it's an auth or connection error
            const errorMessage = error?.message || error?.toString() || 'Unknown error';
            if (errorMessage.includes('Authentication token not available') || 
                errorMessage.includes('Failed to fetch') ||
                errorMessage.includes('NetworkError') ||
                errorMessage.includes('ERR_')) {
                handleConnectionError('Authentication or connection error. Please check your connection and try again.');
            } else {
                handleError('Error searching bookmarks');
                status.value = AppStatusEnum.SERVER_READY;
            }
    } finally {
        // Only set isSearchingBookmark to false if we're not in DOCUMENT_READY state
        // And not transitioning to another loading state
        if (status.value.state !== AppStatusEnum.DOCUMENT_READY.state) {
            isSearchingBookmark.value = false;
        }
    }
}

const handleConnectionError = (message) => {
    console.error('Connection error:', message);
    connectionErrorMessage.value = message;
    status.value = AppStatusEnum.CONNECTION_ERROR;
    isSearchingBookmark.value = false;
}

const handleRetryConnection = async () => {
    isRetryingConnection.value = true;
    connectionRetryCount.value++;
    
    try {
        // First check if server is up
        const serverCheck = await chrome.runtime.sendMessage({ name: 'server-is' });
        
        if (serverCheck && serverCheck.status === 'up') {
            // Server is up, try to refresh auth and reconnect
            console.log('Server is up, attempting to reconnect...');
            
            // Reset connection error state
            connectionRetryCount.value = 0;
            status.value = AppStatusEnum.INITIALIZING;
            
            // Try to search bookmarks again if we have an active tab
            if (active_tab.value && active_tab.value.url && user.value) {
                await new Promise(resolve => setTimeout(resolve, 500)); // Small delay
                searchBookmarksByUrl(active_tab.value.url);
            } else {
                status.value = AppStatusEnum.SERVER_READY;
            }
        } else {
            // Server is down
            if (connectionRetryCount.value >= 2) {
                connectionErrorMessage.value = 'Server is currently unavailable. Please wait a couple of minutes and try again.';
            } else {
                connectionErrorMessage.value = 'Unable to connect to server. Please try again.';
            }
            status.value = AppStatusEnum.CONNECTION_ERROR;
        }
    } catch (error) {
        console.error('Error retrying connection:', error);
        if (connectionRetryCount.value >= 2) {
            connectionErrorMessage.value = 'Server is currently unavailable. Please wait a couple of minutes and try again.';
        } else {
            connectionErrorMessage.value = 'Unable to connect to server. Please try again.';
        }
        status.value = AppStatusEnum.CONNECTION_ERROR;
    } finally {
        isRetryingConnection.value = false;
    }
}

// Initialize chat session
const initializeChatSession = async (url, docId) => {
    if (!docId) return;
    
    // Check cache first
    if (chatSessionsByUrl.value[url]) {
        console.log('Using cached chat session:', chatSessionsByUrl.value[url]);
        currentChatSessionId.value = chatSessionsByUrl.value[url];
        return;
    }
    
    isCreatingChatSession.value = true;
    try {
        console.log('Creating new chat session for doc:', docId);
        const response = await chrome.runtime.sendMessage({
            name: 'create-chat-session',
            data: {
                title: 'Extension Chat', // Backend might generate a better one or we can update it
                scope_type: 'document',
                scope_id: docId
            }
        });
        
        if (response && response.success) {
            console.log('Chat session created:', response.data);
            chatSessionsByUrl.value[url] = response.data.id;
            currentChatSessionId.value = response.data.id;
        } else {
            console.error('Failed to create chat session:', response.error);
        }
    } catch (error) {
        console.error('Error initializing chat:', error);
    } finally {
        isCreatingChatSession.value = false;
    }
};

// Add CSS to ensure chat panel takes specific height
const style = document.createElement('style');
style.textContent = `
  .custom-chat-height {
    height: calc(100vh - 8rem) !important; /* Adjust based on header height */
  }
`;
document.head.appendChild(style);

chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    console.log('onMessage:', request.name, request.data || '');
    
    // Add a handler for panel status check
    if (request.name === 'panel-status-check') {
        console.log('Received panel status check - panel is open');
        sendResponse({ open: true });
        return true;
    }
    
    // Handle focus-input message with context awareness
    if (request.name === 'focus-input') {
        console.log('Received focus-input message:', request.data);
        
        // Check if this is a fresh panel open
        const isFreshOpen = request.data?.freshOpen || false;
        const isFinalAttempt = request.data?.finalAttempt || false;
        
        // If it's a fresh open or final attempt, use a longer delay
        const focusDelay = isFreshOpen ? (isFinalAttempt ? 1000 : 300) : 100;
        
        console.log(`Using focus delay of ${focusDelay}ms (freshOpen: ${isFreshOpen}, finalAttempt: ${isFinalAttempt})`);
        
        // Use setTimeout with appropriate delay
        setTimeout(() => {
            // Decide what to focus based on the current state
            const context = request.data?.context || 'auto';
            
            // Log more detailed diagnostic info
            console.log('Focus request details:', {
                chatExists: chat_messages.value && chat_messages.value.length > 0,
                appState: status.value.state,
                analyzeButtonAvailable: !!analyzeButton.value,
                searchingBookmark: isSearchingBookmark.value,
                freshPanelOpen: isFreshOpen
            });
            
            // If chat exists, focus the input field
            if (chat_messages.value && chat_messages.value.length > 0) {
                focusQuestionInput();
            } 
            // If no chat but "Analyze This Page" button is visible, focus that
            else if (status.value.state === AppStatusEnum.SERVER_READY.state && 
                     (!chat_messages.value || chat_messages.value.length === 0) &&
                     !isSearchingBookmark.value) {
                
                // Check if the analyze button is in the DOM and try to focus it
                if (analyzeButton.value) {
                    console.log('Analyze button found, focusing it');
                    focusAnalyzeButton();
                } else {
                    console.log('Analyze button not found in refs, trying querySelector');
                    
                    // Fallback to using querySelector if the ref isn't working
                    const btnEl = document.querySelector('button.p-button-primary');
                    if (btnEl) {
                        console.log('Found button via querySelector, focusing it');
                        btnEl.focus();
                        btnEl.classList.add('button-focus-highlight');
                        setTimeout(() => {
                            btnEl.classList.remove('button-focus-highlight');
                        }, 2000);
                    } else {
                        console.error('Could not find analyze button via querySelector');
                    }
                }
            }
            // Otherwise, try to focus the input anyway
            else {
                console.log('No valid focus target found, trying question input as fallback');
                focusQuestionInput();
            }
            
            // Send response back to indicate success
            if (sendResponse) {
                try {
                    sendResponse({ 
                        success: true, 
                        activeElement: document.activeElement?.tagName,
                        activeElementId: document.activeElement?.id,
                        activeElementClass: document.activeElement?.className,
                        appState: status.value.state
                    });
                } catch (e) {
                    console.error('Error sending response:', e);
                }
            }
        }, focusDelay);
        
        return true; // Keep the message channel open for the async response
    }
    
    if (request.name === CommunicationEnum.NEW_DOC) {
        console.log('NEW_DOC received:', request.data);
        doc.value = request.data
        document_summary.value = {
            title: request.data.title,
            summary: request.data.ai_is_about,
            bullet_points: request.data.ai_bullet_points
        }
        
        // Update progress to 100% when document is ready
        progressPercent.value = 100;
        
        status.value = AppStatusEnum.DOCUMENT_READY
        console.log('New document received, status:', status.value.state)
        console.log('Document summary:', document_summary.value)
        
        // Parse document ID (backend may send as string)
        const documentId = request.data.id ? parseInt(request.data.id) : request.data.id;
        console.log('Document ID (parsed):', documentId);
        
        // Save document ID and summary for current URL
        if (active_tab.value && active_tab.value.url) {
            const cleanedUrl = cleanUrl(active_tab.value.url);
            documentIdsByUrl.value[cleanedUrl] = documentId;
            summariesByUrl.value[cleanedUrl] = {...document_summary.value};
            
            // Auto-start chat session
            initializeChatSession(cleanedUrl, documentId);
            
            // Update bookmark with document_id if we have the bookmark
            if (bookmark.value && bookmark.value.id) {
                bookmark.value.document_id = documentId;
                bookmark.value.is_processed = true;
                bookmark.value.processing_status = 'completed';
                bookmarksByUrl.value[cleanedUrl] = {...bookmark.value};
                console.log('Updated bookmark with document_id:', documentId);
                console.log('Updated bookmark:', bookmark.value);
            } else {
                console.warn('No bookmark found to update with document_id');
            }
        } else {
            console.warn('No active tab URL found to save document');
        }
    }

    // Chat-related message handlers removed - will be re-implemented in future update

    if (request.name === CommunicationEnum.ERROR) {
        console.log('Error -> request:', request)
        handleError('Error processing document: ' + request.data);
    }

    if (request.name === 'connection-error') {
        console.log('Connection error received from background:', request.error);
        const errorMsg = request.type === 'auth_or_connection' 
            ? 'Authentication or connection error. Please check your connection and try again.'
            : 'Unable to connect to server. Please try again.';
        handleConnectionError(errorMsg);
    }
    
    if (request.name === 'sse-disconnected') {
        console.log('SSE disconnected notification received');
        // Only show error if user is authenticated and not already in error state
        if (user.value && status.value.state !== AppStatusEnum.CONNECTION_ERROR.state) {
            console.log('SSE connection lost, backend will attempt to reconnect automatically');
            // Don't show error UI, just log it - reconnection is automatic
        }
    }
    
    if (request.name === 'sse-reconnected') {
        console.log('SSE reconnected notification received');
        // Clear any connection errors
        if (status.value.state === AppStatusEnum.CONNECTION_ERROR.state) {
            status.value = AppStatusEnum.SERVER_READY;
            connectionErrorMessage.value = '';
        }
    }

    if (request.name === CommunicationEnum.PROGRESS_PERCENTAGE) {
        console.log('PROGRESS_PERCENTAGE received:', request.data, 'Current status:', status.value.state, 'doc.value:', doc.value);
        if (status.value !== AppStatusEnum.DOCUMENT_READY && doc.value == null) {
            status.value = AppStatusEnum.PROCESSING
            // Backend sends absolute percentage values, not increments
            progressPercent.value = Math.min(99, request.data)
            console.log('Progress updated to:', progressPercent.value, '%')
        } else {
            console.log('Progress update ignored - status:', status.value.state, 'doc exists:', !!doc.value);
        }
    }
    
    if (request.name === 'error-bookmarking') {
        console.log('error-bookmarking -> request', request)
        doc.value = null;
        handleError(request.data);
        sendResponse({ message: 'bookmark-page received' })
    }

    if (request.name === 'question-answers-ready') {
        console.log('document-ready -> request', request)
        doc.value = request.data
        status.value = AppStatusEnum.SERVER_READY
        sendResponse({ message: 'document-ready recived' })
    }

    // Suggested questions handler removed - will be re-implemented in future update
})

chrome.storage.onChanged.addListener((changes, namespace) => {
    for (let [key, { oldValue, newValue }] of Object.entries(changes)) {
        console.log(
            `Storage key "${key}" in namespace "${namespace}" changed.`,
            `Old value was "${oldValue}", new value is "${newValue}".`
        );
        if (key === 'bookmarks' && namespace === 'local') {
            if (newValue === undefined) {
                bookmarks.value = []
            } else {
                bookmarks.value = newValue

                if (active_tab.value) {
                    console.log('Update Bookmarks -> active_tab:', active_tab.value)
                    searchBookmarksByUrl(active_tab.value.url)
                } else {
                   //Set status to ready
                   status.value = AppStatusEnum.SERVER_READY
                }
            }
        }
        
        if (key === 'session_user' && namespace === 'session') {
            // Validate that the new value has valid authentication data
            if (newValue && newValue.stsTokenManager && newValue.uid) {
                user.value = newValue;
                console.log('Valid session_user update received');
            } else if (newValue === undefined) {
                // User logged out
                user.value = null;
                console.log('User logged out');
            } else {
                // Invalid user data, don't update
                console.log('Invalid session_user update ignored:', newValue);
                // Clear the invalid data
                chrome.storage.session.remove('session_user');
            }
        }
    }
});

const confirmProceedWithBookmark = () => {
    showUrlWarning.value = false;
    proceedWithBookmark.value = true;
    // Call the actual bookmark creation
    createBookmark();
}

const createBookmark = async () => {
    progressPercent.value = 5;
    // Only set to processing if we aren't already ready (shouldn't happen here usually but good practice)
    if (status.value.state !== AppStatusEnum.DOCUMENT_READY.state) {
        status.value = AppStatusEnum.PROCESSING
        statusMessage.value = AppStatusEnum.PROCESSING.message
    }

    chrome.runtime.sendMessage({name: 'bookmark-page', tab: active_tab.value}).then(async (response) => {
        console.log('handleBookmark -> response:', response)

        if (!response) {
            console.error('handleBookmark -> No response received');
            handleError('No response from bookmark creation');
            return;
        }

        if (response.status === 201 || response.status === 200) {
            // Clean the URL in the bookmark before storing
            const cleanedBookmark = { ...response.content };
            if (cleanedBookmark.url) {
                cleanedBookmark.url = cleanUrl(cleanedBookmark.url);
            }
            bookmark.value = cleanedBookmark;
            
            // Save bookmark for current URL
            if (active_tab.value && active_tab.value.url) {
                bookmarksByUrl.value[cleanUrl(active_tab.value.url)] = {...bookmark.value};
            }

            // Check if we already received the document via SSE (Race condition fix)
            if (status.value.state === AppStatusEnum.DOCUMENT_READY.state) {
                console.log('Document already ready (SSE received before HTTP response), skipping PROCESSING state');
                return;
            }

            // If bookmark is already processed but we don't have the document yet, fetch it
            if (cleanedBookmark.is_processed && cleanedBookmark.processing_status === 'completed') {
                console.log('Bookmark is already processed, fetching document details...');
                try {
                    const docResponse = await chrome.runtime.sendMessage({
                        name: 'fetch-bookmark-document',
                        bookmarkId: cleanedBookmark.id
                    });
                    
                    if (docResponse && docResponse.success && docResponse.document) {
                         console.log('Fetched document details:', docResponse.document);
                         // Use the NEW_DOC handler logic
                         doc.value = docResponse.document;
                         document_summary.value = {
                            title: docResponse.document.title,
                            summary: docResponse.document.ai_is_about,
                            bullet_points: docResponse.document.ai_bullet_points
                         };
                         progressPercent.value = 100;
                         status.value = AppStatusEnum.DOCUMENT_READY;
                         
                         // Initialize chat
                         if (active_tab.value && active_tab.value.url) {
                            const cleanedUrl = cleanUrl(active_tab.value.url);
                            documentIdsByUrl.value[cleanedUrl] = docResponse.document.id;
                            summariesByUrl.value[cleanedUrl] = {...document_summary.value};
                            initializeChatSession(cleanedUrl, docResponse.document.id);
                         }
                         return;
                    }
                } catch (err) {
                    console.error('Failed to fetch document:', err);
                    // Fall through to waiting state logic
                }
            }

            status.value = AppStatusEnum.PROCESSING
            console.log('Bookmark created, waiting for processing. Bookmark ID:', cleanedBookmark.id);
            console.log('Progress will be updated via SSE messages');
            
        } else {
            //If the status is not server down, that is the reason for the error
            if (status.value.state !== AppStatusEnum.SERVER_DOWN.state) {
                const errorMessage = response.content?.detail || 'Error creating bookmark';
                handleError(errorMessage);
            }
        }
    }).catch((error) => {
        console.error('handleBookmark -> Error:', error);
        handleError('Failed to create bookmark: ' + (error.message || 'Unknown error'));
    });
}

const handleBookmark = async () => {
    // Reset proceed flag
    proceedWithBookmark.value = false;
    
    // Check if we have an active tab with URL
    if (!active_tab.value || !active_tab.value.url) {
        handleError('No active tab URL found');
        return;
    }
    
    // Check if we can inject content (extension can get HTML from the page)
    // For most pages, we can inject, so assume hasContent = true
    // Only show warning if it's a critical issue that can't be resolved with content injection
    const hasContent = true; // Extension injects content script to get HTML
    
    // Detect page type and potential issues
    const pageDetection = detectPageType(active_tab.value.url, hasContent);
    
    // Only show warning for critical issues that can't be resolved with content
    // Skip warning if it's an article page with content available (extension will send HTML)
    const shouldShowWarning = pageDetection.issues && pageDetection.issues.length > 0 && 
                              !(pageDetection.is_article && hasContent && pageDetection.has_paywall);
    
    if (shouldShowWarning) {
        urlWarningData.value = pageDetection;
        showUrlWarning.value = true;
        // Wait for user to confirm or cancel
        return;
    }
    
    // No critical issues detected, proceed directly
    createBookmark();
}

// Chat functions removed - will be re-implemented in future update

const getCurrentPageTitle = () => {
    if (active_tab.value && active_tab.value.title) {
        return active_tab.value.title.length > 40 
            ? active_tab.value.title.substring(0, 40) + '...' 
            : active_tab.value.title;
    }
    return 'Current Page';
}

// Extract metadata from page (mimics LinkPresentation behavior)
// Extracts og:title, og:description, and other Open Graph metadata
const extractPageMetadata = async (tabId) => {
    const metadata = {
        title: null,
        description: null,
        ogTitle: null,
        ogDescription: null
    };
    
    try {
        // Inject script to extract Open Graph metadata
        const results = await chrome.scripting.executeScript({
            target: { tabId: tabId },
            func: () => {
                const meta = {};
                
                // Get og:title
                const ogTitle = document.querySelector('meta[property="og:title"]');
                if (ogTitle) {
                    meta.ogTitle = ogTitle.getAttribute('content');
                }
                
                // Get og:description
                const ogDescription = document.querySelector('meta[property="og:description"]');
                if (ogDescription) {
                    meta.ogDescription = ogDescription.getAttribute('content');
                }
                
                // Get article:title as fallback
                const articleTitle = document.querySelector('meta[property="article:title"]');
                if (articleTitle) {
                    meta.articleTitle = articleTitle.getAttribute('content');
                }
                
                // Get article.headline (WSJ specific)
                const articleHeadline = document.querySelector('meta[name="article.headline"]');
                if (articleHeadline) {
                    meta.articleHeadline = articleHeadline.getAttribute('content');
                }
                
                // Get <title> tag
                meta.pageTitle = document.title;
                
                return meta;
            }
        });
        
        if (results && results[0] && results[0].result) {
            const extracted = results[0].result;
            
            // Priority: og:title > article.headline > article:title > page title
            metadata.ogTitle = extracted.ogTitle;
            metadata.ogDescription = extracted.ogDescription;
            metadata.title = extracted.ogTitle || extracted.articleHeadline || extracted.articleTitle || extracted.pageTitle;
            metadata.description = extracted.ogDescription;
            
            // Clean up title (remove common suffixes)
            if (metadata.title) {
                metadata.title = metadata.title
                    .replace(/ - WSJ$/, '')
                    .replace(/ \| WSJ$/, '')
                    .replace(/ - The Wall Street Journal$/, '')
                    .trim();
            }
            
            console.log('✅ Extracted metadata:', metadata);
        }
    } catch (error) {
        console.error('❌ Error extracting metadata:', error);
        // Fallback to tab title if extraction fails
        if (active_tab.value && active_tab.value.title) {
            metadata.title = active_tab.value.title;
        }
    }
    
    return metadata;
}

// Quick bookmark creation (LinkPresentation style)
// Extracts URL, title, and description without full analysis
const handleQuickBookmark = async () => {
    if (!active_tab.value || !active_tab.value.url) {
        handleError('No active tab URL found');
        return;
    }
    
    isQuickSaving.value = true;
    
    try {
        console.log('🔗 Quick bookmark: Extracting metadata from page...');
        
        // Extract metadata from the page
        const metadata = await extractPageMetadata(active_tab.value.id);
        
        // Get base URL from storage
        const result = await chrome.storage.local.get(['backendEnvironment']);
        const environment = result.backendEnvironment || 'staging';
        const baseUrl = environment === 'development' 
            ? 'http://localhost:8000' 
            : 'https://stg.api.icognition.ai';
        
        // Get auth token
        const session_user = await chrome.storage.session.get(["session_user"]);
        if (!session_user.session_user || !session_user.session_user.stsTokenManager) {
            handleError('User not authenticated');
            isQuickSaving.value = false;
            return;
        }
        
        const authToken = session_user.session_user.stsTokenManager.accessToken;
        
        // Prepare bookmark data
        const bookmarkData = {
            url: cleanUrl(active_tab.value.url),
            title: metadata.title || active_tab.value.title || 'Untitled',
            description: metadata.description || null,
            content: null, // No HTML content for quick save
            metadata: {
                source: 'chrome_extension_quick_save',
                extractedTitle: metadata.title,
                extractedDescription: metadata.description,
                ogTitle: metadata.ogTitle,
                ogDescription: metadata.ogDescription,
                linkPresentationStyle: true
            }
        };
        
        console.log('📤 Quick bookmark: Creating bookmark with data:', bookmarkData);
        
        // Create bookmark with metadata (mimics LinkPresentation - URL, title, description)
        const response = await fetch(`${baseUrl}/bookmarks/`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${authToken}`
            },
            body: JSON.stringify(bookmarkData)
        });
        
        if (response.ok) {
            const bookmarkResponse = await response.json();
            console.log('✅ Quick bookmark created:', bookmarkResponse);
            
            // Update local state
            bookmark.value = bookmarkResponse;
            if (active_tab.value && active_tab.value.url) {
                bookmarksByUrl.value[cleanUrl(active_tab.value.url)] = bookmarkResponse;
            }
            
            status.value = {
                ...AppStatusEnum.SERVER_READY,
                message: 'Bookmark saved successfully!'
            };
            
            // Show success message briefly
            setTimeout(() => {
                status.value = AppStatusEnum.SERVER_READY;
            }, 2000);
        } else {
            const errorData = await response.json();
            console.error('❌ Quick bookmark error:', errorData);
            handleError(errorData.detail || 'Failed to create bookmark');
        }
    } catch (error) {
        console.error('❌ Quick bookmark error:', error);
        handleError('Failed to create bookmark: ' + (error.message || 'Unknown error'));
    } finally {
        isQuickSaving.value = false;
    }
}

const handleCancelProcessing = async () => {
    console.log('Cancelling processing...');
    
    // Get document ID from various sources
    let documentId = doc.value?.id;
    if (!documentId && active_tab.value?.url) {
        const currentUrl = cleanUrl(active_tab.value.url);
        documentId = documentIdsByUrl.value[currentUrl];
    }
    
    // Send cancel message to background script
    try {
        const response = await chrome.runtime.sendMessage({
            name: 'cancel-processing',
            bookmarkId: bookmark.value?.id,
            documentId: documentId
        });
        
        if (response && response.success) {
            // Clear local state
            if (active_tab.value && active_tab.value.url) {
                const currentUrl = cleanUrl(active_tab.value.url);
                delete summariesByUrl.value[currentUrl];
                delete bookmarksByUrl.value[currentUrl];
                delete documentIdsByUrl.value[currentUrl];
            }
            
            // Reset current state
            document_summary.value = null;
            bookmark.value = null;
            doc.value = null;
            progressPercent.value = 5;
            status.value = AppStatusEnum.SERVER_READY;
            
            // Send message to background script to update badge
            if (active_tab.value) {
                chrome.runtime.sendMessage({
                    name: 'update-badge',
                    tabId: active_tab.value.id,
                    hasBookmark: false
                });
            }
            
            console.log('Processing cancelled successfully');
        } else {
            const errorMsg = response?.errors?.join(', ') || response?.error || 'Unknown error';
            console.error('Failed to cancel processing:', errorMsg);
            handleError(`Failed to cancel processing: ${errorMsg}`);
        }
    } catch (error) {
        console.error('Error cancelling processing:', error);
        handleError('Error cancelling processing');
    }
}

const clearCurrentChat = async () => {
    if (active_tab.value && active_tab.value.url) {
        const currentUrl = cleanUrl(active_tab.value.url);
        
        // Get the current bookmark ID
        const currentBookmark = bookmarksByUrl.value[currentUrl];
        if (currentBookmark && currentBookmark.id) {
            // Delete the bookmark from the server
            try {
                const response = await chrome.runtime.sendMessage({
                    name: 'delete-bookmark',
                    bookmarkId: currentBookmark.id
                });
                
                if (response.success) {
        // Clear summary for current URL
        delete summariesByUrl.value[currentUrl];
        delete bookmarksByUrl.value[currentUrl];
        delete documentIdsByUrl.value[currentUrl];
        
        // Reset current state
        document_summary.value = null;
        bookmark.value = null;
        doc.value = null;
                    status.value = AppStatusEnum.SERVER_READY;
                    
                    // Send message to background script to update badge
                    chrome.runtime.sendMessage({
                        name: 'update-badge',
                        tabId: active_tab.value.id,
                        hasBookmark: false
                    });
                } else {
                    console.error('Failed to delete bookmark:', response.error);
                    handleError('Failed to delete bookmark');
                }
            } catch (error) {
                console.error('Error deleting bookmark:', error);
                handleError('Error deleting bookmark');
            }
        } else {
            // If no bookmark ID, just clear the local state
            delete summariesByUrl.value[currentUrl];
            delete bookmarksByUrl.value[currentUrl];
            delete documentIdsByUrl.value[currentUrl];
            
            // Reset current state
            document_summary.value = null;
            bookmark.value = null;
            doc.value = null;
            status.value = AppStatusEnum.SERVER_READY;
            
            // Send message to background script to update badge
            chrome.runtime.sendMessage({
                name: 'update-badge',
                tabId: active_tab.value.id,
                hasBookmark: false
            });
        }
    }
}

function handleError(errorMessage) {
  // Set error status and messages
  status.value = {
    ...AppStatusEnum.ERROR,
    message: errorMessage  // Set the message in the status object
  };
  statusMessage.value = errorMessage;  // Also set the statusMessage for consistency
  
  // Clear document summary on error
  document_summary.value = null;
  
  // Clear from URL cache if needed
  if (active_tab.value && active_tab.value.url) {
    const currentUrl = cleanUrl(active_tab.value.url);
    delete summariesByUrl.value[currentUrl];
  }
  
  console.error('Error:', errorMessage);
}

// Update handleKeydownInTextarea to be the only handler active when textarea is focused
const handleKeydownInTextarea = (event) => {
    // If autocomplete is shown, handle navigation within dropdown
    if (showAutocomplete.value && filteredQuestions.value.length > 0) {
        switch (event.key) {
            case 'ArrowDown':
                event.preventDefault();
                // Stop event propagation to prevent global handler from also firing
                event.stopPropagation();
                console.log('Textarea ArrowDown pressed, current activeIndex:', activeIndex.value);
                
                if (activeIndex.value === -1 || activeIndex.value >= filteredQuestions.value.length - 1) {
                    // If no item is selected or at the end, go to first item
                    activeIndex.value = 0;
                } else {
                    // Simply increment the index
                    activeIndex.value += 1;
                }
                
                console.log('Textarea ArrowDown: new activeIndex:', activeIndex.value, 'item:', filteredQuestions.value[activeIndex.value]);
                
                // Ensure the active item is visible in the dropdown
                nextTick(() => {
                    const activeItem = document.querySelector('.autocomplete-item-active');
                    if (activeItem) {
                        activeItem.scrollIntoView({ block: 'nearest' });
                    }
                });
                break;
                
            case 'ArrowUp':
                event.preventDefault();
                // Stop event propagation to prevent global handler from also firing
                event.stopPropagation();
                console.log('Textarea ArrowUp pressed, current activeIndex:', activeIndex.value);
                
                if (activeIndex.value <= 0) {
                    // If no item is selected or at the beginning, go to last item
                    activeIndex.value = filteredQuestions.value.length - 1;
                } else {
                    // Simply decrement the index
                    activeIndex.value -= 1;
                }
                
                console.log('Textarea ArrowUp: new activeIndex:', activeIndex.value, 'item:', filteredQuestions.value[activeIndex.value]);
                
                // Ensure the active item is visible in the dropdown
                nextTick(() => {
                    const activeItem = document.querySelector('.autocomplete-item-active');
                    if (activeItem) {
                        activeItem.scrollIntoView({ block: 'nearest' });
                    }
                });
                break;
                
            case 'Enter':
                event.preventDefault();
                event.stopPropagation();
                if (activeIndex.value !== -1) {
                    // If an item is selected in the dropdown, select it
                    selectSuggestedQuestion(filteredQuestions.value[activeIndex.value]);
                } else {
                    // If no item is selected but dropdown is open, submit the question
                    handleAsk();
                    showAutocomplete.value = false;
                }
                break;
                
            case 'Escape':
                event.preventDefault();
                event.stopPropagation();
                showAutocomplete.value = false;
                break;
                
            case 'Tab':
                // Prevent default tab behavior and select current item if one is active
                if (activeIndex.value !== -1) {
                    event.preventDefault();
                    event.stopPropagation();
                    selectSuggestedQuestion(filteredQuestions.value[activeIndex.value]);
                }
                break;
        }
    } else {
        // When no dropdown is visible, Enter should submit the question
        if (event.key === 'Enter' && !event.shiftKey) {
            event.preventDefault();
            handleAsk();
        }
    }
};

// Update handleKeyDown to only handle keyboard navigation when the textarea is NOT focused
const handleKeyDown = (event) => {
    // Only handle dropdown navigation at the document level if:
    // 1. Suggestions are visible
    // 2. We have suggestions to show
    // 3. The textarea is NOT focused (this is important to avoid double-handling)
    if (!showAutocomplete.value || 
        filteredQuestions.value.length === 0 || 
        document.activeElement === questionTextarea.value?.$el?.querySelector('textarea')) {
        return;
    }
    
    console.log('Global key handler active - textarea is not focused');
    
    switch (event.key) {
        case 'ArrowDown':
            event.preventDefault();
            console.log('Document ArrowDown pressed, current activeIndex:', activeIndex.value);
            
            if (activeIndex.value === -1 || activeIndex.value >= filteredQuestions.value.length - 1) {
                // If no item is selected or at the end, go to first item
                activeIndex.value = 0;
            } else {
                // Simply increment the index
                activeIndex.value += 1;
            }
            
            console.log('Document ArrowDown: new activeIndex:', activeIndex.value, 'item:', filteredQuestions.value[activeIndex.value]);
            break;
            
        case 'ArrowUp':
            event.preventDefault();
            console.log('Document ArrowUp pressed, current activeIndex:', activeIndex.value);
            
            if (activeIndex.value <= 0) {
                // If no item is selected or at the beginning, go to last item
                activeIndex.value = filteredQuestions.value.length - 1;
            } else {
                // Simply decrement the index
                activeIndex.value -= 1;
            }
            
            console.log('Document ArrowUp: new activeIndex:', activeIndex.value, 'item:', filteredQuestions.value[activeIndex.value]);
            break;
            
        case 'Enter':
            if (activeIndex.value !== -1) {
                event.preventDefault();
                selectSuggestedQuestion(filteredQuestions.value[activeIndex.value]);
            }
            break;
            
        case 'Escape':
            showAutocomplete.value = false;
            break;
    }
};

// Update handleTextareaInput to ensure ordered suggestions
const handleTextareaInput = (event) => {
    const query = selectedQuestion.value;
    
    // Show autocomplete dropdown when text is entered
    showAutocomplete.value = true;
    
    // Filter questions based on input, preserving original order
    if (!query.trim().length) {
        // Make a fresh copy of the suggestions array to ensure order is maintained
        filteredQuestions.value = [...suggestedQuestions.value];
    } else {
        // Filter while preserving original order
        filteredQuestions.value = suggestedQuestions.value.filter((item) => {
            return item.toLowerCase().includes(query.toLowerCase());
        });
    }
    
    // Always reset active index when input changes
    activeIndex.value = -1;
    
    console.log('Filtered questions count:', filteredQuestions.value.length);
    console.log('Filtered questions array:', filteredQuestions.value);
};

// Update handleTextareaFocus to ensure ordered suggestions
const handleTextareaFocus = () => {
    // Show all suggestions when textarea is focused, if we have any
    if (suggestedQuestions.value.length > 0) {
        showAutocomplete.value = true;
        // Make a fresh copy of the suggestions array to ensure order is maintained
        filteredQuestions.value = [...suggestedQuestions.value];
        activeIndex.value = -1; // Reset active index when showing suggestions
        console.log('Textarea focused, showing suggestions:', filteredQuestions.value);
    }
};

// Handle textarea blur to hide dropdown with delay
const handleTextareaBlur = () => {
    // Only hide if we're allowing blur to affect visibility
    if (allowBlurToHide.value) {
        // Use setTimeout to allow click events on dropdown items to complete
        setTimeout(() => {
            showAutocomplete.value = false;
            console.log('Hiding autocomplete dropdown');
        }, 200);
    }
};

// Enhanced selectSuggestedQuestion to work with the dropdown
const selectSuggestedQuestion = (question) => {
    selectedQuestion.value = question;
    showAutocomplete.value = false;
    console.log('Selected question:', question);
    
    // Safely focus the textarea after selecting a suggestion
    nextTick(() => {
        if (questionTextarea.value && typeof questionTextarea.value.focus === 'function') {
            try {
                questionTextarea.value.focus();
            } catch (e) {
                console.error('Error focusing textarea:', e);
            }
        }
    });
};

// Improved scrollChatToBottom function to prevent scroll jittering
const scrollChatToBottom = (forceSmooth = true) => {
    console.log('Attempting to scroll to bottom, forceSmooth:', forceSmooth);
    
    // Use setTimeout to ensure DOM is fully updated
    setTimeout(() => {
        // Find all potential scrollable containers
        const chatContainer = document.querySelector('.chat-interface-container');
        const scrollableElement = document.querySelector('.custom-scrollbar');
        const docSummary = document.querySelector('.docsummary-container');
        
        // Create a common scroll function to apply consistent behavior
        const scrollElementToBottom = (element, smooth = forceSmooth) => {
            if (!element) return;
            
            try {
                // Use scrollTo with options for smoother scrolling
                element.scrollTo({
                    top: element.scrollHeight,
                    behavior: smooth ? 'smooth' : 'auto'
                });
                
                // Release scroll control after animation completes
                if (smooth) {
                    setTimeout(() => {
                        // Re-scroll with auto to ensure we reached the bottom and fix any jittering
                        element.scrollTo({
                            top: element.scrollHeight,
                            behavior: 'auto'
                        });
                    }, 300);
                }
            } catch (error) {
                console.error('Error scrolling element to bottom:', error);
                // Fallback to the simple method
                element.scrollTop = element.scrollHeight;
            }
        };
        
        // Try scrolling each potential container
        if (chatContainer) {
            scrollElementToBottom(chatContainer);
            console.log('Scrolled chat container to bottom', chatContainer.scrollHeight);
        }
        
        if (scrollableElement) {
            scrollElementToBottom(scrollableElement);
            console.log('Scrolled custom-scrollbar to bottom', scrollableElement.scrollHeight);
        }
        
        if (docSummary) {
            scrollElementToBottom(docSummary);
            console.log('Scrolled docSummary to bottom', docSummary.scrollHeight);
        }
        
        // As a fallback, try scrolling all elements with class containing 'scroll'
        document.querySelectorAll('[class*="scroll"]').forEach(el => {
            scrollElementToBottom(el, false); // Use auto behavior for these to avoid conflicts
        });
        
        // Ensure scroll is properly released for user control
        setTimeout(() => {
            // This timeout ensures we don't interfere with user scrolling after the content is loaded
            if (scrollableElement) {
                scrollableElement.style.pointerEvents = 'auto';
            }
            if (chatContainer) {
                chatContainer.style.pointerEvents = 'auto';
            }
        }, 350);
    }, 100); // Small delay to ensure DOM update has completed
};

// Update the handleAsk function to better handle the question being posted and the upcoming response
const handleAsk = () => {
    // Don't process empty questions
    if (!selectedQuestion.value || selectedQuestion.value.trim() === '') {
        console.log('Empty question, not submitting');
        return;
    }

    const questionText = selectedQuestion.value.trim();
    console.log('Submitting question:', questionText);
    
    // First try to get document ID from doc.value
    let documentId = doc.value?.id;
    
    // If not available, try to get it from the first chat message
    if (!documentId && chat_messages.value && chat_messages.value.length > 0) {
        documentId = chat_messages.value[0].chat_id;
        console.log('Using document ID from chat_messages:', documentId);
    }
    
    // Check if we have a document ID to ask against
    if (!documentId) {
        console.error('No document ID available for question');
        // Instead of calling handleError, add an error message to the chat
        addErrorMessageToChat('No document available to ask questions against');
        return;
    }
    
    // Add a temporary user question to the chat
    const tempUserQuestion = {
        id: 'temp-question-' + Date.now(),
        created_at: new Date().toISOString(),
        user_id: user.value?.uid || 'user',
        chat_id: documentId,
        chat_type: 'document',
        user_prompt: questionText,
        event_name: 'user_question',
        // Set response to null to trigger skeleton loading state
        response: null
    };
    
    // Add the user's question to the chat immediately
    if (chat_messages.value) {
        chat_messages.value.push(tempUserQuestion);
    } else {
        chat_messages.value = [tempUserQuestion];
    }
    
    // Save updated chat for current URL
    if (active_tab.value && active_tab.value.url) {
        chatsByUrl.value[cleanUrl(active_tab.value.url)] = [...chat_messages.value];
    }
    
    // Scroll to bottom to show the new question
    nextTick(() => {
        scrollChatToBottom();
    });
    
    // Clear the input after submitting
    selectedQuestion.value = '';
    
    // Hide autocomplete dropdown
    showAutocomplete.value = false;
    
    // Send message to background script to ask the question
    chrome.runtime.sendMessage({
        name: CommunicationEnum.ASK_QUESTION,
        payload: {
            document_id: documentId,
            question: questionText
        }
    }).then(response => {
        console.log('Ask question response:', response);
        
        // If response contains an immediate answer, handle it
        if (response && response.answer) {
            console.log('Got immediate answer:', response.answer);
            
            // Remove any temporary messages for this question
            chat_messages.value = chat_messages.value.filter(msg => 
                !msg.id || (typeof msg.id === 'string' && !msg.id.startsWith('temp-question-'))
            );
            
            // Add the answer immediately
            chat_messages.value.push(response.answer);
            
            // Save updated chat for current URL
            if (active_tab.value && active_tab.value.url) {
                chatsByUrl.value[cleanUrl(active_tab.value.url)] = [...chat_messages.value];
            }
            
            // Scroll to bottom to show the answer
            nextTick(() => {
                scrollChatToBottom();
            });
        }
    }).catch(error => {
        console.error('Error asking question:', error);
        // Add error to chat instead of showing banner
        addErrorMessageToChat('Error submitting your question. Please try again.');
    });
}

// Add this function for the keyboard logger
const toggleKeyboardLogger = () => {
    keyboardLoggerActive.value = !keyboardLoggerActive.value;
    console.log(`Keyboard shortcut logger ${keyboardLoggerActive.value ? 'enabled' : 'disabled'}`);
};

// Function to log keyboard shortcuts
const logKeyboardShortcut = (event) => {
    // Skip if logger is inactive
    if (!keyboardLoggerActive.value) return;
    
    // Don't log shortcuts in input fields
    if (document.activeElement && (
        document.activeElement.tagName === 'INPUT' || 
        document.activeElement.tagName === 'TEXTAREA' || 
        document.activeElement.isContentEditable
    )) {
        return;
    }
    
    // Build shortcut string
    let shortcut = '';
    if (event.ctrlKey) shortcut += 'Ctrl+';
    if (event.altKey) shortcut += 'Alt+';
    if (event.shiftKey) shortcut += 'Shift+';
    if (event.metaKey) shortcut += 'Meta+'; // Command key on Mac
    
    // Add the main key to the shortcut
    const key = event.key === ' ' ? 'Space' : event.key;
    shortcut += key;
    
    // Update the last shortcut for display
    lastKeyboardShortcut.value = shortcut;
    
    // Only log if in debug mode
    if (debug_mode.value) {
        console.log('Keyboard Shortcut:', shortcut);
        console.log('Key Details:', {
            key: event.key,
            code: event.code,
            keyCode: event.keyCode,
            ctrlKey: event.ctrlKey,
            altKey: event.altKey,
            shiftKey: event.shiftKey,
            metaKey: event.metaKey,
            handled: event.defaultPrevented,
            timestamp: new Date().toISOString()
        });
    }
};

// Add a function to fetch global shortcuts from the background script
const fetchGlobalShortcuts = () => {
    chrome.runtime.sendMessage({ name: 'get-recent-shortcuts' }, (response) => {
        if (response && response.shortcuts) {
            globalShortcuts.value = response.shortcuts;
            console.log('Received global shortcuts:', globalShortcuts.value);
        }
    });
};

// Add a function to format timestamps
const formatTimestamp = (timestamp) => {
    try {
        const date = new Date(timestamp);
        return date.toLocaleTimeString();
    } catch (e) {
        return timestamp;
    }
};

// Add function to focus the analyze button
const focusAnalyzeButton = () => {
    console.log('Attempting to focus analyze button');
    
    // First try using the ref
    if (analyzeButton.value && analyzeButton.value.$el) {
        console.log('analyzeButton ref found:', analyzeButton.value);
        
        try {
            // Set the focus state first 
            buttonHasFocus.value = true;
            
            // Focus the button
            analyzeButton.value.$el.focus({ preventScroll: false });
            console.log('Focused analyze button via ref');
            
            // Add visual indicator
            analyzeButton.value.$el.classList.add('button-focus-highlight');
            
            // Special trick to ensure focus is visually shown in all browsers
            analyzeButton.value.$el.style.outline = '3px solid var(--primary-color)';
            analyzeButton.value.$el.style.outlineOffset = '3px';
            
            setTimeout(() => {
                if (analyzeButton.value && analyzeButton.value.$el) {
                    analyzeButton.value.$el.classList.remove('button-focus-highlight');
                    // Don't remove the outline - keep it visible as long as focus remains
                }
            }, 2000);
            
            console.log('After focus via ref, active element is:', document.activeElement);
            
            // Create an animation to draw attention to the button
            createFocusAnimation();
            
            return true;
        } catch (e) {
            console.error('Error focusing analyze button via ref:', e);
        }
    } else {
        console.error('analyzeButton ref is not defined or not rendered');
    }
    
    // Fallback to using querySelector if the ref doesn't work
    try {
        const btnEl = document.querySelector('#analyze-button');
        if (btnEl) {
            console.log('Found button via querySelector, focusing it');
            
            // Set the focus state
            buttonHasFocus.value = true;
            
            btnEl.focus({ preventScroll: false });
            btnEl.classList.add('button-focus-highlight');
            
            // Special trick to ensure focus is visually shown
            btnEl.style.outline = '3px solid var(--primary-color)';
            btnEl.style.outlineOffset = '3px';
            
            setTimeout(() => {
                btnEl.classList.remove('button-focus-highlight');
                // Don't remove the outline
            }, 2000);
            
            console.log('After focus via querySelector, active element is:', document.activeElement);
            
            // Create an animation to draw attention to the button
            createFocusAnimation();
            
            return true;
        }
    } catch (e) {
        console.error('Error focusing button via querySelector:', e);
    }
    
    console.error('Could not focus analyze button via any method');
    return false;
};

// Add a function to create a focus animation overlay
const createFocusAnimation = () => {
    try {
        // Remove any existing animation
        const existingAnim = document.getElementById('focus-animation-overlay');
        if (existingAnim) {
            existingAnim.parentNode.removeChild(existingAnim);
        }
        
        // Create an overlay element
        const overlay = document.createElement('div');
        overlay.id = 'focus-animation-overlay';
        overlay.style.position = 'fixed';
        overlay.style.top = '0';
        overlay.style.left = '0';
        overlay.style.right = '0';
        overlay.style.bottom = '0';
        overlay.style.pointerEvents = 'none';
        overlay.style.zIndex = '9999';
        
        // Add it to the document
        document.body.appendChild(overlay);
        
        // Get the button position
        const button = document.getElementById('analyze-button');
        if (!button) return;
        
        const rect = button.getBoundingClientRect();
        
        // Create a highlight element
        const highlight = document.createElement('div');
        highlight.style.position = 'absolute';
        highlight.style.left = `${rect.left - 10}px`;
        highlight.style.top = `${rect.top - 10}px`;
        highlight.style.width = `${rect.width + 20}px`;
        highlight.style.height = `${rect.height + 20}px`;
        highlight.style.borderRadius = '8px';
        highlight.style.border = '3px solid var(--primary-color)';
        highlight.style.boxShadow = '0 0 0 5000px rgba(0, 0, 0, 0.3)';
        highlight.style.animation = 'pulse-focus 1.5s ease-in-out 3';
        
        // Add the highlight to the overlay
        overlay.appendChild(highlight);
        
        // Remove after animation completes
        setTimeout(() => {
            if (document.body.contains(overlay)) {
                document.body.removeChild(overlay);
            }
        }, 5000);
    } catch (e) {
        console.error('Error creating focus animation:', e);
    }
};

// Add function to toggle debug size
const toggleDebugSize = () => {
    debugExpanded.value = !debugExpanded.value;
    const debugPanel = document.querySelector('.debug');
    if (debugPanel) {
        debugPanel.style.maxHeight = debugExpanded.value ? '250px' : '40px';
    }
};

// Add function to clear shortcuts history
const clearShortcuts = () => {
    globalShortcuts.value = [];
    lastKeyboardShortcut.value = '';
    chrome.runtime.sendMessage({ name: 'clear-shortcuts' });
};

// Add function to focus the question input
const focusQuestionInput = () => {
    if (questionTextarea.value) {
        console.log('Focusing question textarea');
        nextTick(() => {
            questionTextarea.value.focus();
        });
    }
};
</script>

<style scoped>
.side-panel-container {
    display: flex;
    flex-direction: column;
    height: 100vh;
    width: 100%;
    /* Add CSS variable for primary color in RGB format for opacity support */
    --primary-color-rgb: 59, 130, 246;
}

.header {
    background: #3497BE;
    border-bottom: 1px solid #e0e0e0;
}

.chat-interface-container {
    flex: 1;
    overflow: hidden;
    display: flex;
    flex-direction: column;
}

.page-info {
    border-bottom: 1px solid #e0e0e0;
}

.message_container {
    margin: 10px;
}

.button_container {
    margin: 10px;
}

.debug {
    position: fixed;
    bottom: 60px;
    left: 0;
    right: 0;
    background-color: var(--surface-ground);
    border-top: 1px solid var(--surface-border);
    z-index: 1000;
    max-height: 250px; /* Increased from 80px to 250px */
    overflow-y: auto;
    font-family: var(--font-family);
    transition: max-height 0.3s ease;
    box-shadow: 0 -3px 10px rgba(0,0,0,0.1);
}

/* Add a toggle button for debug panel size */
.debug-toggle {
    position: absolute;
    top: 5px;
    right: 5px;
    font-size: 0.8rem;
    cursor: pointer;
    background: var(--primary-color);
    color: white;
    border-radius: 3px;
    padding: 2px 5px;
    opacity: 0.8;
}

.debug p {
    margin: 0.25rem 0;
    padding: 0.25rem 0.5rem;
    font-size: 0.75rem;
    color: var(--text-color-secondary);
}

/* Enhance the global shortcuts section */
.global-shortcuts-section {
    max-height: 150px;
    overflow-y: auto;
    background-color: var(--surface-card);
    border-radius: 5px;
    margin: 5px;
    padding: 5px;
    border: 1px solid var(--surface-border);
}

.shortcut-item {
    display: flex;
    justify-content: space-between;
    padding: 3px 8px;
    border-radius: 3px;
}

.shortcut-item:nth-child(odd) {
    background-color: var(--surface-100);
}

.shortcut-item:hover {
    background-color: var(--surface-200);
}

.shortcut-command {
    font-weight: bold;
}

.shortcut-time {
    color: var(--text-color-secondary);
    font-size: 0.7rem;
}

/* Update ask-input for textarea */
.ask-input {
    position: fixed;
    bottom: 0;
    left: 0;
    right: 0;
    background-color: var(--surface-card);
    padding: 0.5rem;
    border-top: 1px solid var(--surface-border);
    min-height: 60px;
    z-index: 1001;
    width: 100%;
    box-sizing: border-box;
}

/* Style for textarea */
.textarea-with-autocomplete {
    position: relative;
    flex: 1;
    min-width: 0; /* Prevent flex item from overflowing */
    box-sizing: border-box;
}

:deep(.p-inputtextarea) {
    width: 100% !important;
    box-sizing: border-box !important;
    resize: none;
    max-height: 120px;
    overflow-y: auto;
    line-height: 1.4;
    padding: 0.5rem 0.75rem;
    min-height: 2.8rem;
    margin: 0;
    border-radius: 6px;
}

/* Style for suggested questions */
.suggested-questions {
    max-height: 80px;
    overflow-y: auto;
    padding-bottom: 5px;
}

.suggestion-pills {
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
}

.suggestion-pill {
    background-color: #f0f7ff;
    border: 1px solid #d0e1fd;
    color: #1e3a8a;
    border-radius: 16px;
    padding: 2px 10px;
    font-size: 0.75rem;
    cursor: pointer;
    display: inline-block;
    max-width: 200px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}

.suggestion-pill:hover {
    background-color: #e0effe;
}

/* Adjust scrollbar height to account for larger ask input */
:deep(.custom-scrollbar) {
    height: calc(100vh - 250px);
}

.mb-2 {
    margin-bottom: 0.5rem;
}

.text-sm {
    font-size: 0.875rem;
}

.text-primary-800 {
    color: #1e3a8a;
}

.bg-primary-50 {
    background-color: #f0f7ff;
}

/* Add these styles to improve chat display */
:deep(.chat-message) {
    max-width: 95% !important;
    width: 95% !important;
    margin-left: auto !important;
    margin-right: auto !important;
}

:deep(.chat-message p) {
    font-size: 0.9rem !important;
    line-height: 1.4 !important;
}

:deep(.chat-message-content) {
    max-width: 95% !important;
    width: 95% !important;
}

:deep(.max-w-25) {
    max-width: 95% !important;
}

:deep(.p-card-content) {
    padding: 0.75rem !important;
}

:deep(.p-card) {
    margin-bottom: 0.75rem !important;
}

:deep(.p-inputtext) {
    font-size: 0.9rem !important;
}

:deep(.p-autocomplete) {
    width: 100%;
    display: block;
}

:deep(.p-autocomplete-panel) {
    position: absolute;
    max-height: 300px !important;
    overflow-y: auto;
    width: 100% !important;
    left: 0 !important;
    right: 0 !important;
    margin: 0 !important;
    box-sizing: border-box !important;
}

:deep(.p-autocomplete-items) {
    padding: 0 !important;
    width: 100% !important;
}

:deep(.p-autocomplete-item) {
    width: 100% !important;
    box-sizing: border-box !important;
    padding: 0.5rem 0.75rem !important;
    line-height: 1.2 !important;
    white-space: pre-wrap !important;
    word-break: break-word !important;
}

.autocomplete-container {
    position: relative;
    width: 100%;
}

.suggestion-item {
    padding: 0.5rem 0.75rem;
    line-height: 1.2;
    font-size: 0.875rem;
    color: var(--text-color);
    white-space: normal;
    word-wrap: break-word;
    border-bottom: 1px solid var(--surface-border);
}

.suggestion-item:last-child {
    border-bottom: none;
}

.suggestion-item:hover {
    background-color: var(--surface-hover);
    cursor: pointer;
}

/* Update dropdown styles for perfect alignment */
.autocomplete-dropdown {
    position: absolute;
    bottom: 100%;
    left: 0;
    width: 100%;
    background-color: white;
    border: 2px solid var(--primary-color);
    border-radius: 6px;
    box-shadow: 0 -2px 20px rgba(0, 0, 0, 0.25);
    max-height: 250px;
    overflow-y: auto;
    z-index: 9999;
    box-sizing: border-box;
    margin-bottom: 3px;
}

.debug-dropdown {
    background-color: #e3f2fd;
    color: #0d47a1;
    padding: 4px 8px;
    font-size: 12px;
    text-align: center;
    border-bottom: 1px solid #bbdefb;
}

.autocomplete-list {
    list-style: none;
    padding: 0;
    margin: 0;
}

.autocomplete-item {
    padding: 8px 12px;
    cursor: pointer;
    border-bottom: 1px solid var(--surface-border);
    white-space: normal;
    word-break: break-word;
    line-height: 1.4;
    font-size: 0.9rem;
    background-color: white;
}

.autocomplete-item:last-child {
    border-bottom: none;
}

.autocomplete-item:hover,
.autocomplete-item-active {
    background-color: var(--surface-hover);
}

/* Update the ask input container */
.ask-input {
    position: fixed;
    bottom: 0;
    left: 0;
    right: 0;
    background-color: var(--surface-card);
    padding: 0.5rem;
    border-top: 1px solid var(--surface-border);
    min-height: 60px;
    z-index: 1001;
    width: 100%;
    box-sizing: border-box;
}

/* Update the flex container to ensure proper width calculation */
.flex.gap-2 {
    position: relative;
    display: flex;
    gap: 0.5rem;
    width: 100%;
    box-sizing: border-box;
    align-items: flex-start;
}

/* Update textarea container for consistent width */
.textarea-with-autocomplete {
    position: relative;
    flex: 1;
    min-width: 0; /* Prevent flex item from overflowing */
    box-sizing: border-box;
}

/* Update textarea styles for proper sizing */
:deep(.p-inputtextarea) {
    width: 100% !important;
    box-sizing: border-box !important;
    resize: none;
    max-height: 120px;
    overflow-y: auto;
    line-height: 1.4;
    padding: 0.5rem 0.75rem;
    min-height: 2.8rem;
    margin: 0;
    border-radius: 6px;
}

/* Update dropdown styles for perfect alignment */
.autocomplete-dropdown {
    position: absolute;
    bottom: 100%;
    left: 0;
    width: 100%;
    background-color: white;
    border: 2px solid var(--primary-color);
    border-radius: 6px;
    box-shadow: 0 -2px 20px rgba(0, 0, 0, 0.25);
    max-height: 250px;
    overflow-y: auto;
    z-index: 9999;
    box-sizing: border-box;
    margin-bottom: 3px;
}

/* Ensure the send button doesn't affect textarea width */
.p-button-rounded {
    flex-shrink: 0;
}

/* Remove any conflicting margins or paddings */
.flex-grow-1 {
    margin: 0;
    padding: 0;
}

/* Ensure proper width inheritance */
:deep(.p-inputtextarea-resizable) {
    width: 100% !important;
}

:deep(.p-inputtextarea-wrapper) {
    width: 100% !important;
}

/* User question styling */
:deep(.user-question) {
    background-color: #f0f7ff;
    color: #1e3a8a;
    padding: 10px 15px;
    border-radius: 8px;
    margin: 5px 0;
    font-style: italic;
}

/* Error message styling */
:deep(.error-message) {
    background-color: #fff5f5;
    color: #e53e3e;
    padding: 10px 15px;
    border-radius: 8px;
    border-left: 4px solid #e53e3e;
    margin: 8px 0;
}

/* Ensure the chat interface scrolls properly */
.chat-interface-container {
    display: flex;
    flex-direction: column;
    flex: 1;
    overflow-y: auto;
    overflow-x: hidden;
    padding-bottom: 60px; /* Give space for the input area */
}

/* Style chat interface to fill space */
:deep(.chat-container) {
    display: flex;
    flex-direction: column;
    flex: 1;
    overflow-y: auto;
    overflow-x: hidden;
}

/* Add styles for debugging item indexes */
.item-index {
    display: none; /* Hide this completely since we're not using it anymore */
}

/* Add CSS style for focus highlight */
.button-focus-highlight {
    animation: button-pulse 1s ease-in-out 2;
}

@keyframes button-pulse {
    0% {
        box-shadow: 0 0 0 0 rgba(var(--primary-500), 0.7);
    }
    50% {
        box-shadow: 0 0 10px 0 rgba(var(--primary-500), 0.9);
    }
    100% {
        box-shadow: 0 0 0 0 rgba(var(--primary-500), 0);
    }
}

/* Enhance button focus styles */
button:focus-visible, 
button:focus {
    outline: 3px solid var(--primary-color) !important;
    outline-offset: 3px !important;
    box-shadow: 0 0 10px rgba(var(--primary-color-rgb), 0.7) !important;
}

.button-has-focus {
    outline: 3px solid var(--primary-color) !important;
    outline-offset: 3px !important;
    box-shadow: 0 0 15px rgba(var(--primary-color-rgb), 0.9) !important;
    transform: scale(1.05);
    transition: transform 0.2s ease, box-shadow 0.2s ease;
}

/* Add a keyframe animation for the focus overlay */
@keyframes pulse-focus {
    0% { 
        opacity: 0.9;
        box-shadow: 0 0 0 5000px rgba(0, 0, 0, 0.3);
    }
    50% { 
        opacity: 1;
        box-shadow: 0 0 0 5000px rgba(0, 0, 0, 0.5);
        border-color: var(--primary-800);
        border-width: 5px;
    }
    100% { 
        opacity: 0.9;
        box-shadow: 0 0 0 5000px rgba(0, 0, 0, 0.3);
    }
}

/* Settings dialog styles */
.cursor-pointer {
    cursor: pointer;
}

.environment-option {
    border: 2px solid var(--surface-border);
    transition: all 0.2s ease;
}

.environment-option:hover {
    background-color: var(--surface-50);
    border-color: var(--primary-300);
}

.environment-option:has(input:checked) {
    background-color: var(--primary-50);
    border-color: var(--primary-500);
}

.gap-3 {
    gap: 0.75rem;
}
</style>