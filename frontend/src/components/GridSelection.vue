<template>
    <div class="col-12 grid grid-nogutter p-0">
        <div class="flex bg-teal-200 flex-row w-full">
            <div class="col-6">
                <p class="inline mr-3 text-black-alpha-90">{{ props.selectedItems.length }} Checked Item<span v-if="props.selectedItems.length > 1">s</span></p>
                <Button type="button" label="Clear" aria-label="Clear" class="p-2 mr-2 bg-white text-black-alpha-90" @click="clearItems" />
            </div>
            <div class="col-6 flex flex-flow justify-content-end">
                <div v-if="props.addToCollection?.length as number > 0">
                    <Select v-model="selectedCollection" :options="props.addToCollection" optionLabel="name" placeholder="Add to Collection" class="mr-2" >
                        <template #option="slotProps">
                            <div class="flex items-center">
                                <div>{{ slotProps.option.name }}</div>
                            </div>
                        </template>
                    </Select>
                    <Button class="flex-shrink-0 px-3 py-1 mr-3" label="Apply" @click="handleApply" />
                </div>
                <div v-if="props.origin != 'addsources'">
                    <Button type="button" label="Remove" aria-label="Remove" class="p-2 mr-2 bg-white text-black-alpha-90" @click="deletedItems" />
                    <!-- <Button type="button" label="Archive" aria-label="Archive" class="p-2 mr-2 bg-white text-black-alpha-90" @click="selectedItems.value = []" /> -->
                </div>
            </div>
        </div>
    </div>
</template>

<script lang="ts" setup>
    import { ref } from 'vue';
    import { StudyCollection } from '@/components/models/StudyCollection.ts';

    const emit = defineEmits({
        'collectionDocumentLink': null,
        'unselectItems': null
    });
    const selectedCollection = ref<any>();

    // props
    export interface GridSelectionProps {
        addToCollection?: Array<StudyCollection>;
        selectedItems?: Array<any>;
        method: Function;
        origin: String;
    }
    const props = withDefaults(defineProps<GridSelectionProps>(), {
        addToCollection: Array<any>,
        selectedItems: Array<any>,
        method: Function,
        origin: String
    });

    const clearItems = async () => {
        emit('unselectItems');
    }

    const deletedItems = async () => {
        console.log(props);
        props.selectedItems.forEach(selectedItem => {
            props.method(selectedItem.id);
        });
    }

    const handleApply = async () => {
        emit('collectionDocumentLink', {
            studyCollection: selectedCollection,
            documents: props.selectedItems
        } );
    }
</script>