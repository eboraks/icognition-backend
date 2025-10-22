/**
 * Document Service
 * Handles all document-related API calls to the FastAPI backend
 */

import { api } from './httpClient';

// Document Types (matching backend models)
export interface DocumentCreateRequest {
  url?: string;
  title?: string;
  content?: string;
  content_type?: 'url' | 'html' | 'text';
  raw_html?: string; // Legacy field
}

export interface DocumentResponse {
  id: number;
  title: string;
  url?: string;
  content?: string;
  content_type: string;
  status: string;
  processing_status?: string;
  document_metadata?: Record<string, any>;
  created_at: string;
  updated_at: string;
  user_id: string;
  ai_is_about?: string;
  ai_bullet_points?: string[];
}

export interface DocumentListResponse {
  documents: DocumentResponse[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface DocumentUpdateRequest {
  title?: string;
  content?: string;
  content_type?: string;
}

export interface DocumentContentResponse {
  id: number;
  title: string;
  url?: string;
  content: string;
  content_type: string;
  status: string;
  document_metadata?: Record<string, any>;
}

export interface DocumentProcessingStatusResponse {
  id: number;
  status: string;
  processing_status?: string;
  updated_at: string;
}

export interface SimilarDocumentSearchRequest {
  query: string;
  limit?: number;
  similarity_threshold?: number;
}

export interface AnalysisRequest {
  analysis_type?: string;
}

export interface AnalysisResponse {
  message: string;
  document_id: number;
  analysis_type: string;
  task_id?: string;
  status: string;
}

export interface AnalysisReport {
  document_id: number;
  title: string;
  url?: string;
  status: string;
  analysis_report: Record<string, any>;
}

export interface EntityExtractionResponse {
  message: string;
  task_id: string;
  document_id: number;
  status: string;
}

export interface DocumentEntities {
  document_id: number;
  entities: Array<{
    id: number;
    name: string;
    type: string;
    description?: string;
    wikidata_id?: string;
    relevance: number;
  }>;
  count: number;
}

class DocumentService {
  /**
   * Create a new document from URL or content
   */
  async createDocument(data: DocumentCreateRequest): Promise<DocumentResponse> {
    return api.post<DocumentResponse>('/documents/', data);
  }

  /**
   * Get paginated list of user documents
   */
  async getDocuments(params?: {
    page?: number;
    page_size?: number;
    status?: string;
  }): Promise<DocumentListResponse> {
    const queryParams = new URLSearchParams();
    
    if (params?.page) queryParams.append('page', params.page.toString());
    if (params?.page_size) queryParams.append('page_size', params.page_size.toString());
    if (params?.status) queryParams.append('status', params.status);
    
    const queryString = queryParams.toString();
    const url = queryString ? `/documents/?${queryString}` : '/documents/';
    
    return api.get<DocumentListResponse>(url);
  }

  /**
   * Get a specific document by ID
   */
  async getDocument(documentId: number): Promise<DocumentResponse> {
    return api.get<DocumentResponse>(`/documents/${documentId}`);
  }

  /**
   * Update document metadata
   */
  async updateDocument(documentId: number, data: DocumentUpdateRequest): Promise<DocumentResponse> {
    return api.put<DocumentResponse>(`/documents/${documentId}`, data);
  }

  /**
   * Delete a document
   */
  async deleteDocument(documentId: number): Promise<void> {
    return api.delete<void>(`/documents/${documentId}`);
  }

  /**
   * Get documents by URL
   */
  async getDocumentsByUrl(url: string): Promise<DocumentResponse[]> {
    return api.get<DocumentResponse[]>(`/documents/url/${encodeURIComponent(url)}`);
  }

  /**
   * Get documents by status
   */
  async getDocumentsByStatus(status: string): Promise<DocumentResponse[]> {
    return api.get<DocumentResponse[]>(`/documents/status/${status}`);
  }

  /**
   * Get document content for analysis
   */
  async getDocumentContent(documentId: number): Promise<DocumentContentResponse> {
    return api.get<DocumentContentResponse>(`/documents/${documentId}/content`);
  }

  /**
   * Update document processing status
   */
  async updateDocumentStatus(documentId: number, status: string): Promise<DocumentProcessingStatusResponse> {
    return api.patch<DocumentProcessingStatusResponse>(`/documents/${documentId}/status`, { status });
  }

  /**
   * Manually trigger content fetching for an existing document
   */
  async fetchDocumentContent(documentId: number): Promise<DocumentResponse> {
    return api.post<DocumentResponse>(`/documents/${documentId}/fetch`);
  }

  /**
   * Generate embedding for a document
   */
  async generateDocumentEmbedding(documentId: number): Promise<DocumentResponse> {
    return api.post<DocumentResponse>(`/documents/${documentId}/embed`);
  }

  /**
   * Search for similar documents using vector similarity
   */
  async searchSimilarDocuments(params: SimilarDocumentSearchRequest): Promise<DocumentResponse[]> {
    return api.post<DocumentResponse[]>('/documents/search/similar', params);
  }

  /**
   * Update embeddings for multiple documents in batch
   */
  async batchUpdateEmbeddings(params?: {
    batch_size?: number;
    force_regenerate?: boolean;
  }): Promise<{ message: string; results: any }> {
    return api.post<{ message: string; results: any }>('/documents/batch/embeddings', params);
  }

  /**
   * Get statistics about document embeddings
   */
  async getEmbeddingStatistics(): Promise<any> {
    return api.get<any>('/documents/embeddings/stats');
  }

  /**
   * Manually trigger content validation for an existing document
   */
  async validateDocumentContent(documentId: number): Promise<DocumentResponse> {
    return api.post<DocumentResponse>(`/documents/${documentId}/validate`);
  }

  /**
   * Get detailed validation report for a document
   */
  async getDocumentValidationReport(documentId: number): Promise<any> {
    return api.get<any>(`/documents/${documentId}/validation-report`);
  }

  /**
   * Trigger content analysis for a document (background task)
   */
  async analyzeDocumentContent(documentId: number, analysisType: string = 'bullet_points'): Promise<AnalysisResponse> {
    return api.post<AnalysisResponse>(`/documents/${documentId}/analyze`, null, {
      params: { analysis_type: analysisType }
    });
  }

  /**
   * Get content analysis report for a document
   */
  async getDocumentAnalysisReport(documentId: number): Promise<AnalysisReport> {
    return api.get<AnalysisReport>(`/documents/${documentId}/analysis-report`);
  }

  /**
   * Trigger batch content analysis for multiple documents
   */
  async batchAnalyzeDocuments(params?: {
    document_ids?: number[];
    analysis_type?: string;
  }): Promise<AnalysisResponse> {
    return api.post<AnalysisResponse>('/documents/batch/analyze', params);
  }

  /**
   * Get all analysis tasks for the current user
   */
  async getAnalysisTasks(): Promise<{ tasks: any[]; total: number }> {
    return api.get<{ tasks: any[]; total: number }>('/documents/analysis/tasks');
  }

  /**
   * Get status of a specific analysis task
   */
  async getAnalysisTaskStatus(taskId: string): Promise<any> {
    return api.get<any>(`/documents/analysis/tasks/${taskId}`);
  }

  /**
   * Cancel a running analysis task
   */
  async cancelAnalysisTask(taskId: string): Promise<{ message: string }> {
    return api.delete<{ message: string }>(`/documents/analysis/tasks/${taskId}`);
  }

  /**
   * Get analysis task statistics
   */
  async getAnalysisStatistics(): Promise<any> {
    return api.get<any>('/documents/analysis/statistics');
  }

  /**
   * Extract entities from a document using Gemini AI
   */
  async extractDocumentEntities(documentId: number): Promise<EntityExtractionResponse> {
    return api.post<EntityExtractionResponse>(`/documents/${documentId}/extract-entities`);
  }

  /**
   * Get entities extracted from a document
   */
  async getDocumentEntities(documentId: number): Promise<DocumentEntities> {
    return api.get<DocumentEntities>(`/documents/${documentId}/entities`);
  }

  /**
   * Get status of an entity extraction task
   */
  async getEntityExtractionStatus(taskId: string): Promise<any> {
    return api.get<any>(`/documents/entity-extraction/${taskId}/status`);
  }
}

// Export singleton instance
export const documentService = new DocumentService();
export default documentService;
