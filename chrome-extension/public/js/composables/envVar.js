// Get base URL based on user preference or fallback to staging
const getBaseUrl = async () => {
    try {
        const result = await chrome.storage.local.get(['backendEnvironment']);
        const environment = result.backendEnvironment || 'staging';
        
        if (environment === 'development') {
            return 'http://localhost:8000';
        }
        return 'https://stg.api.icognition.ai';
    } catch (error) {
        console.error('Error getting base URL:', error);
        return 'https://stg.api.icognition.ai'; // Default to staging on error
    }
};

// Synchronous base URL for immediate use (will be updated asynchronously)
let base_url = 'https://stg.api.icognition.ai'; // Default to staging

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