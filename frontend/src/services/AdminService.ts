/**
 * Admin Service
 * Handles all admin-related API calls to the FastAPI backend
 */

import { api } from './httpClient';

export interface PromptResponse {
  id: number;
  prompt_type: string;
  version: number;
  content: string;
  description?: string;
  is_active: boolean;
  created_by?: string;
  created_at: string;
  updated_at: string;
}

export interface PromptCreate {
  prompt_type: string;
  content: string;
  description?: string;
}

export interface PromptUpdate {
  content: string;
  description?: string;
}

class AdminService {
  /**
   * List all prompts
   */
  async listPrompts(params?: {
    prompt_type?: string;
    include_inactive?: boolean;
    limit?: number;
    offset?: number;
  }): Promise<PromptResponse[]> {
    const queryParams = new URLSearchParams();
    
    if (params?.prompt_type) queryParams.append('prompt_type', params.prompt_type);
    if (params?.include_inactive !== undefined) queryParams.append('include_inactive', params.include_inactive.toString());
    if (params?.limit) queryParams.append('limit', params.limit.toString());
    if (params?.offset) queryParams.append('offset', params.offset.toString());
    
    const queryString = queryParams.toString();
    const url = queryString ? `/api/admin/prompts?${queryString}` : '/api/admin/prompts';
    
    return api.get<PromptResponse[]>(url);
  }

  /**
   * Get prompts by type
   */
  async getPromptsByType(
    promptType: string,
    includeInactive: boolean = false
  ): Promise<PromptResponse[]> {
    const queryParams = new URLSearchParams();
    if (includeInactive) queryParams.append('include_inactive', 'true');
    
    const queryString = queryParams.toString();
    const url = queryString 
      ? `/api/admin/prompts/${promptType}?${queryString}`
      : `/api/admin/prompts/${promptType}`;
    
    return api.get<PromptResponse[]>(url);
  }

  /**
   * Get latest prompt for a type
   */
  async getLatestPrompt(promptType: string): Promise<PromptResponse> {
    return api.get<PromptResponse>(`/api/admin/prompts/${promptType}/latest`);
  }

  /**
   * Get prompt version history
   */
  async getPromptHistory(promptType: string): Promise<PromptResponse[]> {
    return api.get<PromptResponse[]>(`/api/admin/prompts/${promptType}/history`);
  }

  /**
   * Create a new prompt version
   */
  async createPrompt(data: PromptCreate): Promise<PromptResponse> {
    return api.post<PromptResponse>('/api/admin/prompts', data);
  }

  /**
   * Update a prompt (creates new version)
   */
  async updatePrompt(promptId: number, data: PromptUpdate): Promise<PromptResponse> {
    return api.put<PromptResponse>(`/api/admin/prompts/${promptId}`, data);
  }

  /**
   * Soft delete a prompt
   */
  async deletePrompt(promptId: number): Promise<void> {
    return api.delete(`/api/admin/prompts/${promptId}`);
  }
}

// Export singleton instance
export const adminService = new AdminService();
export default adminService;

