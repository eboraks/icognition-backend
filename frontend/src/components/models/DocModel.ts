import { Moment } from "moment";
import { Citation } from "./Citation.ts";

export class DocModel {
    id?: string;
    authors?: any[];
    title: string;
    url: string;
    tldr?: [string];
    publicationDate?: Moment;
    llmServiceMeta?: Object;
    status?: string;
    updateAt?: Moment;
    oneSentenceSummary?: string;
    summary_citations?: [Citation];
    is_about?: string;
    entities_and_concepts?: [Object];
    cosine_similarity?: number;
    image_url?: string;
    site_name?: string;
    html_elements?: [Object];
    source_type?: string;

    constructor(title: string, url: string, id?: string, updateAt?: Moment) {
        this.title = title;
        this.url = url;
        this.id = id;
        this.updateAt = updateAt;
    }
}
