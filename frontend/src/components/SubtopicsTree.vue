<script setup lang="ts">
    import { ref } from 'vue';
    import Tree, { TreeSelectionKeys } from 'primevue/tree';
    import { useDocumentStore } from '@/stores/documents_store';
    const documentStore = useDocumentStore();

    const selectedKey = ref<TreeSelectionKeys | undefined>(undefined)

    const checkedIds = ref(new Set())

const onNodeSelect = (node: any) => {
        console.log("Node Selected: ", checkedIds.value);
        documentStore.tree_selected_docs_ids = new Set([...documentStore.tree_selected_docs_ids, ...(node.doc_ids as string[])]);
        console.log("Node Selected: ", checkedIds.value);
        
    };

    const onNodeUnselect = (node: any) => {
        console.log("Node Unselected: ", node);
        documentStore.tree_selected_docs_ids = new Set(
            [...documentStore.tree_selected_docs_ids].filter(id => !node.doc_ids.includes(id))
        );
        console.log("Node Unselected: ", checkedIds.value);
    };

</script>
<template>
    <div class="sticky justify-content-center h-full">
        <Tree v-model:selectionKeys="selectedKey" :value="documentStore.getTreeNodes"
            selectionMode="checkbox"
            class="w-full text-xs p-0 text-white h-full"
            :filter="true"
            v-on:node-select="onNodeSelect"
            v-on:node-unselect="onNodeUnselect">
         </Tree>  
    </div>

</template>

