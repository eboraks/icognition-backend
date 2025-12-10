<template>
  <div class="admin-prompts-view">
    <Toast />
    <div class="admin-header mb-4">
      <h1 class="text-900 m-0 mb-2">Prompt Management</h1>
      <p class="text-600 m-0">Manage and version all application prompts</p>
    </div>

    <div class="admin-content pb-6">
      <!-- Debug info -->
      <div v-if="loading" style="padding: 2rem; text-align: center;">
        <p>Loading prompts...</p>
      </div>
      <div v-else-if="prompts.length === 0" style="padding: 2rem; text-align: center;">
        <p>No prompts found. Click Refresh to load.</p>
      </div>
      
      <!-- Filters -->
      <div class="filters-section">
        <div class="filter-group">
          <label for="prompt-type-filter">Filter by Type:</label>
          <select 
            id="prompt-type-filter" 
            v-model="selectedPromptType"
            @change="loadPrompts"
            class="filter-select"
          >
            <option value="">All Types</option>
            <option v-for="type in promptTypes" :key="type" :value="type">
              {{ formatPromptType(type) }}
            </option>
          </select>
        </div>
        <Button 
          label="Refresh" 
          icon="pi pi-refresh" 
          @click="loadPrompts"
          :loading="loading"
        />
      </div>

      <!-- Prompts List -->
      <div class="prompts-section mb-5">
        <DataTable 
          :value="prompts" 
          :loading="loading"
          :paginator="true"
          :rows="20"
          sortField="prompt_type"
          :sortOrder="1"
          stripedRows
          scrollable
          scrollHeight="450px"
          class="prompts-table"
        >
          <Column field="prompt_type" header="Type" sortable>
            <template #body="{ data }">
              <strong>{{ formatPromptType(data.prompt_type) }}</strong>
            </template>
          </Column>
          <Column field="version" header="Version" sortable></Column>
          <Column field="content" header="Content">
            <template #body="{ data }">
              <div class="content-preview">{{ truncateContent(data.content, 100) }}</div>
            </template>
          </Column>
          <Column field="created_at" header="Created" sortable>
            <template #body="{ data }">
              {{ formatDate(data.created_at) }}
            </template>
          </Column>
          <Column class="w-5" field="created_by" header="Created By">
            <template #body="{ data }">
              {{ data.created_by || 'System' }}
            </template>
          </Column>
          <Column field="is_active" header="Active">
            <template #body="{ data }">
              <Tag :value="data.is_active ? 'Active' : 'Inactive'" 
                   :severity="data.is_active ? 'success' : 'danger'" />
            </template>
          </Column>
          <Column header="Actions" :style="{ width: '180px', minWidth: '180px' }">
            <template #body="{ data }">
              <div class="action-buttons">
                <Button 
                  icon="pi pi-pencil" 
                  label="Edit" 
                  size="small"
                  @click="openEditDialog(data)"
                  class="p-button-text"
                />
                <Button 
                  icon="pi pi-history" 
                  label="History" 
                  size="small"
                  @click="openHistoryDialog(data.prompt_type)"
                  class="p-button-text"
                />
              </div>
            </template>
          </Column>
        </DataTable>
      </div>
    </div>

    <!-- Edit/Create Dialog -->
    <Dialog 
      v-model:visible="editDialogVisible" 
      :header="editingPrompt ? `Edit Prompt: ${formatPromptType(editingPrompt.prompt_type)}` : 'Create New Prompt'"
      :modal="true"
      :style="{ width: '80vw', maxWidth: '900px' }"
      @hide="closeEditDialog"
    >
      <div class="edit-form">
        <div class="form-group" v-if="!editingPrompt">
          <label for="prompt-type">Prompt Type:</label>
          <select id="prompt-type" v-model="formData.prompt_type" class="form-select">
            <option value="">Select Type</option>
            <option v-for="type in promptTypes" :key="type" :value="type">
              {{ formatPromptType(type) }}
            </option>
          </select>
        </div>
        
        <div class="form-group">
          <label for="prompt-description">Description:</label>
          <InputText 
            id="prompt-description"
            v-model="formData.description" 
            placeholder="Optional description for this version"
          />
        </div>
        
        <div class="form-group">
          <label for="prompt-content">Content:</label>
          <Textarea 
            id="prompt-content"
            v-model="formData.content" 
            :rows="15"
            class="prompt-content-textarea"
            placeholder="Enter prompt content..."
          />
        </div>
      </div>
      
      <template #footer>
        <Button label="Cancel" icon="pi pi-times" @click="closeEditDialog" class="p-button-text" />
        <Button 
          label="Save" 
          icon="pi pi-check" 
          @click="savePrompt" 
          :loading="saving"
          autofocus
        />
      </template>
    </Dialog>

    <!-- History Dialog -->
    <Dialog 
      v-model:visible="historyDialogVisible" 
      :header="`Version History: ${formatPromptType(selectedHistoryType)}`"
      :modal="true"
      :style="{ width: '70vw', maxWidth: '800px' }"
      @hide="closeHistoryDialog"
    >
      <DataTable 
        :value="historyPrompts" 
        :loading="loadingHistory"
        sortField="version"
        :sortOrder="-1"
        scrollable
        scrollHeight="400px"
      >
        <Column field="version" header="Version" sortable></Column>
        <Column field="content" header="Content">
          <template #body="{ data }">
            <div class="content-preview">{{ truncateContent(data.content, 150) }}</div>
          </template>
        </Column>
        <Column field="description" header="Description">
          <template #body="{ data }">
            {{ data.description || '-' }}
          </template>
        </Column>
        <Column field="created_at" header="Created" sortable>
          <template #body="{ data }">
            {{ formatDate(data.created_at) }}
          </template>
        </Column>
        <Column field="created_by" header="Created By">
          <template #body="{ data }">
            {{ data.created_by || 'System' }}
          </template>
        </Column>
      </DataTable>
    </Dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { useToast } from 'primevue/usetoast';
