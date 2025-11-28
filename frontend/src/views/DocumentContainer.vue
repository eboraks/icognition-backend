<template>
    <div class="document-container-view">
        <div class="toolbar-section">
            <LibraryToolbar class="w-full" @search="onToolbarSearch" @expandAll="onExpandAll" @collapseAll="onCollapseAll" @upload="onUpload" />
        </div>
        <!-- Div that will display RAG answer if resp_type === RAGAnswer -->
        <div v-if="documentStore.resp_type === 'RAGAnswer'" class="rag-answer-section">
            <div class="rag-answer-content">{{ documentStore.answer }}</div>
        </div>
        
        <!-- Splitter to divide documents and chat -->
        <Splitter class="content-splitter">
            <SplitterPanel :size="60" :minSize="30" class="splitter-panel">
                <div class="table-section">
                    <LibraryTable ref="docsTable" :documents="libraryStore.filteredDocuments" :loading="libraryStore.loading"/>
                </div>
            </SplitterPanel>
            <SplitterPanel :size="40" :minSize="20" class="splitter-panel">
                <div class="chat-section">
                    <Tabs :value="activeChatTabId" @update:model-value="setActiveChatTab" class="full-height-tabs">
                        <div class="tab-header-container">
                            <TabList>
                                <Tab v-for="tab in chatTabs" :key="tab.id" :value="tab.id">
                                    <i class="pi pi-comments" />
                                    <span>{{ tab.title }}</span>
                                </Tab>
                            </TabList>
                            <button class="tab-add-button" type="button" @click="addChatTab()">
                                <i class="pi pi-plus" />
                            </button>
                        </div>
                        <div class="tab-panels-container">
                            <TabPanels>
                                <TabPanel v-for="tab in chatTabs" :key="tab.id" :value="tab.id">
                                    <ChatPanel
                                        :selected-entity-id="selectedEntityId"
                                        :selected-document-id="selectedDocumentId"
                                        :chat-session-id="Number(tab.sessionId)"
                                    />
                                </TabPanel>
                            </TabPanels>
                        </div>
                    </Tabs>
                </div>
            </SplitterPanel>
        </Splitter>
        
        <FileUploadDialog v-if="showUploadFileDialog"></FileUploadDialog>
    </div>
</template>

<script lang="ts">
    import LibraryTable from '@/components/library/LibraryTable.vue';
    export default {
        name: 'DocumentContainer',
        components: {
            'LibraryTable': LibraryTable
        }
    }
</script>

