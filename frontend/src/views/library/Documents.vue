<script lang="ts">
    import GridSelection from '@/components/GridSelection.vue';
    export default {
        name: 'Library',
        components: {
            'GridSelection': GridSelection
        }
    }
</script>

<script setup lang="ts">
    import { useDocumentStore } from '@/stores/documents_store';
    import { useStudyCollection } from '@/composables/useStudyCollection';
    import user_state from '@/composables/getUser';
    import { formatUrlsAsLinks } from '@/composables/useUrlFormatter';
    import { ref, onMounted, watch } from 'vue';
    import { DataTableExpandedRows } from 'primevue';
    import FileUpload from 'primevue/fileupload';
    import moment from 'moment';
    import { useToast } from 'primevue/usetoast';

    const documentStore = useDocumentStore();
    const { docs, answer, resp_type, errorLibrary, isPendingLibrary, fetchDocuments, getSubtopicsNodes, getEntitiesNames, deleteDocument, tree_nodes, entities_names } = documentStore;
    const { studyCollections, studyCollection, errorStudyCollection, isPendingStudyCollection, getStudyCollections, getStudyCollection, 
        getRelatedEntities, postStudyCollection, postCollectionDocumentLink, postCollectionDocumentUnlink, 
        deleteStudyCollection, searchCollections } = useStudyCollection();
    const answer_loading = ref(false);
    const expandedRows = ref<DataTableExpandedRows | null>({});
    const fileupload = ref([]);
    const hasNoData = ref();
    let isError = false;
    const props = defineProps({
        documents: Array,
        collapseAll: Boolean,
        expandAll: Boolean
    });
    const search_term = ref('');
    const selectedDocuments = ref();
    const showFooterSelect = ref(false);
    let showUploadFileDialog = ref(false);
    const toast = useToast();

    onMounted(async() => {
        try {
            await fetchDocuments(user_state.user?.uid as string);
            await getSubtopicsNodes(user_state.user?.uid as string);
            await getEntitiesNames(user_state.user?.uid as string);
            await getStudyCollections(user_state.user?.uid as string);
            console.log("Documents from document store: ", docs);
            console.log("Subtopics Nodes: ", tree_nodes.length);
            console.log("Entities Names: ", entities_names.length);

            isError = false;
        } catch (err) {
            isError = true;
            console.log("Error: ", err);
        }
    });

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

    const collectionDocumentLink = async (collectionDocumentObject: any) => {
        // By assinging the value to the Ref cititation it will trigger the vnode to be updated
        if (collectionDocumentObject.documents.length > 0) {
            const documents_ids = collectionDocumentObject.documents.map((doc: any) => doc.id);
            await postCollectionDocumentLink(collectionDocumentObject.studyCollection.value.id, documents_ids);
        }
    }

    const filteredDocuments = ref();

    const hasData = async (documentsLength: number) => {
        if (documentsLength != null && documentsLength > 0) {
            hasNoData.value = false;
        }
    }

    const onCollapseAll = () => {
        expandedRows.value = null;
    };

    const onExpandAll = () => {
        expandedRows.value = props.documents?.reduce((acc: any, p: any) => (acc[p.id] = true) && acc, {}) as DataTableExpandedRows;
    };

    const onRowCollapse = (event: any) => {
        toast.add({ severity: 'success', summary: 'Documents Collapsed', detail: event.data.title, life: 3000 });
    };

    const onRowExpand = (event: any) => {
        toast.add({ severity: 'info', summary: 'Documents Expanded', detail: event.data.title, life: 3000 });
    };

    const searchHandle = async () => {
        answer_loading.value = true;
        await documentStore.searchDocuments(user_state.user?.uid as string, search_term.value);
        answer_loading.value = false; 
        console.log("Search handle, answer: ", resp_type)
        console.log('documents from searchHandle', docs);
        filteredDocuments.value = docs;
        console.log('props.documents', props.documents);
    };

    const onUpload = async (e: any) => {
        console.log(e);
        // files.value = event.files;
        // files.value.forEach((file) => {
        //     totalSize.value += parseInt(formatSize(file.size));
        // });
        console.log('fileupload ', fileupload.value);
    };

    const unselectItems = async () => {
        selectedDocuments.value = [];
    }

    defineExpose({
        onCollapseAll,
        onExpandAll
    });
</script>

<template>
    <div class="col-12 grid p-0 grid-nogutter h-full">
        <div class="col-12 pr-0" style="height: calc(100% - 3em);" v-if="props.documents?.length != 0" :class="{'collectionHeightLarge': showFooterSelect}">
            <div class="card h-full">
                <DataTable v-model:expandedRows="expandedRows" v-model:selection="selectedDocuments" :value="props.documents" dataKey="id"
                        @rowExpand="onRowExpand" @rowCollapse="onRowCollapse" scrollable tableStyle="min-width: 1rem" class="min-h-full h-full text-xs relative">
                    <Column expander style="width: 2rem" />
                    <Column field="title" header="Title" class="set-background-image">
                        <template #body="slotProps">
                            <div class="flex flex-row align-items-center">
                                <i v-if="slotProps.data.source_type == 'web'" class="pi pi-globe"></i>
                                <i v-if="slotProps.data.source_type == 'pdf'" class="pi pi-file-pdf"></i>
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
                    <Column field="Added to Library" header="Added to Library" headerStyle="min-width: 12rem;" sortable >
                        <template #body="slotProps">
                            {{ moment(slotProps.data.updated_at).format('YYYY-MM-DD') }}
                        </template>
                    </Column>
                    <Column field="site_name" header="Source" sortable >
                        <template #body="slotProps">
                            <a v-bind:href="slotProps.data.url" target="_blank">{{ slotProps.data.site_name }}</a>
                        </template>
                    </Column>
                    <Column selectionMode="multiple" headerStyle="width: 3rem"></Column>
                    <template #expansion="slotProps">
                        <div class="p-1">
                            <div class="grid">
                                <div class="col-12">
                                    <div class="text-xs px-3">
                                        <div class="mb-2">
                                            <span class="font-semibold text-xs">Summary:</span>
                                            <p class="m-0 p-2 text-xs line-height-2 font-mono" v-html="formatUrlsAsLinks(slotProps.data.ai_is_about || '')"></p>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </template>
                </DataTable>
                <div v-if="isPendingLibrary" class="flex flex-flow justify-content-center">
                    <i class="text-white pi pi-spin pi-spinner" style="font-size: 2rem"></i>
                </div>
            </div>
        </div>
        <div class="col-12 card" v-if="!isPendingLibrary && props.documents?.length == 0">
            <div class="col-12 pt-7 mt-7">
                <img class="flex m-auto" alt="bookmark" style="max-width: 100px;" src="/src/assets/images/icons/bookmark.png" />
            </div>
            <div class="col-12">
                <p class="block text-center m-auto" style="max-width: 60%;" src="/src/assets/images/icons/bookmark.png">
                    You don't have any bookmark topics created yet, because you haven't bookmarked any pages.
                </p>
            </div>
        </div>
        <GridSelection v-if="showFooterSelect" :add-to-collection="studyCollections" :selectedItems="selectedDocuments" :method="deleteDocument" :origin="'library'"
            @unselectItems="unselectItems" @collectionDocumentLink="collectionDocumentLink"/>
    </div>
</template>