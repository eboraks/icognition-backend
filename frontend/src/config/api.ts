/**
 * API Configuration
 * Centralized configuration for API endpoints and settings
 */

// API Configuration
export const API_CONFIG = {
  // Base URL for the FastAPI backend
  BASE_URL: import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000',
  
  // Timeout settings
  TIMEOUT: 30000, // 30 seconds
  
  // Retry configuration
  MAX_RETRIES: 3,
  RETRY_DELAY: 1000, // 1 second
  
  // Request/Response settings
  DEFAULT_HEADERS: {
    'Content-Type': 'application/json',
    'Accept': 'application/json',
  },
  
  // Pagination defaults
  DEFAULT_PAGE_SIZE: 20,
  MAX_PAGE_SIZE: 100,
};

// Environment configuration
export const ENV_CONFIG = {
  IS_DEVELOPMENT: import.meta.env.DEV,
  IS_PRODUCTION: import.meta.env.PROD,
  DEBUG: import.meta.env.VITE_DEBUG === 'true',
};

// WebSocket configuration
export const WS_CONFIG = {
  BASE_URL: import.meta.env.VITE_WS_BASE_URL || 'ws://localhost:8000',
  RECONNECT_INTERVAL: 5000, // 5 seconds
  MAX_RECONNECT_ATTEMPTS: 5,
};

export default API_CONFIG;