<script lang="ts" setup>
    import LibraryToolbar from '@/components/library/LibraryToolbar.vue';
    import ChatPanel from '@/components/knowledge_explorer/ChatPanel.vue';
    import { useLibraryStore } from '@/stores/library_store';
    import Splitter from 'primevue/splitter';
    import SplitterPanel from 'primevue/splitterpanel';
    import Tabs from 'primevue/tabs';
    import TabList from 'primevue/tablist';
    import Tab from 'primevue/tab';
    import TabPanels from 'primevue/tabpanels';
    import TabPanel from 'primevue/tabpanel';
    
    import user_state from '@/composables/getUser';
    import { handleFileUpload } from '@/composables/handleFileUpload';
    import { computed, ref, onMounted } from 'vue';
    import { useRouter  } from 'vue-router';
    import { Route_Location } from '@/components/models/RouteLocation';
    import { useDocumentStore } from '@/stores/documents_store';
    import FileUploadDialog from '@/components/FileUploadDialog.vue';
    import { useChatStore } from '@/stores/chat_store';
    
    const answer_loading = ref(false);
    const search_term = ref('');
    const currentTab = ref('0');
    let isError = false;
    const router  = useRouter();
    const fitlerCheckedIds = ref(new Map());
    const items = ref<any[]>([]);
    let showUploadFileDialog = ref(false);

    interface ChatTab {
        id: number;
        title: string;
        createdAt: number;
        sessionId: number;
    }

    const chatTabs = ref<ChatTab[]>([
        {
            id: 1,
            title: 'Default Chat',
            createdAt: Date.now(),
            sessionId: 0,
        },
    ]);
    const activeChatTabId = ref<number>(1);
    const nextChatTabIndex = ref(2);
    
    const file = ref([]);    
    const files = ref<File[]>([]);
    const totalSize = ref(0);

    const docsTable = ref<any>(null);
    const onExpandAll = () => {
        if (docsTable.value?.expandedRows) {
            const newExpandedRows: { [key: string]: boolean } = {};
            libraryStore.documents.forEach(doc => {
                newExpandedRows[doc.id] = true;
            });
            docsTable.value.expandedRows = newExpandedRows;
        }
    }
    const onCollapseAll = () => {
        if (docsTable.value?.expandedRows) docsTable.value.expandedRows = {};
    };

    async function ensureActiveChatTab() {
        if (!chatTabs.value.length) {
            await addChatTab('New Chat');
            return;
        }

        let currentActiveTab = chatTabs.value.find((tab) => tab.id === activeChatTabId.value);
        if (!currentActiveTab) {
            // Fallback to the first tab if activeChatTabId somehow doesn't match any existing tab
            currentActiveTab = chatTabs.value[0];
            activeChatTabId.value = currentActiveTab?.id ?? 0; // Ensure activeChatTabId is set
        }

        // If the current active tab has a sessionId of 0, it means no backend session has been created for it yet
        if (currentActiveTab && currentActiveTab.sessionId === 0) {
            console.log(`Tab '${currentActiveTab.title}' has no active session, creating one.`);
            const newSession = await chatStore.createSession(
                currentActiveTab.title,
                'all_library',
                null
            );

            if (newSession) {
                currentActiveTab.sessionId = newSession.id;
            } else {
                console.error('Failed to create new chat session for tab:', currentActiveTab.title);
                // Optionally, handle this failure by displaying an error message or removing the tab
            }
        }

        // Ensure activeChatTabId is always set to a valid tab id, even if the session creation failed
        if (!chatTabs.value.some(tab => tab.id === activeChatTabId.value)) {
          activeChatTabId.value = chatTabs.value[chatTabs.value.length - 1]?.id ?? 0;
        }

    }

    async function addChatTab(title?: string) {
        const nextIndex = nextChatTabIndex.value++;
        const newSession = await chatStore.createSession(
            title || `Chat ${nextIndex}`,
            'all_library',
            null // scopeId
        );

        if (!newSession) {
            console.error('Failed to create new chat session.');
            return;
        }

        const newTab: ChatTab = {
            id: Date.now() + nextIndex,
            title: newSession.title,
            createdAt: Date.now(),
            sessionId: newSession.id,
        };
        chatTabs.value.push(newTab);
        activeChatTabId.value = newTab.id;
    }

    function setActiveChatTab(tabId: number) {
        if (chatTabs.value.some((tab) => tab.id === tabId)) {
            activeChatTabId.value = tabId;
        }
    }

    const documentStore = useDocumentStore();
    const libraryStore = useLibraryStore();
    const chatStore = useChatStore();
    const uploadUrl = ref('http://localhost:8889/create_source_upload_file/');
    
    // Computed properties for chat panel context
    const selectedEntityId = computed(() => {
        const entityIds = Array.from(libraryStore.selectedEntityIds);
        return entityIds.length > 0 ? entityIds[0] : null;
    });
    
    const selectedDocumentId = computed(() => {
        const docIds = libraryStore.selectedDocumentIds;
        return docIds.size > 0 ? Array.from(docIds)[0] : null;
    });

    onMounted(async () => {
        try {
            if (router.currentRoute.value.name == Route_Location.COLLECTIONS) {
                currentTab.value = '1';
            }
            
            // Fetch documents and entity tree
            await documentStore.fetchDocuments(user_state.user?.uid as string);
            await libraryStore.fetchDocuments();
            await libraryStore.fetchEntityTree();

            await ensureActiveChatTab();

            console.log("Documents from document store: ", documentStore.getDocuments);
            console.log("Entity tree nodes: ", libraryStore.entityTree.length);
            isError = false;
        } catch (err) {
            isError = true;
            console.log("Error: ", err);
        }
    });

    // Handle filter updates from sidebar (LibraryFilters component)
    const onCheckedIds = (checkedIds: any) => {
        fitlerCheckedIds.value = checkedIds;
        libraryStore.updateSelectedEntities(checkedIds);
    };
    
    // Expose the handler for the sidebar component to use
    defineExpose({ onCheckedIds });

    const socketSetup = async (user_id: string) => {
        const socket = new WebSocket('http://localhost:8889/ws/' + user_id);

        socket.onopen = () => {
            console.log("WebSocket connection open.");
            socket.send("Hello, WebSocket Server!");
        };

        socket.onmessage = async (event) => {
            console.log("Server says: ", event.data);
            if (event.data == "PULLDOCUMENTS") {
                console.log('get Documents');
                await documentStore.fetchDocuments(user_state.user?.uid as string);
            }
        };
        
        // Close the WebSocket connection when done
        socket.onclose = () => {
            console.log("WebSocket connection closed.");
        };
    }

    const emptied = () => {
        console.log("Emptied");
        search_term.value = '';
        searchHandle();
    }
    const onToolbarSearch = (q: string) => {
        search_term.value = q;
        libraryStore.setSearch(q);
        searchHandle();
    }
    const searchHandle = async () => {
        answer_loading.value = true;
        await documentStore.searchDocuments(user_state.user?.uid as string, search_term.value);
        answer_loading.value = false; 
        console.log("Search handle, answer: ", documentStore.resp_type)
        console.log('documents from searchHandle', documentStore.getDocuments);
        console.log('RAG Answer: ', documentStore.answerResponse);
    };
    const autocompleteSearch = (e: any) => {
        console.log("Autocomplete Search: ", e.query);

        items.value = documentStore.entities_names;
        console.log("query length ", e.query.length);
        if (e.query.length > 1) {
            items.value = [];
            
            const words = e.query.trim().split(/\s+/);
            const lastWord = words[words.length - 1];

            if (e.query.endsWith(' ')) {
                items.value = documentStore.entities_names.filter(entname => !e.query.includes(entname.toLowerCase())).map((item) => {
                    return e.query + item;
                });
                
            } else {
                items.value = documentStore.entities_names.filter((item) => {
                    return item.toLowerCase().startsWith(lastWord.toLowerCase());
                }).map((item) => {
                    words.pop();
                    return words.join(' ') + ' ' + item;
                });
                if (items.value.length == 0) {
                    return e.query;
                }
            }
            return e.query;
        }
    }
    function inputHandle(params: any) {
        if (search_term.value === '') {
            emptied();
        }
    };

