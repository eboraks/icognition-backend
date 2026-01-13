// Get base URL based on user preference or fallback to staging
const getBaseUrl = async () => {
    try {
        const result = await chrome.storage.local.get(['backendEnvironment']);
        const environment = result.backendEnvironment || 'development';

        if (environment === 'development') {
            return 'http://localhost:8000';
        }
        return 'https://stg.api.icognition.ai';
    } catch (error) {
        console.error('Error getting base URL:', error);
        return 'http://localhost:8000'; // Default to development on error
    }
};

// Synchronous base URL for immediate use (will be updated asynchronously)
let base_url = import.meta.env.VITE_BASE_URL || 'http://localhost:8000';

// Update base_url asynchronously
getBaseUrl().then(url => {
    base_url = url;
    console.log('Base URL set to:', base_url);
});

const Endpoints = {
    bookmark: '/bookmark',
    document: '/bookmark/{ID}/document',
    entities: '/document_plus/{ID}'
}