import { Moment } from "moment";
import { Citation } from "./Citation.ts";

export class DocModel {
    id?: number;
    authors?: any[];
    title: string;
    url: string;
    aiMarkdownContent?: string;
    publicationDate?: Moment;
    status?: string;
    updatedAt?: Moment;
    oneSentenceSummary?: string;
    summary_citations?: [Citation];
    is_about?: string;
    image_url?: string;
    site_name?: string;
    source_type?: string;

    constructor(title: string, url: string, id?: number, updatedAt?: Moment) {
        this.title = title;
        this.url = url;
        this.id = id;
        this.updatedAt = updatedAt;
    }
}
