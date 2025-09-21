export class AskQuestionPayload {
    question: string;
    document_id: string | null;
    collection_id: string | null;
    
    constructor(question: string, document_id: string | null, collection_id: string | null) {
        this.question = question;
        this.document_id = document_id;
        this.collection_id = collection_id;
    }
}