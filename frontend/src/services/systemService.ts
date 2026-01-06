import axios from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

export const systemService = {
    async getAuthStatus() {
        try {
            const response = await axios.get(`${API_BASE_URL}/api/v1/system/auth-status`);
            return response.data;
        } catch (error) {
            console.error('Failed to fetch auth status:', error);
            return { disable_auth: false };
        }
    }
};
