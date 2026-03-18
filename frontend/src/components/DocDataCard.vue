<template>
    <div class="grid nested-grid border-round border-1 border-primary-100 m-1 shadow-2 w-full">
        <div class="col-12">
            <div class="grid">
                <div class="col-12 align-items-center justify-content-start border-bottom-1 border-200">
                    <h3><a class="text-xl text-color" :href="doc.url" style="text-decoration: none" target="_blank">{{ doc.title }}</a></h3>
                </div>
                <div class="col-3 overflow-hidden">
                    <p><a href="{{doc.url}}" target="_blank">{{ doc.site_name }}</a></p>
                    <p class="text-sm text-color my-1">Saved on: {{ formate_date }}</p>
                </div>
                <div class="col-7">
                    <p class="m-0">{{ doc.is_about }}</p>
                </div>
                <div class="col-2">
                    <a
                        @click="navigateToDocChat(doc)"
                        class="border-primary border-round mt-2 border-solid surface-border border-1 p-2 text-white bg-blue-600 w-full cursor-pointer">Open Chat
                    </a>
                    <button type="button" class="border-primary border-round mt-2 border-solid surface-border border-1 p-2 text-white surface-400 w-full" @click="handleRemoveClick">Remove</button>
                </div>
                <!-- <div class="col-12">
                    <label class="text-primary-500 underline" @click="showmore = !showmore">{{ showmore_text }}</label>
                    <div v-if="showmore" class="m-2">
                        <h3>Key Points</h3>
                        <ul class="m-0" v-if="showmore" v-for="(item, index) in doc.tldr" :key="index">
                            <li class="m-2">{{ item }}</li>
                        </ul>
                        <h3>Concepts, Ideas and Entities</h3>
                        <ul class="m-0" v-if="showmore" v-for="entity in doc.entities_and_concepts">
                            <li class="m-2">{{ entity.name }} ({{ entity.type }}) - {{ entity.description }}</li>
                        </ul>
                    </div>
                </div> -->
            </div>
        </div>
        <!-- <div class="col-3">
            <div class="text-center">
                <img :src="image_url" :alt="doc.title" class="max-w-full h-full" style="max-height: 175px;">
            </div>
        </div> -->
    </div>

</template>
<script setup lang="ts">
    import { ref, computed} from 'vue';
    import { useRouter } from 'vue-router';
    import { DocModel } from './models/DocModel.js';
    import { useChatStore } from '../stores/chat_store.js';
    import moment from 'moment';

    const router = useRouter();
    const chatStore = useChatStore();
    const showmore = ref(false);

    const props = defineProps<{
        doc: DocModel | any
    }>();

    const navigateToDocChat = async (doc: any) => {
        const session = await chatStore.getOrCreateDocumentSession(doc.id, doc.title);
        if (session) {
            router.push({ name: 'chats', params: { id: session.id } });
        }
    };

    const showmore_text = computed(() => {
        return showmore.value ? 'Less Details' : 'More Details';
    });

    const formate_date = computed(() => {
        return moment(props.doc.updatedAt).locale();
    });

    const handleRemoveClick = async () => {
        try {
            console.log('Remove ' + props.doc.id);
        } catch (error: any) {
            console.log(error.value)
        }
    }
</script>
