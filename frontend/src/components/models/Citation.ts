import { VerbatimText } from './VerbatimText.ts';
export class Citation {
    id: number;
    text_reference: VerbatimText[] | null;
    document_id: string | null;
    document_title: string | undefined;
    task_id: number | null;
    created_at: Date | undefined;
    verbatim_text: string | undefined;
    verbatims?: VerbatimText[];

    constructor(id: number, text_reference: VerbatimText[] | null, document_id: string, task_id: number | null) {
        this.id = id;
        this.text_reference = text_reference;
        this.document_id = document_id;
        this.task_id = task_id;
    }
}