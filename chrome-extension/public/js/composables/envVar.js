// Use environment variable with fallback to staging
const base_url = import.meta.env.VITE_BASE_URL || 'https://stg.api.icognition.ai'

const Endpoints = {
    bookmark: '/bookmark',
    document: '/bookmark/{ID}/document',
    entities: '/document_plus/{ID}'
}