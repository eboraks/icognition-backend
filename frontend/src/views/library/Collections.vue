<script lang="ts">
    import GridSelection from '@/components/GridSelection.vue';
    import { DataTableExpandedRows } from 'primevue';
    export default {
        name: 'Collections',
        components: {
            'GridSelection': GridSelection
        }
    }
</script>

<script setup lang="ts">
    import { useDocumentStore } from '@/stores/documents_store';
    import { useStudyCollection } from '@/composables/useStudyCollection';
    import user_state from '@/composables/getUser';
    import { defineAsyncComponent, ref, onMounted, watch } from 'vue';
    import moment from 'moment';
    import { StudyCollection } from '@/components/models/StudyCollection';
    import { useDialog } from 'primevue/usedialog';
    import { useRouter } from 'vue-router';
    import { useToast } from 'primevue/usetoast';

    const documentStore = useDocumentStore();
    const { docs, answer, resp_type, errorLibrary, isPendingLibrary, getDocuments, getSubtopicsNodes, getEntitiesNames, deleteDocument, entities_names } = documentStore;

    const { studyCollections, studyCollection, errorStudyCollection, isPendingStudyCollection, getStudyCollections, getStudyCollection, 
        getRelatedEntities, postStudyCollection, postCollectionDocumentLink, postCollectionDocumentUnlink, 
        deleteStudyCollection, searchCollections } = useStudyCollection();
    const answer_loading = ref(false);
    const dialog = useDialog();
    let hasNoData = false;
    const items = ref<string[]>([]);
    const expandedRows = ref<any[] | DataTableExpandedRows | null | undefined>({});
    const newCollectionErrorMessages = ref<any[]>([]);
    const new_study_collection_name = ref('');
    const new_study_collection_description = ref('');
    const search_term = ref('');
    const selectedCollections = ref<StudyCollection[]>();
    let showAddANewStudyPointDialog = ref(false);
    let showExamplesOfObjectiveCriteriaDialog = ref(false);
    let showExampleStudyPointsDialog = ref(false);
    const showFooterSelect = ref(false);
    const showNewCollectionDialog = ref(false);
    const toast = useToast();

    onMounted(async() => {
        try {
            getEntitiesNames(user_state.user?.uid as string);
            getStudyCollections(user_state.user?.uid as string);
        } catch (err) {
            console.log("Error: ", err);
        }
    });

    watch(
        () => selectedCollections.value,
        () => {
            if (selectedCollections.value?.length as number > 0) {
                showFooterSelect.value = true;
            } else {
                showFooterSelect.value = false;
            }
        }
    )

    const autocompleteSearch = (e: any) => {
        console.log("Autocomplete Search: ", e.query);

        items.value = entities_names;
        console.log("query length ", e.query.length);
        if (e.query.length > 1) {
            items.value = [];
            
            const words = e.query.trim().split(/\s+/);
            const lastWord = words[words.length - 1];

            if (e.query.endsWith(' ')) {
                items.value = entities_names.filter(entname => !e.query.includes(entname.toLowerCase())).map((item) => {
                    return e.query + item;
                });
                
            } else {
                items.value = entities_names.filter((item: string) => {
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

    const handleShowNewCollectionDialogComponents = async () => {
        // Reset
        newCollectionErrorMessages.value = [];

        // Collection Name Error
        if (new_study_collection_name.value == '') {
            newCollectionErrorMessages.value.push({id: 1, content: 'Collection Name Missing.'});
        }

        // Descrition Error
        // if (new_study_collection_description.value == '') {
        //     newCollectionErrorMessages.value.push({id: 2, content: 'Description Missing.'});
        // }

        if (newCollectionErrorMessages.value.length == 0) {
            await postStudyCollection(new StudyCollection(new_study_collection_name.value, new_study_collection_description.value, user_state.user?.uid as string));
            clearNewCollectionDialog();
        }
    }

    function clearNewCollectionDialog() {
        showNewCollectionDialog.value = false;
        new_study_collection_name.value = '';
        new_study_collection_description.value = '';
    }

    const emptied = () => {
        console.log("Emptied");
        search_term.value = '';
        searchHandle();
    }

    const handleCancelNewCollectionDialog = async () => {
        clearNewCollectionDialog();
        showNewCollectionDialog.value = false;
    }

    const handleNewCollectionDialog = async () => {
        showNewCollectionDialog.value = !showNewCollectionDialog.value;
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

    const onRowCollapse = (event: Event | any) => {
        toast.add({ severity: 'success', summary: 'Product Collapsed', detail: event.data.title, life: 3000 });
    };

    const onRowExpand = (event: Event | any) => {
        toast.add({ severity: 'info', summary: 'Product Expanded', detail: event.data.title, life: 3000 });
    };

    const searchHandle = async () => {
        studyCollections.value = null
        answer_loading.value = true;
        await searchCollections(user_state.user?.uid as string, search_term.value);
        answer_loading.value = false; 
        console.log("Search handle, answer: ", answer)   
    }

    const unselectItems = async () => {
        selectedCollections.value = [];
    }

</script>

<template>
    <div id="body-library" class="grid nested-grid grid-nogutter col-12 surface-100" style="height: calc(100% - 72px - 84px);">
        <div class="col-12 bg-white border-round border-300 border-2 p-0 h-full">
            <div class="col-12 grid grid-nogutter p-0" style="height: calc(100% - 51px);">
                <div class="flex flex-row w-full py-2">
                    <div class="col-6 mt-1">
                        <IconField>
                            <InputIcon>
                                <i class="pi pi-search"></i>
                            </InputIcon>
                            <AutoComplete class="surface-50 border-round-lg w-full" inputId="ac" v-model="search_term" :suggestions="items" 
                                @complete="autocompleteSearch" @keydown.enter="searchHandle"  
                                @input="inputHandle" @keydown.escape="emptied" placeholder="Search"/> 
                        </IconField>
                    </div>
                    <div class="col-6 flex align-content-center flex-wrap justify-content-end pr-0">
                        <a class="pr-3 py-1 font-semibold" @click="onExpandAll" style="height: 2rem;" tabindex="0">
                            <i class="pi pi-plus text-black-alpha-90 text-xs"></i> Expand All
                        </a>
                        <a @click="onCollapseAll" class="py-1 mr-3 font-semibold" style="height: 2rem;" tabindex="0">
                            <i class="pi pi-minus text-black-alpha-90 text-xs"></i> Collapse All
                        </a>
                        <Button type="button" icon="pi pi-plus" label="New Collection" aria-label="New Collection" class="p-2 mr-2 bg-primary-500" @click="handleNewCollectionDialog" />
                    </div>
                </div>
                <div class="col-12 px-2" style="height: calc(100% - 61px);">
                    <div class="card h-full" v-if="!hasNoData">
                        <DataTable v-model:expandedRows="expandedRows" v-model:selection="selectedCollections" :value="studyCollections" dataKey="id"
                                @rowExpand="onRowExpand" @rowCollapse="onRowCollapse" tableStyle="min-width: 1rem" class="h-full relative text-xs overflow-y-auto">
                            <Column expander style="width: 2rem" />
                            <Column field="name" header="Title" class="set-background-image">
                                <template #body="slotProps">
                                    <p class="inline-block">
                                        <router-link 
                                            :to="{
                                                name: 'collectiondetails',
                                                params: {id: slotProps.data.id}
                                            }"
                                            class="mt-2 text-700 py-1 ml-2">{{ slotProps.data.name }}
                                        </router-link>
                                    </p>
                                </template>
                            </Column>
                            <Column field="Created" header="Created">
                                <template #body="slotProps">
                                    {{ moment(slotProps.data.created_at).format('DD MMM YYYY h:mm a') }}
                                </template>
                            </Column>
                            <Column field="related_docs" header="# Documents">
                                <template #body="slotProps">
                                    {{ slotProps.data.related_docs.length }}
                                </template>
                            </Column>
                            <Column selectionMode="multiple" headerStyle="width: 3rem"></Column>

                            <template #expansion="slotProps">
                                <div class="p-2">
                                    <h5>{{ slotProps.data.objective }}</h5>
                                </div>
                            </template>
                        </DataTable>
                    </div>
                    <div class="card" v-if="hasNoData">
                        <div class="col-12 pt-7 mt-7">
                            <img class="flex m-auto" alt="bookmark" style="max-width: 100px;" src="/src/assets/images/icons/bookmark.png" />
                        </div>
                        <div class="col-12">
                            <p class="flex text-center m-auto" style="max-width: 60%;" src="/src/assets/images/icons/bookmark.png">
                                You don't have any bookmark topics created yet, because you haven't bookmarked any pages.
                            </p>
                        </div>
                    </div>
                </div>
            </div>
            <GridSelection v-if="showFooterSelect" :add-to-collection="[]" :selectedItems="selectedCollections" :method="deleteStudyCollection" :origin="'collections'" @unselectItems="unselectItems" />
        </div>
    </div>
    <Dialog v-model:visible="showNewCollectionDialog" modal header="New Collection" :style="{ width: '40%' }">
        <template #header>
            <div class="inline-flex gap-2">
                <h2>New Collection</h2>
            </div>
        </template>
        <div class="grid grid-nested">
            <div class="col-12 px-3">
                <div class="grid flex flex-row"  v-if="newCollectionErrorMessages.length != 0">
                    <Message v-for="msg of newCollectionErrorMessages" severity="error" class="mr-2">{{ msg.content }}</Message>
                </div>
                <div class="grid">
                    <div class="col-12 pr-3">
                        <div class="flex flex-column mb-2">
                            <label for="collectionname" class="pl-2 text-600 text-sm w-full">Collection Name *</label>
                            <InputText v-model.trim.lazy="new_study_collection_name" class="flex-auto" autocomplete="off" />
                        </div>
                        <div class="flex flex-column mb-1 mt-3">
                            <label for="collectiondescription" class="pl-2 text-600 text-sm w-full">Description</label>
                            <Textarea v-model.trim.lazy="new_study_collection_description" rows="5" cols="30" placeholder="Ex: &quot;I am looking to examine contributory factors to muscle retention in a group of elderly people..&quot;" />
                        </div>
                    </div>
                </div>
                <div class="grid grid-nogutter flex justify-content-end gap-2">
                    <Button type="button" label="Cancel" class="text-black-alpha-90 surface-300 border-300 border-400" severity="secondary" @click="handleCancelNewCollectionDialog"></Button>
                    <Button type="button" label="Submit" class="bg-green-800" @click="handleShowNewCollectionDialogComponents"></Button>
                </div>
            </div>
        </div>
    </Dialog>
    <Dialog v-model:visible="showExamplesOfObjectiveCriteriaDialog" modal header="Examples of Objective Criteria" :style="{ width: '60%' }">
        <template #header>
            <div class="inline-flex gap-2">
                <span class="font-semibold text-2xl">Examples of Objective Criteria</span>
            </div>
        </template>
        <div class="grid grid-nested">
            <div class="col-12 px-4">
                <div class="grid flex justify-content-end">
                    <div class="col-6 px-3">
                        <h2 class="font-semibold text-xl">Why should I care?</h2>
                        <p>
                            Providing this criteria gives iCorgnition's AI engine a way to scan your collection documents and identify how
                            their content supports the questions you are going to use it for. If you were gathering sources for a 
                            researchpaper on the feeding habits of Whales, for example, iCognition will assign a Relevancy score to
                            each document linked to you collection indicating how helpful each document would be in providing you with
                            Whale feeding habits.
                        </p>
                        <p>
                            You can also provide specific questions that you are looking to answer with the material in your sources to
                            improve the accuracy of that Relevancy number.
                        </p>
                    </div>
                    <div class="col-6 px-3">
                        <h2 class="font-semibold text-xl">Objective Criteria Examples</h2>
                        <p class="font-italic">
                            "To author a dissertation on how the Fourth Industrial Revolution has impacted education and learning,
                            with specific focus on the following points.
                        </p>
                        <p class="font-italic">
                            1. At vero eos et accusamus et iusto odio dignissimos ducimus qui blanditiis praesentium voluptatum
                            deleniti atque corrupti quos dolores et quas molestias excepturi sint occaecati cupiditate non provident
                        </p>
                        <p class="font-italic">
                            2. At vero eos et accusamus et iusto odio dignissimos ducimus qui blanditiis praesentium voluptatum
                            deleniti atque corrupti quos dolores et quas molestias excepturi sint occaecati cupiditate non provident”
                        </p>
                        <p class="font-italic pt-2">
                            “To identify the best prep, time, temperature and grill setup with which to roast a 4lb rack of baby back
                            ribs.”
                        </p>
                    </div>
                </div>
                <div class="grid grid-nogutter flex justify-content-end gap-2">
                    <Button type="button" label="Ok" class="bg-blue-500 mt-3 flex justify-content-end" @click="showExamplesOfObjectiveCriteriaDialog = false"></Button>
                </div>
            </div>
        </div>
    </Dialog>
    <Dialog v-model:visible="showExampleStudyPointsDialog" modal header="Example Study Points" :style="{ width: '60%' }">
        <template #header>
            <div class="inline-flex gap-2">
                <span class="font-semibold text-2xl">Example Study Points</span>
            </div>
        </template>
        <div class="grid grid-nested">
            <div class="col-12 px-4">
                <div class="grid flex justify-content-end">
                    <div class="col-12">
                        <p>
                            What were the conditions that led up to the French Revolution?
                        </p>
                        <p>
                            What is the windspeed velocity of an unladen swallow?
                        </p>
                    </div>
                </div>
                <div class="grid grid-nogutter flex justify-content-end gap-2">
                    <Button type="button" label="Close" class="bg-blue-500 mt-3 flex justify-content-end" @click="showExampleStudyPointsDialog = false"></Button>
                </div>
            </div>
        </div>
    </Dialog>
</template>