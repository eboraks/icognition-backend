import { AskQuestionAnswerInterface } from "./AskQuestionAnswerInterface.ts";
import { Moment } from "moment";
import { Citation } from "./Citation.ts";

export class AskQuestionAnswerModel {
    uuid?: string;
    created_at?: Moment;
    status?: string;
    question?: string;
    answer?: string;
    source_doc_id?: string;
    source_collection_id?: string;
    documents_used?: [string];
    citations?: Citation[];
    llm_service_meta?: Object;
}