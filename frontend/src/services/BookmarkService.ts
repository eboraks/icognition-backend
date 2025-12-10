/**
 * Bookmark Service
 * Handles all bookmark-related API calls to the FastAPI backend
 */

import { api } from './httpClient.js';

// Bookmark Types (matching backend models)
export interface BookmarkCreateRequest {
  url: string;
  title: string;
  description?: string;
  content?: string;
  metadata?: Record<string, any>;
}

export interface BookmarkUpdateRequest {
  title?: string;
  description?: string;
  content?: string;
  metadata?: Record<string, any>;
}

export interface BookmarkResponse {
  id: number;
  url: string;
  title: string;
  description?: string;
  content?: string;
  bookmark_metadata?: Record<string, any>;
  is_processed: boolean;
  processing_status?: string;
  created_at?: string;
  updated_at?: string;
  user_id: string;
}

export interface BookmarkListResponse {
  bookmarks: BookmarkResponse[];
  total: number;
  page: number;
  page_size: number;
  has_next: boolean;
  has_previous: boolean;
}

class BookmarkService {
  /**
   * Create a bookmark with full document processing workflow.
   * This extracts content from the URL and triggers background processing.
   * Use this for URLs that should be analyzed and processed.
   */
  async createBookmark(data: BookmarkCreateRequest): Promise<BookmarkResponse> {
    return api.post<BookmarkResponse>('/bookmarks/', data);
  }

  /**
   * Get current user's bookmarks with pagination
   */
  async getUserBookmarks(params?: {
    page?: number;
    page_size?: number;
    is_processed?: boolean;
  }): Promise<BookmarkListResponse> {
    const queryParams = new URLSearchParams();
    
    if (params?.page) queryParams.append('page', params.page.toString());
    if (params?.page_size) queryParams.append('page_size', params.page_size.toString());
    if (params?.is_processed !== undefined) queryParams.append('is_processed', params.is_processed.toString());
    
    const queryString = queryParams.toString();
    const url = queryString ? `/bookmarks/?${queryString}` : '/bookmarks/';
    
    return api.get<BookmarkListResponse>(url);
  }

  /**
   * Get a specific bookmark by ID
   */
  async getBookmark(bookmarkId: number): Promise<BookmarkResponse> {
    return api.get<BookmarkResponse>(`/bookmarks/${bookmarkId}`);
  }

  /**
   * Update a specific bookmark
   */
  async updateBookmark(bookmarkId: number, data: BookmarkUpdateRequest): Promise<BookmarkResponse> {
    return api.put<BookmarkResponse>(`/bookmarks/${bookmarkId}`, data);
  }

  /**
   * Delete a specific bookmark
   */
  async deleteBookmark(bookmarkId: number): Promise<{ message: string }> {
    return api.delete<{ message: string }>(`/bookmarks/${bookmarkId}`);
  }

  /**
   * Get bookmarks by URL for current user
   */
  async getBookmarksByUrl(url: string): Promise<{ bookmarks: BookmarkResponse[]; count: number }> {
    return api.get<{ bookmarks: BookmarkResponse[]; count: number }>(`/bookmarks/url/${encodeURIComponent(url)}`);
  }

  /**
   * Find bookmark by document ID
   * Fetches user bookmarks and filters by document_id client-side
   */
  async findBookmarkByDocumentId(documentId: number): Promise<BookmarkResponse | null> {
    try {
      const response = await this.getUserBookmarks({ page_size: 100 });
      const bookmark = response.bookmarks.find(b => b.document_id === documentId);
      return bookmark || null;
    } catch (error) {
      console.error('Error finding bookmark by document ID:', error);
      return null;
    }
  }
}

// Export singleton instance
export const bookmarkService = new BookmarkService();
export default bookmarkService;
