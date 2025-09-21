import { defineStore } from 'pinia';
import { ref, watch, onUnmounted, computed } from 'vue';
import { AskQuestionAnswerModel } from '@/components/models/AskQuestionAnswerModel.ts';
import { DocModel } from '@/components/models/DocModel.ts';
import { documentService } from '@/services/DocumentService';
import { api } from '@/services/httpClient';


export const useDocumentStore = defineStore('documentStore', () => {
    const docs = ref<DocModel[]>([]);
    const docs_filtered = ref<DocModel[]>([]);
    const answer = ref<null | string>(null);
    const answerResponse = ref(new AskQuestionAnswerModel());
    const resp_type = ref<null | string>(null);
    const errorLibrary = ref<string | null>(null);
    const isPendingLibrary = ref(false);
    const tree_nodes = ref<any[]>([]);
    const tree_selected_docs_ids = ref<Set<string>>(new Set());
    const entities_names = ref<any[]>([]);
    const socket = ref<any | null>(null);

    // Load docs and subtopics_nodes from local storage if available
    const loadFromLocalStorage = () => {
        const storedDocs = localStorage.getItem('docs');
        if (storedDocs) {
            docs.value = JSON.parse(storedDocs);
        }
        const storedSubtopicsNodes = localStorage.getItem('subtopics_nodes');
        if (storedSubtopicsNodes) {
            tree_nodes.value = JSON.parse(storedSubtopicsNodes);
        }
    };

    // Save docs and subtopics_nodes to local storage whenever they change
    watch(docs, (newDocs) => {
        localStorage.setItem('docs', JSON.stringify(newDocs));
    });

    watch(tree_nodes, (newSubtopicsNodes) => {
        localStorage.setItem('subtopics_nodes', JSON.stringify(newSubtopicsNodes));
    });

    const fetchDocuments = async (user_id: any) => {
        // If socket is not initialized, initialize it
        if (!socket.value) {
            setupWebSocket(user_id);
        }

        errorLibrary.value = null;
        isPendingLibrary.value = true;
        try {
            // Use the new DocumentService to get documents
            const response = await documentService.getDocuments({ page_size: 100 });
            docs.value = response.documents as DocModel[];
            isPendingLibrary.value = false;
        } catch (err: any) {
            errorLibrary.value = err.message;
            isPendingLibrary.value = false;
            console.log("Error: ", errorLibrary.value);
        }
    };

    const searchDocuments = async (user_id: string, search_term: string) => {
        errorLibrary.value = null;
        isPendingLibrary.value = true;
        resp_type.value = null;
        try {
            // Use the new DocumentService for search
            const response = await documentService.searchDocuments(search_term);
            resp_type.value = 'search'; // Set response type
            docs.value = response.documents as DocModel[];
            
            console.log("Library documents: ", docs.value);
            
            isPendingLibrary.value = false;
        } catch (err: any) {
            errorLibrary.value = err.message;
            isPendingLibrary.value = false;
            console.log("Error: ", errorLibrary.value);
        }
    };

    const getSubtopicsNodes = async (user_id: string) => {
        errorLibrary.value = null;
        isPendingLibrary.value = true;
        console.log("User id: ", user_id);
        try {
            // This endpoint might not exist in the new backend, using placeholder
            const response = await api.get(`/filter_nodes/${user_id}`);
            tree_nodes.value = response.data;
            console.log("Library Subtopics: ", tree_nodes.value);
            isPendingLibrary.value = false;
        } catch (err: any) {
            errorLibrary.value = err.message;
            isPendingLibrary.value = false;
            console.log("Error: ", errorLibrary.value);
        }
    };

    const getEntitiesNames = async (user_id: string) => {
        errorLibrary.value = null;
        isPendingLibrary.value = true;
        try {
            // This endpoint might not exist in the new backend, using placeholder
            const response = await api.get(`/entities_names/${user_id}`);
            entities_names.value = response.data;
            console.log("getEntitiesNames -> entities length: ", entities_names.value.length);
            isPendingLibrary.value = false;
        } catch (err: any) {
            errorLibrary.value = err.message;
            isPendingLibrary.value = false;
            console.log("Error: ", errorLibrary.value);
        }
    };

    const deleteDocument = async (document_id: string) => {
        errorLibrary.value = null;
        isPendingLibrary.value = true;
        try {
            // Use the new DocumentService for deletion
            await documentService.deleteDocument(parseInt(document_id));
            console.log(`Document ${document_id} deleted successfully`);
            isPendingLibrary.value = false;
        } catch (err: any) {
            errorLibrary.value = err.message;
            isPendingLibrary.value = false;
            console.log("Error: ", errorLibrary.value);
        }       
    };

    // WebSocket setup
    const setupWebSocket = (user_id: string) => {
        const wsBaseUrl = import.meta.env.VITE_WS_BASE_URL || 'ws://localhost:8000';
        socket.value = new WebSocket(`${wsBaseUrl}/ws/${user_id}/app_documents`);
        
        socket.value.onopen = () => {
            console.log('WebSocket connection opened');
        };

        socket.value.onmessage = (event: any) => {
            const message = JSON.parse(event.data);
            if (message.type === 'document') {
                console.log('Got websocket message about documents');
                fetchDocuments(user_id).then(() => {
                    console.log('Websocket type document, getDocuments done');
                }).catch((error: any) => {
                    console.log('Websocket type document, getDocuments error: ', error);
                });
            }
            
            
        };

        socket.value.onclose = () => {
            console.log('WebSocket connection closed');
        };

        socket.value.onerror = (error: any) => {
            console.log('WebSocket error:', error);
        };
    };

    // Close WebSocket connection when the store is destroyed
    onUnmounted(() => {
        if (socket.value) {
            socket.value.close();
        }
    });

    const getDocuments = computed(() => {
        if (tree_selected_docs_ids.value.size > 0) {
            return docs.value.filter(doc => tree_selected_docs_ids.value.has(doc.id as string));
        }
        return docs.value;
    });

    const getTreeNodes = computed(() => {
        console.log("getTreeNodes -> tree_nodes: ", tree_nodes.value);
        return tree_nodes.value;
    });

    // Load docs and subtopics_nodes from local storage on store initialization
    loadFromLocalStorage();

    return {
        docs, docs_filtered, answer, answerResponse, resp_type, errorLibrary,
        isPendingLibrary, fetchDocuments, searchDocuments,
        getSubtopicsNodes, getEntitiesNames, deleteDocument,
        tree_nodes, tree_selected_docs_ids, entities_names, setupWebSocket,
        getDocuments, getTreeNodes
    };
});