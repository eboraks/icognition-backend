import { DocModel } from './DocModel.ts';

export class StudyCollection {
    id: string | undefined;
    name: string | null;
    description: string | null;
    ai_explanation: string | undefined;
    user_id: string;
    created_at: Date | undefined;
    related_docs: [DocModel] | undefined;

    constructor(name: string | null, description: string | null, user_id: string) {
        this.name = name;
        this.description = description;
        this.user_id = user_id;
    }
}