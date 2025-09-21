const TalkifyTTSService = {
    getTalkifyData() {
        return [];
    },
    getTalkifyTTSAPIKEY() {
        return Promise.resolve(import.meta.env.VITE_TALKIFY_TTS_API_KEY);
    },
    getTalkifyTTSHost() {
        return Promise.resolve(import.meta.env.VITE_TALKIFY_TTS_HOST);
    }
};

export default TalkifyTTSService;