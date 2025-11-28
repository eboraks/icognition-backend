<template>
  <div class="flex align-items-center justify-content-between gap-2 w-full">
    <IconField iconPosition="left" class="flex-1">
      <InputIcon class="pi pi-search" style="top: 75% !important; transform: translateY(-75%) !important;" />
      <InputText v-model="localSearch" placeholder="Search" class="w-full" @input="onSearch" />
    </IconField>
    <div class="flex gap-2" style="flex-shrink: 0;">
      <Button label="Expand All" icon="pi pi-plus" text @click="$emit('expandAll')" class="text-primary" />
      <Button label="Collapse All" icon="pi pi-minus" text @click="$emit('collapseAll')" class="text-primary" />
      <Button label="Upload PDF" severity="info" @click="onUploadClick" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import InputText from 'primevue/inputtext';
import Button from 'primevue/button';
import IconField from 'primevue/iconfield';
import InputIcon from 'primevue/inputicon';

const emit = defineEmits(['search', 'expandAll', 'collapseAll', 'upload']);
const props = defineProps<{ search?: string }>();

const localSearch = ref(props.search ?? '');

const onSearch = () => emit('search', localSearch.value);
const onUploadClick = () => emit('upload', []);
</script>


