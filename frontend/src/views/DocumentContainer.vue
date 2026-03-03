<template>
    <div class="document-container-view">
        <div class="toolbar-section">
            <LibraryToolbar class="w-full" @search="onToolbarSearch" @expandAll="onExpandAll" @collapseAll="onCollapseAll" @upload="onUpload" />
        </div>
        <!-- Div that will display RAG answer if resp_type === RAGAnswer -->
        <div v-if="documentStore.resp_type === 'RAGAnswer'" class="rag-answer-section">
            <div class="rag-answer-content">{{ documentStore.answer }}</div>
        </div>

        <!-- Main Splitter: Filters | Table -->
        <Splitter class="main-splitter">
            <!-- Filter Sidebar Panel -->
            <SplitterPanel :size="20" :minSize="0" class="filter-panel">
                <div class="filter-section">
                    <LibrarySidebar />
                </div>
            </SplitterPanel>

            <!-- Table Panel -->
            <SplitterPanel :size="80" :minSize="40" class="splitter-panel">
                <div class="table-section">
                    <LibraryTable
                        ref="docsTable"
                        :documents="libraryStore.filteredDocuments"
                        :loading="libraryStore.loading"
                        @refresh="refreshDocuments"
                    />
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
    import LibrarySidebar from '@/components/library/LibrarySidebar.vue';
    import { useLibraryStore } from '@/stores/library_store';
    import Splitter from 'primevue/splitter';
    import SplitterPanel from 'primevue/splitterpanel';

    import user_state from '@/composables/getUser';
    import { handleFileUpload } from '@/composables/handleFileUpload';
    import { ref, onMounted } from 'vue';
    import { useRouter  } from 'vue-router';
    import { Route_Location } from '@/components/models/RouteLocation';
    import { useDocumentStore } from '@/stores/documents_store';
    import FileUploadDialog from '@/components/FileUploadDialog.vue';

    const answer_loading = ref(false);
    const search_term = ref('');
    const currentTab = ref('0');
    let isError = false;
    const router  = useRouter();
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
    };

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

    // Handle refresh after document delete/reprocess
    const refreshDocuments = async () => {
        try {
            await documentStore.fetchDocuments(user_state.user?.uid as string);
            await libraryStore.fetchDocuments();
            await libraryStore.fetchEntityTree();
        } catch (error) {
            console.error('Error refreshing documents:', error);
        }
    };

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

.main-splitter {
    flex: 1;
    min-height: 0;
    overflow: hidden;
}

:deep(.main-splitter .p-splitter) {
    height: 100%;
    border: none;
}

:deep(.main-splitter .p-splitter-panel) {
    display: flex;
    flex-direction: column;
    min-height: 0;
    overflow: hidden;
}

.filter-panel {
    display: flex;
    flex-direction: column;
    min-height: 0;
}

.filter-section {
    flex: 1;
    min-height: 0;
    overflow: hidden;
    background: var(--p-surface-0);
    border-right: 1px solid var(--p-content-border-color);
    padding: 1rem;
    display: flex;
    flex-direction: column;
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
</style>
