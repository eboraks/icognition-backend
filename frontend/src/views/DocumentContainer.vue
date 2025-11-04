<template>
    <div id="body-library" class="grid nested-grid grid-nogutter col-12 surface-100" style="height: calc(100% - 4.5em - 5.25em);">
        <div class="col-12 bg-white border-round border-300 border-2 p-0 h-full">
            <Splitter class="h-full border-round border-noround-right">
                <SplitterPanel :class="{ 'splitter-panel-container-small': !buttonToggleSplitterPanelLeft }" class="p-2 border-round bg-primary-500 border-noround-right" :size="25" :minSize="1">
                    <div class="grid h-full">
                        <div class="col-6">
                            <Button v-if="!buttonToggleSplitterPanelLeft" class="bg-transparent border-transparent border-0 text-white ml-1" icon="pi pi-filter" @click="buttonToggleSplitterPanelLeft = !buttonToggleSplitterPanelLeft" rounded aria-label="Expand Panel"/>
                            <h4 v-if="buttonToggleSplitterPanelLeft" class="font-semibold pt-2 text-white">Filter by Topic</h4>
                        </div>
                        <div class="col-6 text-right">
                            <Button v-if="buttonToggleSplitterPanelLeft" class="bg-transparent border-transparent border-0 text-white" icon="pi pi-filter" @click="buttonToggleSplitterPanelLeft = !buttonToggleSplitterPanelLeft" rounded aria-label="Collapse Panel"/>
                        </div>
                        <div class="w-full" style="height: calc(100% - 3.75em);" v-if="buttonToggleSplitterPanelLeft">
                            <div v-if="libraryStore.loading" class="flex flex-flow justify-content-center">
                                <i class="text-white pi pi-spin pi-spinner" style="font-size: 2rem"></i>
                            </div>                         
                            <div class="w-full h-full" v-else>
                                <div class="w-full border-round-lg h-full">
                                    <LibraryFilters :nodes="libraryStore.entityTree" @update:filters="onCheckedIds" />
                                </div>
                            </div>
                        </div>
                    </div>
                </SplitterPanel>
                <SplitterPanel :class="{ 'splitter-panel-container-big': !buttonToggleSplitterPanelLeft }" class="p-0 bg-white flex flex-column" :size="75">
                    <div class="flex flex-row w-full p-3 bg-white" style="flex-shrink: 0;">
                        <LibraryToolbar class="w-full" @search="onToolbarSearch" @expandAll="onExpandAll" @collapseAll="onCollapseAll" @upload="onUpload" />
                    </div>
                    <!-- Div that will display RAG answer if resp_type === RAGAnswer -->
                    <div v-if="documentStore.resp_type === 'RAGAnswer'" class="col-12 p-0 bg-white">
                        <div class="col-12 p-0">
                            <div class="col-8 p-4">{{ documentStore.answer }}</div>
                        </div>
                    </div>
                    <div class="bg-white" style="flex-grow: 1; overflow: auto;">
                        <LibraryTable ref="docsTable" :documents="libraryStore.filteredDocuments" :loading="libraryStore.loading"/>
                    </div>
                </SplitterPanel>
            </Splitter>
        </div>
    </div>

    <FileUploadDialog v-if="showUploadFileDialog"></FileUploadDialog>

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
    import LibraryFilters from '@/components/library/LibraryFilters.vue';
    import LibraryToolbar from '@/components/library/LibraryToolbar.vue';
    import { useLibraryStore } from '@/stores/library_store';
    import Splitter from 'primevue/splitter';
    import SplitterPanel from 'primevue/splitterpanel';
    import Button from 'primevue/button';
    
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
    const buttonToggleSplitterPanelLeft = ref(true);
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


    const onCheckedIds = (checkedIds: any) => {
        fitlerCheckedIds.value = checkedIds;
        libraryStore.updateSelectedEntities(checkedIds);
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