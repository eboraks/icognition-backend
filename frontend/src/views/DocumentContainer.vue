<template>
    <div class="document-container-view">
        <div class="toolbar-section">
            <LibraryToolbar class="w-full" @search="onToolbarSearch" @expandAll="onExpandAll" @collapseAll="onCollapseAll" @upload="onUpload" />
        </div>
        <!-- Div that will display RAG answer if resp_type === RAGAnswer -->
        <div v-if="documentStore.resp_type === 'RAGAnswer'" class="rag-answer-section">
            <div class="rag-answer-content">{{ documentStore.answer }}</div>
        </div>
        <div class="table-section">
            <LibraryTable ref="docsTable" :documents="libraryStore.filteredDocuments" :loading="libraryStore.loading"/>
        </div>
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
    import { useLibraryStore } from '@/stores/library_store';
    
    import user_state from '@/composables/getUser';
    import { handleFileUpload } from '@/composables/handleFileUpload';
    import { computed, ref, onMounted } from 'vue';
    import { useRouter  } from 'vue-router';
    import { Route_Location } from '@/components/models/RouteLocation';
    import { useDocumentStore } from '@/stores/documents_store';
    import FileUploadDialog from '@/components/FileUploadDialog.vue';
    
    const answer_loading = ref(false);
    const search_term = ref('');
    const currentTab = ref('0');
    let isError = false;
    const router  = useRouter();
    const fitlerCheckedIds = ref(new Map());
    const items = ref<any[]>([]);
    let showUploadFileDialog = ref(false);
    
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
    }

    const documentStore = useDocumentStore();
    const libraryStore = useLibraryStore();
    const uploadUrl = ref('http://localhost:8889/create_source_upload_file/');
    

    onMounted(async () => {
        try {
            if (router.currentRoute.value.name == Route_Location.COLLECTIONS) {
                currentTab.value = '1';
            }
            
            // Fetch documents and entity tree
            await documentStore.fetchDocuments(user_state.user?.uid as string);
            await libraryStore.fetchDocuments();
            await libraryStore.fetchEntityTree();
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

.table-section {
    flex: 1;
    min-height: 0;
    overflow: auto;
    background: var(--p-surface-0);
}
</style>