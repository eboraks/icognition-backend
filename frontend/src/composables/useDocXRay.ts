// Function that makes http request to get library data
import { ref } from 'vue';
import { DocModel } from '@/components/models/DocModel.ts';
import { documentService } from '@/services/DocumentService';

export function useDocXRay() {

    const original_elements = ref(null);
    const doc = ref<DocModel | null>(null);
    const error = ref(null);
    const xRayIsPending = ref(false);
    
    const getDocumetXRay = async (id: string) => {
        error.value = null;
        xRayIsPending.value = true;
        try {
            // Use the new DocumentService to get document details
            const results = await documentService.getDocument(parseInt(id));
            doc.value = results as DocModel;

            // Get document content for html_elements
            const contentResponse = await documentService.getDocumentContent(parseInt(id));
            
            // Check if html_elements is a string or an object. This is results from the API change of changing how the html_elements are stored. 
            if (typeof contentResponse.content === 'string') {
                try {
                    original_elements.value = JSON.parse(contentResponse.content);
                } catch {
                    // If parsing fails, create a simple structure
                    original_elements.value = [{
                        element: 'p',
                        text: contentResponse.content
                    }];
                }
            } else {
                original_elements.value = contentResponse.content;
            }    
            xRayIsPending.value = false;
        } catch (err: any) {
            console.error(err);
            error.value = err.message;
            xRayIsPending.value = false;
            console.log("Error: ", error.value);
        }
    }

    return { doc, original_elements, xRayIsPending, getDocumetXRay }
}
