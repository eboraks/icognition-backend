<script lang="ts">
    import GridSelection from '@/components/GridSelection.vue';
    export default {
        name: 'AddSources',
        components: {
            'GridSelection': GridSelection
        }
    }
</script>

<script setup lang="ts">
    import { inject, onMounted, ref, watch } from 'vue';
    import { marked } from 'marked';
    import { DataTableExpandedRows, ProgressSpinner } from 'primevue';
    import moment from 'moment';
    import { StudyCollection } from '@/components/models/StudyCollection';
    import user_state from '@/composables/getUser';
    import { useDocumentStore } from '@/stores/documents_store';
    import { useStudyCollection } from '@/composables/useStudyCollection';
    import { useToast } from 'primevue/usetoast';

    const documentStore = useDocumentStore();
    const { docs, answer, resp_type, errorLibrary, isPendingLibrary, getDocuments, getSubtopicsNodes, getEntitiesNames, deleteDocument, entities_names } = documentStore;
    const { studyCollections, studyCollection, errorStudyCollection, isPendingStudyCollection, getStudyCollections, getStudyCollection, 
        getRelatedEntities, postStudyCollection, postCollectionDocumentLink, postCollectionDocumentUnlink, 
        deleteStudyCollection, candidateDocs, getCandidatesDocs, searchCollections, searchResult } = useStudyCollection();
    
    const answer_loading = ref(false);
    const dialogRef = inject("dialogRef") as any;
    const expandedRows = ref<any[] | DataTableExpandedRows | null | undefined>({});
    const fileupload = ref();
    const items = ref<string[]>([]);
    const search_term = ref('');
    const selectedDocuments = ref();
    const showFooterSelect = ref(false);
    const study_collection = ref<StudyCollection>();
    study_collection.value = dialogRef.value.options.data;
    const toast = useToast();
    const file_upload_url = ref(process.env.VITE_APP_API_BASE_URL + "/create_source_upload_file")

    onMounted(async() => {
        try {
        } catch (err) {
            console.log("Error: ", err);
        }
    });

    const closeStudyCollection = async () => {
        let onCloseData = ref<any[]>([]);
        if (selectedDocuments.value.length > 0) {
            selectedDocuments.value.forEach((selectedDocument: any) => {
                onCloseData.value.push(selectedDocument.id);
            });
        }
        dialogRef.value.close(onCloseData);
    }

    const emptied = () => {
        search_term.value = '';
        searchHandle();
    }

    function inputHandle(params: any) {
        if (search_term.value === '') {
            emptied();
        }
    }

    const onCollapseAll = () => {
        expandedRows.value = null;
    };

    const onExpandAll = () => {
        expandedRows.value = studyCollections.value.reduce((acc: any, p: any) => (acc[p.id] = true) && acc, {});
    };

    const onRowCollapse = (event: any) => {
        toast.add({ severity: 'success', summary: 'Documents Collapsed', detail: event.data.title, life: 3000 });
    };

    const onRowExpand = (event: any) => {
        toast.add({ severity: 'info', summary: 'Documents Expanded', detail: event.data.title, life: 3000 });
    };

    const onUpload = async (e: any) => {
        console.log(e);
        // files.value = event.files;
        // files.value.forEach((file) => {
        //     totalSize.value += parseInt(formatSize(file.size));
        // });
        console.log('fileupload ', fileupload.value);
    };

    const searchHandle = async () => {
        studyCollections.value = null
        answer_loading.value = true;
        await searchCollections(user_state.user?.uid as string, search_term.value);
        answer_loading.value = false; 
        console.log("Search handle, answer: ", searchResult.value)   
    }

    const unselectDocuments = async () => {
        selectedDocuments.value = [];
    }

    watch(
        () => selectedDocuments.value,
        () => {
            if (selectedDocuments.value.length > 0) {
                showFooterSelect.value = true;
            } else {
                showFooterSelect.value = false;
            }
        }
    )

    const renderMarkdown = (content?: string) => {
        if (!content) return '';
        const renderer = new marked.Renderer();
        renderer.link = ({ href, title, text }) => `<a href="${href}" target="_blank" rel="noopener noreferrer" class="text-primary hover:underline" title="${title || ''}">${text}</a>`;
        marked.setOptions({ renderer });
        return marked.parse(content);
    };

</script>

