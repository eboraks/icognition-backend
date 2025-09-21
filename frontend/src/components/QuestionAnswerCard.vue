<template>
    <div class="panel mb-3">
        <p class="flex text-xs justify-content-start">{{moment(qanda?.created_at).format('DD MMM YYYY h:mm a')}}</p>
        <div class="card">
            <Card class="border-1 border-round border-300 bg-white shadow-3">
                <template #header>
                    <div class="border-1 border-round border-300 surface-300 flex border-bottom-1 border-noround-bottom border-top-none border-left-none border-right-none">
                        <p class="flex-grow-1 px-3 py-2 text-sm border-round font-semibold">{{qanda?.question}}</p>
                        <Button icon="pi pi-times" 
                            class="bg-transparent border-transparent border-0 flex-shrink-0 text-black-alpha-50" 
                            size="small" aria-label="Close" @click="handleQandARemove(uuid)"/>
                    </div>
                </template>
                <template #content class="p-0">
                    <div v-if="qanda?.status == null">
                        <div>Loading...</div>
                    </div>
                    <div class="bg-white flex flex-column">
                        <div class="flex-row mx-3">
                            <p v-if="is_answer_include_html" class="flex-grow-1 py-1 text-sm text-black-alpha-90 border-round" v-html="qanda?.answer"></p>
                            <p v-else class="flex-grow-1 py-1 text-sm text-black-alpha-90 border-round">{{qanda?.answer}}</p>
                        </div>
                        <div class="flex-row mx-3">
                            <Button type="button" class="bg-white text-600 border-none" size="small" icon="pi pi-comment" @click="handleHightLightCitiation()" />

                            <Button v-if="qanda?.status === 'COMPLETED_NO_SAVE'" 
                                type="button" class="bg-transparent border-transparent border-0 text-500 flex-shrink-0 align-content-start flex-wrap pb-0 pr-0" 
                                size="large" aria-label="Save" icon="pi pi-save" />
                        </div>
                    </div>
                </template>
            </Card>
        </div>
    </div>
</template>

<script setup lang="ts">
    import { QuestionsAnswersStore } from '@/stores/questions_answers_store';
    import moment from 'moment';
    import { computed } from 'vue';

    const qa_store = QuestionsAnswersStore();
    const props = defineProps({ qanda: Object, uuid: String });
    const emits = defineEmits(['highlight_citiation']);

    //Computed fuction to format the answer, if the string include html tags then it will be rendered as html
    const is_answer_include_html = computed(() => {
        if (props.qanda?.answer === undefined) {
            return false;
        } else {
            return props.qanda.answer.includes('<');
        }
    })

    const handleHightLightCitiation = () => {
        console.log('Hightlight Citation: ', props.qanda);
        emits('highlight_citiation', props.qanda)
    }

    const handleQandARemove = (uuid: string | undefined) => {
        //call backend to remove the QandA and only then remove it from the UI
        console.log('Remove QandA: ', uuid);
        qa_store.delete_question(uuid as string);
    }
</script>