const onUpload = (e: any) => {
    console.log('Upload Event: ', e);
    handleFileUpload(e, user_state.user?.uid as string);
};
</script>

<style scoped>
.document-container-view {
    display: flex;
    flex-direction: column;
    height: 100%;
    min-height: 0;
    background: var(--p-surface-ground);
}

.toolbar-section {
    flex-shrink: 0;
    padding: 1rem;
    background: var(--p-surface-0);
    border-bottom: 1px solid var(--p-content-border-color);
}

.rag-answer-section {
    flex-shrink: 0;
    padding: 1rem;
    background: var(--p-surface-0);
    border-bottom: 1px solid var(--p-content-border-color);
}

.rag-answer-content {
    max-width: 66.666%;
    padding: 1rem;
}

.content-splitter {
    flex: 1;
    min-height: 0;
    overflow: hidden;
}

:deep(.content-splitter .p-splitter) {
    height: 100%;
    border: none;
}

:deep(.content-splitter .p-splitter-panel) {
    display: flex;
    flex-direction: column;
    min-height: 0;
    overflow: hidden;
}

.splitter-panel {
    display: flex;
    flex-direction: column;
    min-height: 0;
    overflow: hidden;
}

.table-section {
    flex: 1;
    min-height: 0;
    overflow: auto;
    background: var(--p-surface-0);
}

.chat-section {
    flex: 1;
    min-height: 0;
    overflow: hidden;
    background: var(--p-surface-0);
    border-left: 1px solid var(--p-content-border-color);
    display: flex;
    flex-direction: column;
}

.full-height-tabs {
    display: flex;
    flex-direction: column;
    height: 100%;
}

:deep(.full-height-tabs .p-tabpanels) {
    flex: 1;
    min-height: 0;
}

.tab-header-container {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0.5rem 1rem;
    border-bottom: 1px solid var(--p-content-border-color);
    flex-shrink: 0;
}

:deep(.tab-header-container .p-tabs) {
    flex-grow: 1;
}

:deep(.tab-header-container .p-tablist) {
    border: none;
    padding: 0;
}

:deep(.tab-header-container .p-tablist .p-tab:not(.p-highlight)) {
    background: transparent;
    border: none;
}

:deep(.tab-header-container .p-tablist .p-tab.p-highlight) {
    background: var(--p-primary-50);
    border-color: var(--p-primary-200);
    color: var(--p-primary-700);
    box-shadow: inset 0 -2px 0 var(--p-primary-300);
}

:deep(.tab-header-container .p-tablist .p-tab-header) {
    margin-right: 0.5rem; /* Space between tabs */
}

:deep(.tab-header-container .p-tab-nav-container) {
    overflow-x: auto;
    scrollbar-width: none; /* Hide scrollbar for Firefox */
    -ms-overflow-style: none;  /* Hide scrollbar for IE and Edge */
}

:deep(.tab-header-container .p-tab-nav-container::-webkit-scrollbar) {
    display: none; /* Hide scrollbar for Chrome, Safari, and Opera */
}

:deep(.tab-header-container .p-tab-header-action) {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.5rem 1rem;
    border-radius: 0.75rem;
    font-weight: 600;
    color: var(--p-text-muted-color);
}

:deep(.tab-header-container .p-tab-header-action:hover) {
    background: var(--p-surface-200);
    color: var(--p-text-color);
}

.tab-add-button {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 2.25rem;
    height: 2.25rem;
    border-radius: 0.75rem;
    border: 1px dashed var(--p-content-border-color);
    background: var(--p-surface-0);
    color: var(--p-text-muted-color);
    transition: all 0.2s ease;
    cursor: pointer;
    flex-shrink: 0;
}

.tab-add-button:hover {
    border-color: var(--p-primary-400);
    color: var(--p-primary-500);
    background: var(--p-primary-50);
    box-shadow: 0 4px 12px rgba(45, 122, 138, 0.15);
}

.tab-panels-container {
    flex: 1;
    min-height: 0;
    overflow: hidden;
}

:deep(.tab-panels-container .p-tabpanels) {
    height: 100%;
    background: transparent;
    padding: 0;
}

:deep(.tab-panels-container .p-tabpanel) {
    height: 100%;
    padding: 0;
}
</style>