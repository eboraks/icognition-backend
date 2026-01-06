/**
 * HTTP Client Service
 * Centralized Axios configuration for API calls to the FastAPI backend
 */

import axios, { AxiosInstance, InternalAxiosRequestConfig, AxiosResponse, AxiosError, AxiosRequestConfig } from 'axios';
import { getAuth } from 'firebase/auth';
import { API_CONFIG } from '../config/api.js';

// Create Axios instance with configuration
const httpClient: AxiosInstance = axios.create({
  baseURL: API_CONFIG.BASE_URL,
  timeout: API_CONFIG.TIMEOUT,
  headers: API_CONFIG.DEFAULT_HEADERS,
});

// Request interceptor to add authentication headers
httpClient.interceptors.request.use(
  async (config: InternalAxiosRequestConfig) => {
    try {
      // Get Firebase auth token
      const auth = getAuth();
      const user = auth.currentUser;

      if (user) {
        const token = await user.getIdToken();
        config.headers = config.headers || {};
        config.headers.Authorization = `Bearer ${token}`;
      }
    } catch (error) {
      console.warn('Failed to get auth token:', error);
    }

    return config;
  },
  (error: AxiosError) => {
    return Promise.reject(error);
  }
);

// Response interceptor for error handling and retry logic
httpClient.interceptors.response.use(
  (response: AxiosResponse) => {
    return response;
  },
  async (error: AxiosError) => {
    const config = error.config as InternalAxiosRequestConfig & { _retry?: boolean; _retryCount?: number };

    // Retry logic for network errors
    if (!error.response && !config._retry && (config._retryCount || 0) < API_CONFIG.MAX_RETRIES) {
      config._retry = true;
      config._retryCount = (config._retryCount || 0) + 1;

      console.warn(`Retrying request (attempt ${config._retryCount}/${API_CONFIG.MAX_RETRIES})`);

      // Wait before retrying
      await new Promise(resolve => setTimeout(resolve, API_CONFIG.RETRY_DELAY));

      return httpClient(config);
    }

    // Handle common error cases
    if (error.response) {
      // Server responded with error status
      const { status, data } = error.response;

      switch (status) {
        case 401:
          console.error('Unauthorized - please log in again');
          // TODO: Redirect to login or refresh token
          break;
        case 403:
          console.error('Forbidden - insufficient permissions');
          break;
        case 404:
          console.error('Resource not found');
          break;
        case 422:
          console.error('Validation error:', data);
          break;
        case 500:
          console.error('Internal server error');
          break;
        default:
          console.error(`API Error ${status}:`, data);
      }
    } else if (error.request) {
      // Network error
      console.error('Network error - please check your connection');
    } else {
      // Other error
      console.error('Request setup error:', error.message);
    }

    return Promise.reject(error);
  }
);

// Generic API methods
export const api = {
  // GET request
  get: async <T>(url: string, config?: AxiosRequestConfig): Promise<T> => {
    const response = await httpClient.get<T>(url, config);
    return response.data;
  },

  // POST request
  post: async <T>(url: string, data?: any, config?: AxiosRequestConfig): Promise<T> => {
    const response = await httpClient.post<T>(url, data, config);
    return response.data;
  },

  // PUT request
  put: async <T>(url: string, data?: any, config?: AxiosRequestConfig): Promise<T> => {
    const response = await httpClient.put<T>(url, data, config);
    return response.data;
  },

  // PATCH request
  patch: async <T>(url: string, data?: any, config?: AxiosRequestConfig): Promise<T> => {
    const response = await httpClient.patch<T>(url, data, config);
    return response.data;
  },

  // DELETE request
  delete: async <T>(url: string, config?: AxiosRequestConfig): Promise<T> => {
    const response = await httpClient.delete<T>(url, config);
    return response.data;
  },
};

export default httpClient;
