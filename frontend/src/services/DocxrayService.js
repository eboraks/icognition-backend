import { documentService } from './DocumentService';

const DocxrayService = {
    async getCitationsData(documentId) {
        try {
            // Get document entities for citations
            const entitiesResponse = await documentService.getDocumentEntities(documentId);
            const entities = entitiesResponse.entities;
            
            // Convert entities to citation format
            return entities.map((entity, index) => ({
                id: `100${index}`,
                color: 'rgba(0,170,255,.15)',
                char_count: entity.name.length,
                highlight: entity.description || entity.name,
                note: `Entity: ${entity.name} (${entity.type})`,
                start_highlight: 0
            }));
        } catch (error) {
            console.error('Error fetching citations data:', error);
            // Return fallback data
            return [{
                id: '1000',
                color: 'rgba(0,170,255,.15)',
                char_count: 5,
                highlight: 'No citations available',
                note: 'Unable to load citations data',
                start_highlight: 0
            }];
        }
    },

    async getHighlightsData(documentId) {
        try {
            // Get document content for highlights
            const contentResponse = await documentService.getDocumentContent(documentId);
            const content = contentResponse.content;
            
            if (!content) {
                return [{
                    id: '1000',
                    color: 'rgba(0,170,255,.15)',
                    char_count: 5,
                    highlight: 'No content available for highlighting',
                    note: 'Document has no content',
                    start_highlight: 0
                }];
            }
            
            // Simple text highlighting (split by sentences)
            const sentences = content.split(/[.!?]+/).filter(s => s.trim().length > 10);
            const highlights = sentences.slice(0, 4).map((sentence, index) => ({
                id: `100${index}`,
                color: 'rgba(0,170,255,.15)',
                char_count: sentence.trim().length,
                highlight: sentence.trim(),
                note: `Highlight ${index + 1}`,
                start_highlight: content.indexOf(sentence.trim())
            }));
            
            return highlights;
        } catch (error) {
            console.error('Error fetching highlights data:', error);
            // Return fallback data
            return [{
                id: '1000',
                color: 'rgba(0,170,255,.15)',
                char_count: 5,
                highlight: 'No highlights available',
                note: 'Unable to load highlights data',
                start_highlight: 0
            }];
        }
    },

    async getHighlights(documentId) {
        return await this.getHighlightsData(documentId);
    },
    async getCitations(documentId) {
        return await this.getCitationsData(documentId);
    }
};

export default DocxrayService;