/**
 * User Service
 * Handles all user-related API calls to the FastAPI backend
 */

import { api } from './httpClient';

// User Types (matching backend models)
export interface UserProfileResponse {
  id: number;
  firebase_uid: string;
  email: string;
  display_name?: string;
  photo_url?: string;
  is_active: boolean;
  is_verified: boolean;
  first_login?: string;
  last_login?: string;
  last_active?: string;
  created_at: string;
  updated_at: string;
  preferences?: Record<string, any>;
}

export interface UserProfileUpdateRequest {
  email?: string;
  display_name?: string;
  photo_url?: string;
  preferences?: Record<string, any>;
}

export interface UserActivityResponse {
  user_id: number;
  firebase_uid: string;
  last_active?: string;
  last_login?: string;
  first_login?: string;
  total_bookmarks: number;
  processed_bookmarks: number;
  pending_bookmarks: number;
}

export interface UserStatsResponse {
  user_id: number;
  firebase_uid: string;
  total_bookmarks: number;
  processed_bookmarks: number;
  pending_bookmarks: number;
  last_bookmark_date?: string;
  account_age_days?: number;
}

export interface UserListResponse {
  users: UserProfileResponse[];
  total: number;
  page: number;
  page_size: number;
  has_next: boolean;
  has_previous: boolean;
}

class UserService {
  /**
   * Get current user's profile information
   */
  async getUserProfile(): Promise<UserProfileResponse> {
    return api.get<UserProfileResponse>('/users/profile');
  }

  /**
   * Update current user's profile information
   */
  async updateUserProfile(data: UserProfileUpdateRequest): Promise<UserProfileResponse> {
    return api.put<UserProfileResponse>('/users/profile', data);
  }

  /**
   * Get current user's activity information
   */
  async getUserActivity(): Promise<UserActivityResponse> {
    return api.get<UserActivityResponse>('/users/activity');
  }

  /**
   * Get current user's statistics
   */
  async getUserStats(): Promise<UserStatsResponse> {
    return api.get<UserStatsResponse>('/users/stats');
  }

  /**
   * Refresh user's last active timestamp
   */
  async refreshUserActivity(): Promise<{ message: string }> {
    return api.post<{ message: string }>('/users/refresh-activity');
  }

  /**
   * Deactivate current user's account
   */
  async deactivateUserAccount(): Promise<{ message: string }> {
    return api.delete<{ message: string }>('/users/account');
  }

  /**
   * List all users (admin endpoint)
   * Note: This endpoint should be protected with admin authentication in production
   */
  async listUsersAdmin(params?: {
    page?: number;
    page_size?: number;
    active_only?: boolean;
  }): Promise<UserListResponse> {
    const queryParams = new URLSearchParams();
    
    if (params?.page) queryParams.append('page', params.page.toString());
    if (params?.page_size) queryParams.append('page_size', params.page_size.toString());
    if (params?.active_only !== undefined) queryParams.append('active_only', params.active_only.toString());
    
    const queryString = queryParams.toString();
    const url = queryString ? `/users/admin/list?${queryString}` : '/users/admin/list';
    
    return api.get<UserListResponse>(url);
  }
}

// Export singleton instance
export const userService = new UserService();
export default userService;
