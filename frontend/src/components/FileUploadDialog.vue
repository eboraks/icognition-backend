<template>
    <Dialog v-model:visible="isVisible" modal header="Upload Document(s)" :style="{ width: '60%' }">
        <template #header>
            <div class="inline-flex gap-2">
                <span class="font-semibold text-2xl">Upload Document(s)</span>
            </div>
        </template>
        <div class="grid grid-nested">
            <div class="col-12 px-4">
                <div class="grid flex justify-content-end">
                    <div class="col-12">
                        <FileUpload ref="files" 
                            mode="basic"
                            @uploader="onUpload"
                            :custom-upload="true" 
                            :multiple="false" 
                            :auto="true">
                        </FileUpload>
                    </div>
                </div>
                <div class="grid grid-nogutter flex justify-content-end gap-2">
                    <Button type="button" label="Close" class="bg-blue-500 mt-3 flex justify-content-end" @click="closeDialog"></Button>
                </div>
            </div>
        </div>
    </Dialog>
</template>

<script lang="ts" setup>
import { ref } from 'vue';
import Dialog from 'primevue/dialog';
import Button from 'primevue/button';

const isVisible = ref(true);
import FileUpload from 'primevue/fileupload';
import { handleFileUpload } from '@/composables/handleFileUpload';
import user_state from '@/composables/getUser';


const emit = defineEmits(['update:modelValue', 'upload']);

const files = ref<File[]>([]);

const closeDialog = () => {
    emit('update:modelValue', false);
};


const onUpload = (e: any) => {

console.log('Upload Event: ', e);

handleFileUpload(e, user_state.user?.uid as string);

};
</script>
