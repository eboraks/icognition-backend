import { defineEmits } from 'vue';

export function useSockets() {
    let socket;

    const socketSetup = async (user_id: string) => {
        const emit = defineEmits({
            'pullDocuments': null
        });
        socket = new WebSocket('http://localhost:8889/' + user_id);
    }

    return {
        socketSetup, socket
    }
}
