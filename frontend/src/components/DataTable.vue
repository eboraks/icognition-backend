<script setup lang="ts">
  import DocDataCard from '@/components/DocDataCard.vue';
  import { DocModel } from './models/DocModel';

  export interface DataTableProps {
    documents?: Array<DocModel>;
  }
  const props = withDefaults(defineProps<DataTableProps>(), {
    documents: Array<DocModel | any>
  });
</script>
<template>

  <ScrollPanel style="width: 102%; height: 1000px"  
      :pt="{ bary: 'hover:bg-primary-400 bg-primary-300 opacity-100'}">
                                    
    <TransitionGroup name="list" tag="div">
        <div class="w-full" v-for="(document, index) in props.documents" :key="index">
            <DocDataCard :doc="document" />
        </div>
    </TransitionGroup>
  </ScrollPanel>
    
</template>

<style scoped>
  .list-move,
  .list-enter-active,
  .list-leave-active {
    transition: all 0.5s ease;
  }
  .list-enter-from,
  .list-leave-to {
    opacity: 0;
    transform: translateX(20px);
  }
  .list-leave-active {
    position: absolute;
  }
</style>