import DataTable from 'primevue/datatable';
import Column from 'primevue/column';
import Button from 'primevue/button';
import Dialog from 'primevue/dialog';
import InputText from 'primevue/inputtext';
import Textarea from 'primevue/textarea';
import Tag from 'primevue/tag';
import Toast from 'primevue/toast';
import { adminService, type PromptResponse, type PromptCreate, type PromptUpdate } from '@/services/AdminService';

const toast = useToast();

// State
const prompts = ref<PromptResponse[]>([]);
const loading = ref(false);
const selectedPromptType = ref('');
const editingPrompt = ref<PromptResponse | null>(null);
const editDialogVisible = ref(false);
const historyDialogVisible = ref(false);
const historyPrompts = ref<PromptResponse[]>([]);
const loadingHistory = ref(false);
const selectedHistoryType = ref('');
const saving = ref(false);

const formData = ref<PromptCreate>({
  prompt_type: '',
  content: '',
  description: ''
});

// Prompt types (matching backend PromptType enum + react_agent_system)
const promptTypes = [
  'content_summary',
  'entity_extraction',
  'topic_categorization',
  'sentiment_analysis',
  'language_detection',
  'content_validation',
  'bullet_points',
  'react_agent_system',
  'react_agent_template'
];

// Methods
const loadPrompts = async () => {
  loading.value = true;
  try {
    console.log('Loading prompts...');
    if (selectedPromptType.value) {
      prompts.value = await adminService.getPromptsByType(selectedPromptType.value, true);
    } else {
      prompts.value = await adminService.listPrompts({ include_inactive: true });
    }
    console.log('Prompts loaded:', prompts.value.length);
  } catch (error: any) {
    console.error('Error loading prompts:', error);
    toast.add({
      severity: 'error',
      summary: 'Error',
      detail: error.message || 'Failed to load prompts',
      life: 3000
    });
  } finally {
    loading.value = false;
  }
};

const openEditDialog = (prompt: PromptResponse) => {
  editingPrompt.value = prompt;
  formData.value = {
    prompt_type: prompt.prompt_type,
    content: prompt.content,
    description: prompt.description || ''
  };
  editDialogVisible.value = true;
};

const openCreateDialog = () => {
  editingPrompt.value = null;
  formData.value = {
    prompt_type: '',
    content: '',
    description: ''
  };
  editDialogVisible.value = true;
};

const closeEditDialog = () => {
  editDialogVisible.value = false;
  editingPrompt.value = null;
  formData.value = {
    prompt_type: '',
    content: '',
    description: ''
  };
};

