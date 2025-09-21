// Function that makes http request to get library data
import { ref } from 'vue';
import { AskQuestionAnswerModel } from '@/components/models/AskQuestionAnswerModel.ts';
import { api } from '@/services/httpClient';

export function useDocQuesAnswers() {

    const qas = ref<AskQuestionAnswerModel[]>([]);
    const error = ref(null);
    const qasPending = ref(false);
    
    const getDocQuestionsAnswers = async (id: string) => {
        error.value = null;
        qasPending.value = true;
        try {
            // Use the new API client to make the request
            const response = await api.get(`/document/${id}/questions_answers`);
            qas.value = response.data;
            qasPending.value = false;
        } catch (err: any) {
            console.error(err)
            error.value = err.message;
            qasPending.value = false;
            console.log("Error: ", error.value);
        }
    }

    return { qas, qasPending, getDocQuestionsAnswers }    

}