<template>
    <div class="grid grid-nested grid-nogutter">
        <div class="col-12 px-2">
            <div class="card h-full">
                <Tabs value="0" class="h-full">
                    <TabList class="border-bottom-1 border-200">
                        <Tab value="0">From Library</Tab>
                        <!-- <Tab value="1">Upload New</Tab> -->
                    </TabList>
                    <TabPanels>
                        <TabPanel value="0">
                            <div class="card border-1 border-300">
                                <div class="col-12 py-0 bg-white border-bottom-1 border-300">
                                    <div class="col-5 inline-flex mt-1">
                                        <IconField>
                                            <InputIcon>
                                                <i class="pi pi-search"></i>
                                            </InputIcon>
                                            <AutoComplete class="surface-50 border-round-lg w-full" inputId="ac" v-model="search_term" :suggestions="items" 
                                                @keydown.enter="searchHandle" @input="inputHandle" @keydown.escape="emptied" placeholder="Search"/> 
                                        </IconField>
                                    </div>
                                    <div class="col-7 inline-flex align-content-center flex-wrap justify-content-end pr-0">
                                        <a class="pr-3 py-1 font-semibold" @click="onExpandAll" style="height: 2rem;" tabindex="0">
                                            <i class="pi pi-plus text-black-alpha-90 text-xs"></i> Expand All
                                        </a>
                                        <a @click="onCollapseAll" class="py-1 mr-3 font-semibold" style="height: 2rem;" tabindex="0">
                                            <i class="pi pi-minus text-black-alpha-90 text-xs"></i> Collapse All
                                        </a>
                                    </div>
                                </div>
                                <div class="col-12 card">
                                    <DataTable v-model:expandedRows="expandedRows" v-model:selection="selectedDocuments" :value="docs" dataKey="id"
                                            @rowExpand="onRowExpand" @rowCollapse="onRowCollapse" scrollable tableStyle="min-width: 1rem" class="min-h-full h-full text-xs relative">
                                        <Column expander style="width: 2rem" />
                                        <Column field="title" header="Title" class="set-background-image">
                                            <template #body="slotProps">
                                                <div class="flex flex-row align-items-center">
                                                    <i v-if="slotProps.data.source_type == 'web'" class="pi pi-globe"></i>
                                                    <i v-if="slotProps.data.source_type == 'pdf'" class="pi pi-pdf"></i>
                                                    <router-link 
                                                        :to="{
                                                            name: 'docxray',
                                                            params: {id: slotProps.data.id}
                                                        }"
                                                        class="text-700 py-1 ml-2">{{slotProps.data.title}}
                                                    </router-link>
                                                </div>
                                            </template>
                                        </Column>
                                        <Column field="Last updated" header="Last updated" headerStyle="min-width: 12rem;" sortable >
                                            <template #body="slotProps">
                                                {{ moment(slotProps.data.updatedAt).format('DD MMM YYYY h:mm a') }}
                                            </template>
                                        </Column>
                                        <Column field="site_name" header="Source" sortable >
                                            <template #body="slotProps">
                                                <a v-bind:href="slotProps.data.url" target="_blank">{{ slotProps.data.site_name }}</a>
                                            </template>
                                        </Column>
                                        <Column selectionMode="multiple" headerStyle="width: 3rem"></Column>
                                        <template #expansion="slotProps">
                                            <div class="p-1 pl-5">
                                                <!-- <div class="col-12 pb-0">
                                                    <a class="mr-3" :href="slotProps.data.url" target="_blank"><i class="pi pi-pen-to-square"></i> OPEN ORIGINAL</a>
                                                    <a @click="showXRayDialog(slotProps.data)" tabindex="0">OPEN X-RAY</a>
                                                </div> -->
                                                <div class="grid">
                                                    <div class="col-fixed" style="width: 100px;">
                                                        <p>Summary:</p>    
                                                    </div>
                                                    <div class="col-12" style="max-width: 60%;">
                                                        <p>{{ slotProps.data.is_about}}</p>
                                                    </div>
                                                </div>
                                                <div class="grid">
                                                    <div class="col-fixed" style="width: 100px;">
                                                        <p>Key Points:</p>
                                                    </div>
                                                    <div class="col-11" style="max-width: 60%;">
                                                        <div v-if="slotProps.data.aiMarkdownContent" v-html="renderMarkdown(slotProps.data.aiMarkdownContent)"></div>
                                                        <div v-else>No key points available.</div>
                                                    </div>  
                                                </div>
                                            </div>
                                        </template>
                                    </DataTable>
                                </div>
                                <GridSelection v-if="showFooterSelect" :add-to-collection="[]" :selectedItems="selectedDocuments" :method="postCollectionDocumentLink" :origin="'addsources'" @unselectDocuments="unselectDocuments" />
                            </div>
                        </TabPanel>
                        <TabPanel value="1">
                            <div class="grid grid-nested">
                                <div class="col-12 px-4">
                                    <div class="grid flex justify-content-end">
                                        <div class="col-12">
                                            <FileUpload ref="fileupload" url="file_upload_url" @upload="onUpload($event)" :multiple="true" accept="application/pdf" :maxFileSize="100000000000">
                                                <template #empty>
                                                    <span>Drag and drop files to here to upload.</span>
                                                </template>
                                            </FileUpload>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </TabPanel>
                    </TabPanels>
                </Tabs>
            </div>
            <div class="grid grid-nogutter flex justify-content-end gap-2">
                <Button type="button" label="Cancel" class="text-black-alpha-90 my-2 surface-400 border-300 border-400" severity="secondary" @click="closeStudyCollection" />
                <Button type="button" label="Done" class="text-black-alpha-90 my-2 bg-primary text-white mr-3 border-300 border-400" :disabled="selectedDocuments?.length == 0" @click="closeStudyCollection" />
            </div>
        </div>
    </div>
</template>