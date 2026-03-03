<template>
  <DataTable :value="documents"
             v-model:expandedRows="expandedRows"
             dataKey="id"
             responsiveLayout="scroll"
             class="w-full"
             :loading="loading">
    <Column expander style="width:3rem" />
    <Column field="title" header="Title">
      <template #body="{ data }">
        <div class="flex align-items-center">
          <i :class="getIconForType(data.type)" class="mr-2 text-600"></i>
          <a 
            v-if="data.url || data.sourceUrl" 
            :href="data.url || data.sourceUrl" 
            target="_blank" 
            rel="noopener noreferrer"
            class="cursor-pointer text-primary hover:underline">
            {{ data.title }}
          </a>
          <a 
            v-else
            class="cursor-pointer text-primary" 
            @click="$emit('open', data)">
            {{ data.title }}
          </a>
        </div>
      </template>
    </Column>
    <Column field="updatedAt" header="Last updated" style="width:10rem"/>
    <Column header="Source" style="width:10rem">
      <template #body="{ data }">
        <a v-if="data.sourceUrl" :href="data.sourceUrl" target="_blank" rel="noopener noreferrer" class="text-primary">{{ data.sourceHost }}</a>
        <span v-else class="text-600">-</span>
      </template>
    </Column>
    <Column header="Actions" style="width:10rem">
      <template #body="{ data }">
        <SplitButton 
          label="Delete" 
          icon="pi pi-trash" 
          :model="getActionItems(data)" 
          @click="handleDelete(data)"
          size="small"
          severity="danger"
          outlined
        />
      </template>
    </Column>

    <template #expansion="{ data }">
      <div class="p-4 bg-white border-round">
        <div v-if="data.keyPoints" class="text-700" v-html="renderMarkdown(data.keyPoints)"></div>
        <div v-else class="text-600 text-sm">No AI content available.</div>
      </div>
    </template>
  </DataTable>
</template>

<script setup lang="ts">
import { ref, watchEffect, computed } from 'vue';
import { marked } from 'marked';
import DataTable from 'primevue/datatable';
import Column from 'primevue/column';
import SplitButton from 'primevue/splitbutton';
import { useConfirm } from 'primevue/useconfirm';
import { useToast } from 'primevue/usetoast';
import { formatUrlsAsLinks } from '@/composables/useUrlFormatter';
import { documentService } from '@/services/DocumentService';
import { bookmarkService } from '@/services/BookmarkService';

interface DocRow {
  id: string | number;
  title: string;
  updatedAt: string;
  url?: string;
  sourceUrl?: string;
  sourceHost?: string;
  summary?: string;
  keyPoints?: string;
  type?: string;
}

const props = defineProps<{ documents: DocRow[]; expandAllKey?: number; loading?: boolean }>();
const emit = defineEmits(['open', 'refresh']);

const expandedRows = ref<any>({});
const confirm = useConfirm();
const toast = useToast();

const renderMarkdown = (content?: string) => {
  if (!content) return '';
  // Fixes a bug where links open within app by setting target to _blank
  const renderer = new marked.Renderer();
  renderer.link = ({ href, title, text }) => `<a href="${href}" target="_blank" rel="noopener noreferrer" class="text-primary hover:underline" title="${title || ''}">${text}</a>`;
  marked.setOptions({ renderer });
  return marked.parse(content);
};

const getIconForType = (type?: string) => {
  switch (type) {
    case 'web':
      return 'pi pi-globe';
    case 'pdf':
      return 'pi pi-file-pdf';
    case 'document':
      return 'pi pi-file';
    default:
      return 'pi pi-file';
  }
};

const getActionItems = (doc: DocRow) => {
  return [
    {
      label: 'Reprocess',
      icon: 'pi pi-refresh',
      command: () => handleReprocess(doc)
    }
  ];
};

const handleDelete = async (doc: DocRow) => {
  confirm.require({
    message: `Are you sure you want to delete "${doc.title}"? This will also delete any associated bookmark.`,
    header: 'Confirm Delete',
    icon: 'pi pi-exclamation-triangle',
    acceptClass: 'p-button-danger',
    accept: async () => {
      try {
        console.log(`Starting delete process for document ${doc.id}`);
        
        // CRITICAL: Must delete bookmark FIRST due to foreign key constraint
        const bookmark = await bookmarkService.findBookmarkByDocumentId(Number(doc.id));
        
        if (bookmark) {
          console.log(`Found bookmark ${bookmark.id} for document ${doc.id}, deleting bookmark first...`);
          await bookmarkService.deleteBookmark(bookmark.id);
          console.log(`Successfully deleted bookmark ${bookmark.id}`);
        } else {
          console.log(`No bookmark found for document ${doc.id}`);
        }
        
        // Now delete the document
        console.log(`Deleting document ${doc.id}...`);
        await documentService.deleteDocument(Number(doc.id));
        console.log(`Successfully deleted document ${doc.id}`);
        
        toast.add({ 
          severity: 'success', 
          summary: 'Deleted', 
          detail: `Document "${doc.title}" has been deleted`, 
          life: 3000 
        });
        
        // Emit refresh event to parent
        emit('refresh');
      } catch (error: any) {
        console.error('Error deleting document:', error);
        toast.add({ 
          severity: 'error', 
          summary: 'Error', 
          detail: error.message || 'Failed to delete document', 
          life: 5000 
        });
      }
    }
  });
};

const handleReprocess = async (doc: DocRow) => {
  try {
    await documentService.reprocessDocument(Number(doc.id), false);
    
    toast.add({ 
      severity: 'info', 
      summary: 'Reprocessing', 
      detail: `Document "${doc.title}" is being reprocessed`, 
      life: 3000 
    });
    
    // Optionally emit refresh event
    setTimeout(() => emit('refresh'), 2000);
  } catch (error: any) {
    console.error('Error reprocessing document:', error);
    toast.add({ 
      severity: 'error', 
      summary: 'Error', 
      detail: error.message || 'Failed to reprocess document', 
      life: 5000 
    });
  }
};

watchEffect(() => {
  // Re-compute when expandAllKey changes to support external expand/collapse toggles
  // Parent can toggle by changing the key and setting expandedRows appropriately
});

// Expose methods for parent to control expansion
defineExpose({ expandedRows });
</script>

<style scoped>
</style>


