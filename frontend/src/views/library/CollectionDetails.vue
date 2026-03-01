<script setup lang="ts">
    import moment from 'moment';
    import { useDocumentStore } from '@/stores/documents_store';
    import { useStudyCollection } from '@/composables/useStudyCollection';
    import user_state from '@/composables/getUser';
    import { defineAsyncComponent, ref, onMounted } from 'vue';
    import { marked } from 'marked';
    import { useDialog } from 'primevue/usedialog';
    import { useRouter } from 'vue-router';
    import { AskQuestionPayload } from '@/components/models/AskQuestion.ts';
    import { AskQuestionAnswerModel } from '@/components/models/AskQuestionAnswerModel';
    import { useCustomQandA } from '@/composables/useCustomQandA.ts';
    import { StudyCollection } from '@/components/models/StudyCollection';
    import DynamicDialog from 'primevue/dynamicdialog';
    import { DocModel } from '@/components/models/DocModel';
    import { DataTableExpandedRows } from 'primevue';
    import { useToast } from 'primevue/usetoast';

    const documentStore = useDocumentStore();
    const { docs, answer, resp_type, errorLibrary, isPendingLibrary, getDocuments, getSubtopicsNodes, getEntitiesNames, deleteDocument, entities_names } = documentStore;
    const { studyCollections, studyCollection, errorStudyCollection, isPendingStudyCollection, getStudyCollections, getStudyCollection, 
        getRelatedEntities, postStudyCollection, postCollectionDocumentLink, postCollectionDocumentUnlink, 
        deleteStudyCollection, candidateDocs, getCandidatesDocs, searchCollections, searchResult } = useStudyCollection();
    const { isAskPending, askQuestion, answerResponse } = useCustomQandA();
    
    const answer_loading = ref(false);
    const breadcrumb_home = ref({
        icon: 'pi pi-home',
        route: '/collections'
    });
    const breadcrumb_items = ref([
        { label: 'My Collections' }
    ]);
    const buttonToggleSplitterPanelRight = ref(true);
    const dialogAddSources = useDialog();
    const dialogOutlineBuilder = useDialog();
    const expandedRows = ref<any[] | DataTableExpandedRows | null | undefined>({});
    const items = ref<string[]>([]);
    const qas = ref();
    const question = ref('');
    const router = useRouter();
    const search_term = ref('');
    const selectedDocuments = ref();
    let tempAnswer: string = '';
    const toast = useToast();

    onMounted(async() => {
        try {
            await getCandidatesDocs(router.currentRoute.value.params.id as string);
            await getStudyCollection(router.currentRoute.value.params.id as string);
            console.log("Seleced Documents: ", selectedDocuments.value);
            tempAnswer = answer as string;
        } catch (err) {
            console.log("Error: ", err);
        }
    });

    const emptied = () => {
        console.log("Emptied");
        search_term.value = '';
        searchHandle();
    }

    const renderMarkdown = (content?: string) => {
        if (!content) return '';
        const renderer = new marked.Renderer();
        renderer.link = ({ href, title, text }) => `<a href="${href}" target="_blank" rel="noopener noreferrer" class="text-primary hover:underline" title="${title || ''}">${text}</a>`;
        marked.setOptions({ renderer });
        return marked.parse(content);
    };

    const handleApply = async () => {
        if (!selectedDocuments.value) {
            return;
        }

        selectedDocuments.value.forEach((selectedDocument: any) => {
            postCollectionDocumentLink(studyCollection.value.id as string, selectedDocument.id);
        });
    }

    const handleAsk = async () => {
        console.log("Asking question: ", question.value, " collection_id: ", studyCollection.value.id);
        if (!question.value) {
            tempAnswer = 'Please enter a question';
            return;
        }
        let askQuestionPayload = new AskQuestionPayload(question.value, null, studyCollection.value.id as string);
        await askQuestion(askQuestionPayload);
        if (isAskPending.value) {
            tempAnswer = 'Please wait for the answer';
        } else {
            tempAnswer = answerResponse.value?.answer as string;
        }
        console.log("Answer: ", tempAnswer);
        qas.value.push({question: question.value, answer: tempAnswer, created_at: moment()});
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

    const searchHandle = async () => {
        studyCollections.value = null;
        answer_loading.value = true;
        await searchCollections(user_state.user?.uid as string, search_term.value);
        answer_loading.value = false; 
        console.log("Search handle, answer: ", answer);
    }

    const showAddSourcesDialog = () => {
        dialogAddSources.open(AddSourcesView, {
            data: studyCollection.value,
            props: {
                header: 'Add Source Documents',
                contentClass: 'dialog-inner-scroll',
                style: {
                    height: 'auto',
                    width: '80%'
                },
                modal: true
            },
            onClose: (options) => {
                const selectedDocumentObjectArray = options?.data;
                if (selectedDocumentObjectArray.length > 0) {
                    selectedDocumentObjectArray.forEach((selectedDocumentId: any) => {
                        postCollectionDocumentLink(studyCollection.value.id as string, selectedDocumentId);
                    })
                }
            }
        });
    };

    const AddSourcesView = defineAsyncComponent(() => import('@/views/library/AddSources.vue'));

    const showOutlineBuilderDialog = () => {
        dialogOutlineBuilder.open(OutlineBuilderView, {
            data: studyCollection.value,
            props: {
                header: studyCollection.value.name as string,
                contentClass: 'dialog-inner-scroll',
                style: {
                    height: 'auto',
                    width: '80%'
                },
                modal: true
            },
            onClose: (options) => {
                const dataClose = options?.data;
            }
        });
    };

    const OutlineBuilderView = defineAsyncComponent(() => import('@/views/library/OutlineBuilder.vue'));

</script>

<template>
    <!-- The height is calculated based on the full page - header(55.2px) - footer(72px) for padding on top and bottom -->
    <div id="body-library" class="grid nested-grid grid-nogutter p-0" style="height: calc(100% - 3.45em - 4.5em);">
        <div class="col-12 p-0 h-full">
            <div class="grid nested-grid grid-nogutter bg-white">
                <div class="max-w-100rem mx-auto w-full">
                    <div class="px-3 py-2 flex flex-column">
                        <Breadcrumb :home="breadcrumb_home" :model="breadcrumb_items">
                            <template #item="{ item, props }">
                                <router-link v-slot="{ href, navigate }" :to="item.route" custom>
                                    <a :href="href" v-bind="props.action" @click="navigate">
                                        <span :class="[item.icon, 'text-400 text-sm']"></span>
                                        <span class="text-400 text-sm">{{ item.label }}</span>
                                    </a>
                                </router-link>
                            </template>
                        </Breadcrumb>
                        <div class="flex flex-row">
                            <h3>{{ studyCollection.name }}</h3>
                        </div>
                    </div>
                </div>
            </div>
            <Splitter class="grid nested-grid grid-nogutter max-w-100rem mx-auto my-2 px-3 splitter-height">
                <SplitterPanel :class="{ 'hidden': !buttonToggleSplitterPanelRight }" class="col-12 p-0" :size="50" :minSize="1">
                    <div class="card h-full">
                        <Tabs value="0" class="h-full">
                            <TabList class="border-bottom-1 border-200">
                                <Tab value="0">Overview</Tab>
                                <Tab value="1">Ask iCognition</Tab>
                            </TabList>
                            <TabPanels>
                                <TabPanel value="0">
                                    <div class="w-full h-full bg-white border-1 border-300">
                                        <div class="overflow-y-auto px-2 py-3" style="height: calc(100% - 49.6px);">
                                            <div v-if="studyCollection.description != null">
                                                <h4 class="pb-2">Description</h4>
                                                <p class="line-height-2 font-mono">{{ studyCollection.description }}</p>
                                            </div>
                                            <div v-if="studyCollection.ai_explanation != null">
                                                <h4 class="pb-2">Summary</h4>
                                                <p class="line-height-2 font-mono">{{ studyCollection.ai_explanation }}</p>
                                            </div>
                                        </div>
                                    </div>
                                </TabPanel>
                                <TabPanel value="1">
                                    <div class="flex-column h-full bg-white border-1 border-300">
                                        <div class="overflow-y-auto px-2 py-2" ref="qanda_div" style="height: calc(100% - 2.75em);">
                                            <div class="panel mb-3">
                                                <div class="card">
                                                    <Card class="border-1 border-round border-300 bg-white shadow-3">
                                                        <template #header>
                                                        </template>
                                                        <template #content class="p-0">
                                                            <div class="bg-300 flex flex-column">
                                                                <div class="flex-row mx-3">
                                                                    <p class="flex-grow-1 py-1 text-sm text-black-alpha-90 border-round">
                                                                        You can ask the AI for a variety of information about this collection of documents, such as:
                                                                    </p>
                                                                    <ul>
                                                                        <li><a @click="showOutlineBuilderDialog()" class="px-0">Create an outline summary for my objective.</a></li>
                                                                        <li>What are the common themes supported by all documents associated with this project?</li>
                                                                    </ul>
                                                                </div>
                                                            </div>
                                                        </template>
                                                    </Card>
                                                    <DynamicDialog />
                                                </div>
                                            </div>
                                            <div class="panel mb-3" v-for="item in qas">
                                                <p class="flex text-xs justify-content-end">{{moment(item.created_at).format('DD MMM YYYY h:mm a')}}</p>
                                                <div class="card">
                                                    <Card class="border-1 border-round border-300 bg-white shadow-3">
                                                        <template #header>
                                                            <div class="border-1 border-round border-300 surface-300 flex border-bottom-1 border-noround-bottom border-top-none border-left-none border-right-none">
                                                            <p class="flex-grow-1 px-3 py-2 text-sm border-round font-semibold">{{item.question}}</p>
                                                            <Button icon="pi pi-times" class="bg-transparent border-transparent border-0 flex-shrink-0 text-black-alpha-90 pr-0" size="small" aria-label="Close"/>
                                                            </div>
                                                        </template>
                                                        <template #content class="p-0">
                                                            <div class="bg-white flex flex-column">
                                                            <p class="flex-grow-1 pl-3 py-1 text-sm text-black-alpha-90 border-round">{{item.answer}}</p>
                                                            <div class="flex-row">
                                                                <Button icon="pi pi-copy" class="bg-transparent border-transparent border-0 text-surface-500 flex-shrink-0 align-content-start flex-wrap pr-0" size="large" aria-label="Close"/>
                                                                <Button icon="pi pi-clipboard" class="bg-transparent border-transparent border-0 text-surface-500 flex-shrink-0 align-content-start flex-wrap pr-0" size="large" aria-label="Close"/>
                                                            </div>
                                                            </div>
                                                        </template>
                                                    </Card>
                                                </div>
                                            </div>
                                        </div>
                                        <div class="flex p-2 bg-white border-top-1 border-300" style="height: 2.75em;">
                                            <InputText @keyup.enter="handleAsk" class="flex-grow-1 p-1 font-mono" type="text" v-model="question" />
                                            <Button class="flex-shrink-0 px-3 py-1 ml-1 bg-primary-500 text-white" icon="pi pi-arrow-right" @click="handleAsk" />
                                        </div>
                                    </div>
                                </TabPanel>
                                <TabPanel value="2">
                                    <div class="flex-column my-1 h-full surface-100">
                                        <div class="overflow-y-auto px-2 py-2" style="height: calc(100% - 63.59px);">
                                            <div v-for="doc in studyCollection.related_docs">
                                                <div>{{doc.title}} - {{ doc.cosine_similarity }}</div>
                                            </div>
                                        </div>
                                        <div class="flex p-2 pr-0 bg-white">
                                            <MultiSelect v-model="selectedDocuments" display="chip" :options="candidateDocs" optionLabel="title" filter placeholder="Select Documents" class="w-full md:w-80" style="max-width: 85%;">
                                                <template #option="slotProps">
                                                    <div class="flex items-center">
                                                        <div>{{ slotProps.option.title }}</div>
                                                    </div>
                                                </template>
                                            </MultiSelect>
                                            <Button class="flex-shrink-0 px-3 py-1 ml-1" label="Apply" @click="handleApply" />
                                        </div>
                                    </div>
                                </TabPanel>
                            </TabPanels>
                        </Tabs>
                    </div>
                </SplitterPanel>
                <SplitterPanel :class="{ 'splitter-panel-container-full': !buttonToggleSplitterPanelRight }" class="col-12 p-0" :minSize="1" :size="50">
                    <div class="card h-full border-1 border-300">
                        <div class="col-12 py-0 bg-white border-bottom-1 border-300">
                            <div class="col-12 p-0 inline-flex pt-2">
                                <h3>Source Documents</h3>
                            </div>
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
                                <Button type="button" icon="pi pi-plus" label="Add Sources" aria-label="Add Sources" class="p-2 mr-2 bg-primary-500" @click="showAddSourcesDialog" />
                                <DynamicDialog/>
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
                                                <p class="font-mono">{{ slotProps.data.is_about}}</p>
                                            </div>
                                        </div>
                                        <div class="grid">
                                            <div class="col-fixed" style="width: 100px;">
                                                <p>Key Points:</p>
                                            </div>
                                            <div class="col-11 font-mono" style="max-width: 60%;">
                                                <div v-if="slotProps.data.tldr" v-html="renderMarkdown(slotProps.data.tldr)"></div>
                                                <div v-else>No key points available.</div>
                                            </div>  
                                        </div>
                                    </div>
                                </template>
                            </DataTable>
                        </div>
                    </div>
                </SplitterPanel>
            </Splitter>
        </div>
    </div>
</template>