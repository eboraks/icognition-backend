<script setup lang="ts">
    import { inject, onMounted, ref } from 'vue';

    const buttonPreview = ref<boolean | null>(null);
    const buttonText = ref<boolean | null>(null);
    const buttonDesign = ref<boolean | null>(null);
    const dialogRef = inject("dialogRef") as any;
    const study_collection = ref([]);
    study_collection.value = dialogRef.value.options.data;

    onMounted(async() => {
        try {
            buttonPreview.value = true;
        } catch (err) {
            console.log("Error: ", err);
        }
    });

    const closeStudyCollection = async () => {
        dialogRef.value.close(study_collection.value);
    }

    const selectButton = async(buttonLabel: any) => {
        buttonPreview.value = false;
        buttonText.value = false;
        buttonDesign.value = false;
        
        switch(buttonLabel) {
            case 'preview':
                buttonPreview.value = true;
                break;
            case 'text':
                buttonText.value = true;
                break;
            case 'design':
                buttonDesign.value = true;
                break;
            default: 
                buttonPreview.value = false;
                buttonText.value = false;
                buttonDesign.value = false;
                break;
        }
        console.log('buttonText', buttonPreview.value);
        console.log('buttonText', buttonText.value);
        console.log('buttonDesign', buttonDesign.value);
    }

</script>

<template>
    <div class="grid grid-nested grid-nogutter">
        <h2 class="mb-1 ml-2">Outline Builder</h2>
    </div>
    <div class="grid grid-nested grid-nogutter">
        <div class="col-12 px-2">
            <div class="card h-full">
                <Tabs value="0" class="h-full">
                    <TabList>
                        <ButtonGroup class="surface-200 px-3 border-round-3xl">
                            <Button @click="selectButton('preview')" ref="buttonPreview" aria-label="Preview" label="Preview" class="p-2 bg-transparent text-xl text-black-alpha-50 border-round-3xl w-10rem h-3rem border-none" :class="{'active': buttonPreview != null && buttonPreview}" icon="pi pi-eye" size="large" />
                            <Button @click="selectButton('text')" ref="buttonText" aria-label="Text" label="Text" class="m-3 bg-transparent text-xl text-black-alpha-50 border-round-3xl w-10rem h-3rem border-none" :class="{'active': buttonText != null && buttonText}" icon="pi pi-pencil" size="large" />
                            <Button @click="selectButton('design')" ref="buttonDesign" aria-label="Design" label="Design" class="p-2 bg-transparent text-xl text-black-alpha-50 border-round-3xl w-10rem h-3rem border-none" :class="{'active': buttonDesign != null && buttonDesign}" icon="pi pi-objects-column" size="large" />
                        </ButtonGroup>
                        
                    </TabList>
                    <TabPanels>
                        <TabPanel value="0">

                        </TabPanel>
                        <TabPanel value="1">
                        </TabPanel>
                        <TabPanel value="2">
                        </TabPanel>
                    </TabPanels>
                </Tabs>
            </div>
            <div class="grid grid-nogutter flex justify-content-end gap-2">
                <Button type="button" label="Close" class="text-black-alpha-90 mt-3 surface-400 border-300 border-400" severity="secondary" @click="closeStudyCollection"></Button>
            </div>
        </div>
    </div>
</template>