const savePrompt = async () => {
  if (!formData.value.prompt_type || !formData.value.content.trim()) {
    toast.add({
      severity: 'warn',
      summary: 'Validation Error',
      detail: 'Prompt type and content are required',
      life: 3000
    });
    return;
  }

  saving.value = true;
  try {
    if (editingPrompt.value) {
      // Update existing prompt (creates new version)
      await adminService.updatePrompt(editingPrompt.value.id, {
        content: formData.value.content,
        description: formData.value.description
      });
      toast.add({
        severity: 'success',
        summary: 'Success',
        detail: 'New prompt version created successfully',
        life: 3000
      });
    } else {
      // Create new prompt
      await adminService.createPrompt(formData.value);
      toast.add({
        severity: 'success',
        summary: 'Success',
        detail: 'Prompt created successfully',
        life: 3000
      });
    }
    closeEditDialog();
    await loadPrompts();
  } catch (error: any) {
    toast.add({
      severity: 'error',
      summary: 'Error',
      detail: error.message || 'Failed to save prompt',
      life: 3000
    });
  } finally {
    saving.value = false;
  }
};

const openHistoryDialog = async (promptType: string) => {
  selectedHistoryType.value = promptType;
  historyDialogVisible.value = true;
  loadingHistory.value = true;
  try {
    historyPrompts.value = await adminService.getPromptHistory(promptType);
  } catch (error: any) {
    toast.add({
      severity: 'error',
      summary: 'Error',
      detail: error.message || 'Failed to load prompt history',
      life: 3000
    });
  } finally {
    loadingHistory.value = false;
  }
};

const closeHistoryDialog = () => {
  historyDialogVisible.value = false;
  selectedHistoryType.value = '';
  historyPrompts.value = [];
};

const formatPromptType = (type: string): string => {
  return type
    .split('_')
    .map(word => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ');
};

const truncateContent = (content: string, length: number): string => {
  if (!content) return '';
  return content.length > length ? content.substring(0, length) + '...' : content;
};

const formatDate = (dateString: string): string => {
  if (!dateString) return '-';
  const date = new Date(dateString);
  return date.toLocaleString();
};

// Lifecycle
onMounted(async () => {
  console.log('AdminPromptsView mounted');
  try {
    await loadPrompts();
  } catch (error) {
    console.error('Error in onMounted:', error);
  }
});
</script>

<style scoped>
.admin-prompts-view {
  padding: 2rem;
  padding-bottom: 4rem;
  max-width: 1400px;
  margin: 0 auto;
  min-height: calc(100vh - 4rem);
}

.admin-header h1 {
  font-size: 2rem;
  font-weight: 600;
}

.filters-section {
  display: flex;
  gap: 1rem;
  align-items: flex-end;
  margin-bottom: 1.5rem;
}

.filter-group {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.filter-group label {
  font-weight: 500;
}

.filter-select {
  padding: 0.5rem;
  border: 1px solid #ced4da;
  border-radius: 4px;
  min-width: 200px;
}

.prompts-table {
  margin-top: 1rem;
}

.prompts-table :deep(.p-datatable-wrapper) {
  border: 1px solid #dee2e6;
  border-radius: 4px;
}

.prompts-table :deep(.p-datatable-scrollable-body) {
  max-height: 450px;
}

.prompts-table :deep(.p-datatable-tbody) {
  padding-bottom: 2rem;
}

.prompts-table :deep(.p-datatable-tbody tr:last-child td) {
  padding-bottom: 2rem;
  border-bottom: none;
}

.prompts-table :deep(.p-datatable-footer) {
  padding: 1rem;
  border-top: 1px solid #dee2e6;
  position: sticky;
  bottom: 0;
  background: white;
  z-index: 1;
}

.content-preview {
  max-width: 300px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.action-buttons {
  display: flex;
  gap: 0.5rem;
  flex-wrap: nowrap;
  white-space: nowrap;
}

.edit-form {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.form-group label {
  font-weight: 500;
}

.form-select {
  padding: 0.5rem;
  border: 1px solid #ced4da;
  border-radius: 4px;
}

.prompt-content-textarea {
  width: 100%;
  font-family: monospace;
  font-size: 0.9rem;
}
</style>

