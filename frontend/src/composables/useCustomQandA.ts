// Function that makes http request to get library data
import { ref } from 'vue';
import { AskQuestionPayload } from '@/components/models/AskQuestion.ts';
import { AskQuestionAnswerModel } from '@/components/models/AskQuestionAnswerModel.ts';
import { AskQuestionAnswerInterface } from '@/components/models/AskQuestionAnswerInterface.ts';
import { api } from '@/services/httpClient';

export function useCustomQandA() {

    const answerResponse = ref<AskQuestionAnswerInterface>();
    const error = ref(null);
    const isAskPending = ref(true);
    
    const askQuestion = async (askQuestionPayload: any) => {
        error.value = null;
        isAskPending.value = true;
        try {
            console.log("Asking question with payload:", JSON.stringify(askQuestionPayload));
            
            // Use the new API client to make the request
            const response = await api.post('/ask_question', askQuestionPayload);
            answerResponse.value = response.data;
            isAskPending.value = false;
        } catch (err: any) {
            console.error(err)
            error.value = err.message;
            isAskPending.value = false;
            console.log("Error: ", error.value);
        }
    }
    return { answerResponse, isAskPending, askQuestion }    
}
