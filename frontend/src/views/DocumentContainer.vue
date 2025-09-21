<template>
    <div id="body-library" class="grid nested-grid grid-nogutter col-12 surface-100" style="height: calc(100% - 4.5em - 5.25em);">
        <div class="col-12 bg-white border-round border-300 border-2 p-0 h-full">
            <Splitter class="grid nested-grid grid-nogutter h-full border-round border-noround-right">
                <SplitterPanel :class="{ 'splitter-panel-container-small': !buttonToggleSplitterPanelLeft }" class="col-12 p-2 border-round bg-primary-800 border-noround-right" :size="25" :minSize="1">
                    <div class="grid h-full">
                        <div class="col-6">
                            <Button v-if="!buttonToggleSplitterPanelLeft" class="bg-transparent border-transparent border-0 text-white ml-1" icon="pi pi-filter" @click="buttonToggleSplitterPanelLeft = !buttonToggleSplitterPanelLeft" rounded aria-label="Expand Panel"/>
                            <h4 v-if="buttonToggleSplitterPanelLeft" class="font-semibold pt-2 text-white">Filters</h4>
                        </div>
                        <div class="col-6 text-right">
                            <Button v-if="buttonToggleSplitterPanelLeft" class="bg-transparent border-transparent border-0 text-white" icon="pi pi-filter" @click="buttonToggleSplitterPanelLeft = !buttonToggleSplitterPanelLeft" rounded aria-label="Collapse Panel"/>
                        </div>
                        <div class="w-full" style="height: calc(100% - 3.75em);" v-if="buttonToggleSplitterPanelLeft">
                            <div v-if="documentStore.tree_nodes.length == 0 && documentStore.isPendingLibrary" class="flex flex-flow justify-content-center">
                                <i class="text-white pi pi-spin pi-spinner" style="font-size: 2rem"></i>
                            </div>                         
                            <div v-if="documentStore.tree_nodes.length == 0 && !documentStore.isPendingLibrary">
                                <div class="col-12 pt-7 mt-6">
                                    <img class="flex m-auto" alt="bookmark" style="max-width: 100px;" src="/src/assets/images/icons/bookmark.png" />
                                </div>
                                <div class="col-12">
                                    <p class="flex text-center m-auto text-white" style="max-width: 60%;">
                                        You don't have any bookmark filters created yet, because you haven't bookmarked any pages.
                                    </p>
                                </div>
                            </div>
                            <div class="w-full h-full" v-else>
                                <div class="w-full border-round-lg h-full">
                                    <SubtopicsTree />
                                </div>
                            </div>
                        </div>
                    </div>
                </SplitterPanel>
                <SplitterPanel :class="{ 'splitter-panel-container-big': !buttonToggleSplitterPanelLeft }" class="col-12 p-0" :size="75">
                    <div class="flex flex-row w-full" style="height: 3.3em;">
                        <div class="col-6 mt-1">
                            <IconField>
                                <InputIcon>
                                    <i class="pi pi-search" />
                                </InputIcon>
                                <AutoComplete class="surface-50 border-round-lg w-full" inputId="ac" v-model="search_term" :suggestions="items" 
                                    @complete="autocompleteSearch" @keydown.enter="searchHandle"  
                                    @input="inputHandle" @keydown.escape="emptied" placeholder="Search"/> 
                            </IconField>
                        </div>
                        <div class="col-6 flex align-content-between flex-wrap justify-content-end pr-0">
                            <a class="px-5 py-1 font-semibold" @click="onExpandAll" style="height: 2rem;" tabindex="0">
                                <i class="pi pi-plus text-black-alpha-90 text-xs"></i> Expand All
                            </a>
                        <a @click="onCollapseAll" class="px-5 py-1 mr-3 font-semibold" style="height: 2rem;" tabindex="0">
                            <i class="pi pi-minus text-black-alpha-90 text-xs"></i> Collapse All
                        </a>
                            <Button type="button" label="Upload PDF" aria-label="Upload PDF" class="p-2 mr-2 bg-primary-500" @click="showUploadFileDialog = !showUploadFileDialog" />
                        </div>
                    </div>
                    <!-- Div that will display RAG answer if resp_type === RAGAnswer -->
                    <div v-if="documentStore.resp_type === 'RAGAnswer'" class="col-12 p-0">
                        <div class="col-12 p-0">
                            <div class="col-8 p-4">{{ documentStore.answer }}</div>
                        </div>
                    </div>
                    <div class="card" style="height: calc(100% - 3.3em);">
                        <Library ref="docsTable" :documents="documentStore.getDocuments"/>
                    </div>
                </SplitterPanel>
            </Splitter>
        </div>
    </div>

    <FileUploadDialog v-if="showUploadFileDialog"></FileUploadDialog>

</template>

<script lang="ts">
    import Library from '@/views/library/Documents.vue';
    export default {
        name: 'DocumentContainer',
        components: {
            'Library': Library
        }
    }
</script>

<script lang="ts" setup>
    import SubtopicsTree from '@/components/SubtopicsTree.vue';
    
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
        docsTable.value.onExpandAll(); 
    }
    const onCollapseAll = () => {
        docsTable.value.onCollapseAll();
    }

    const documentStore = useDocumentStore();
    const uploadUrl = ref('http://localhost:8889/create_source_upload_file/');
    

    onMounted(async () => {
        try {
            if (router.currentRoute.value.name == Route_Location.COLLECTIONS) {
                currentTab.value = '1';
            }
            
            //await getDocuments(user_state.user?.uid as string);
            await documentStore.fetchDocuments(user_state.user?.uid as string);
            console.log("Documents from document store: ", documentStore.getDocuments);
            //await getSubtopics(user_state.user.uid);
            await documentStore.getSubtopicsNodes(user_state.user?.uid as string);
            //await getEntitiesNames(user_state.user.uid);
            //console.log("Subtopics: ", subtopics.value);
            console.log("Subtopics Nodes: ", documentStore.tree_nodes.length);
            //console.log("Entities Names: ", entities_names.value);
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
    }


    const emptied = () => {
        console.log("Emptied");
        search_term.value = '';
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