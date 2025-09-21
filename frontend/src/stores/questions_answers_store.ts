import { defineStore } from "pinia";
import { ref } from 'vue';
import { AskQuestionPayload } from "@/components/models/AskQuestion.ts";
import { api } from '@/services/httpClient';

interface QuestionAnswer {
    uuid: string;
    [key: string]: any;
}

const array_to_map = (array: QuestionAnswer[]): Map<string, QuestionAnswer> => {
    let map = new Map<string, QuestionAnswer>();
    array.forEach((item) => {
        map.set(item.uuid, item);
    });
    return map;
}

const askQuestion = async (askQuestionPayload: AskQuestionPayload): Promise<any> => {
    try {
        console.log("Asking question with payload:", JSON.stringify(askQuestionPayload));
        const response = await api.post('/ask_question', askQuestionPayload);
        return response.data;
    } catch (err) {
        throw Error(err as string);
    }
}

const getDocQuestionsAnswers = async (id: string) => {
    try {
        const response = await api.get(`/document/${id}/questions_answers`);
        let arr = response.data;
        let ma = array_to_map(arr);
        return ma;
    } catch (err) {
        console.error(err)
        throw Error(err as string);
    }
}

const delete_question_answer = async (uuid: string) => {
    try {
        await api.delete(`/question_answer/${uuid}`);
        return true;
    } catch (err) {
        throw Error(err as string);
    }
}

export const QuestionsAnswersStore = defineStore('qa_store', () => {

    const config = ref({ source_id: '', source_type: '', list: new Map() }); 


    const init = (source_id: string, source_type: string) => {
        config.value.source_id = source_id;
        config.value.source_type = source_type;
        console.log("IniConfig: ", config.value);
    }

    const getQuestionsAnswers = (uuid: string) => {
        return config.value.list.get(uuid);
    }

    const fetchQuestionsAnswers = async () => {
        try {
            console.log("Fetching questions and answers: ", config.value);
            const response = await getDocQuestionsAnswers(config.value.source_id);
            config.value.list = response;
        } catch (err) {
            console.error(err);
        }
    }

    const delete_question = async (uuid: string) => {

        try {

            const response = await delete_question_answer(uuid);
            console.log("Delete Response: ", response);
            if (response) {
                config.value.list.delete(uuid);
            }
        } catch(err) {
            console.error(err);
        }
    }

    const addQuestion = async (question: string) => {

        let qa = {question: question,}
        let key = 'temp_key';

        config.value.list.set(key, qa);
        console.log("Adding Question Answer: ", qa.question);
        const payload = new AskQuestionPayload(question, config.value.source_id, null);
        try {
            const response = await askQuestion(payload);
            console.log("Response: ", response);
            config.value.list.delete(key);
            config.value.list.set(response.uuid, response);
        } catch (err) {
            console.error("AddQuestion, error", err);
        }

    }
    return {
        config,
        init,
        fetchQuestionsAnswers,
        addQuestion,
        getQuestionsAnswers, 
        delete_question
    }

});