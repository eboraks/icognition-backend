/// <reference types="vite/client" />

interface ImportMetaEnv {
    readonly VITE_JWT_SECRET: string;
    readonly VITE_APP_API_BASE_URL: string;
    readonly VITE_APP_FB_API_KEY: string;
    readonly VITE_WEBSOCKET_URL: string;
    readonly TALKIFY_TTS_API_KEY: string;
    readonly TALKIFY_TTS_HOST: string;
    readonly VITE_TESTING: string;
}

interface ImportMeta {
    readonly env: ImportMetaEnv;
}
