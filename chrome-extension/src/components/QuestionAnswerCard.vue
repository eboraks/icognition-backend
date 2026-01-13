<template>
    <div class="chat-message">
        <!-- User Question -->
        <div id="question" class="flex align-items-end justify-content-end mb-2">
            <div class="bg-primary border-round px-3 py-2 shadow-1 max-w-25 relative">
                <p class="m-0 text-white pb-3">{{chat?.user_prompt}}</p>
                <small class="timestamp text-50">
                    {{moment(chat?.created_at).format('h:mm a')}}
                </small>
            </div>
        </div>
        
        <!-- AI Response -->
        <div class="flex align-items-start">
            <Avatar image="/icons/icog_action_icon_16x16.png" 
                   class="mr-2" 
                   :pt="{
                       root: { class: 'custom-avatar' }
                   }" 
                   size="small" 
                   shape="circle" />
            <div class="surface-card border-round px-3 py-2 shadow-1 max-w-25 relative fadein animation-duration-500">
                <div v-if="!chat?.response" class="skeleton-container">
                    <div class="skeleton-content">
                        <Skeleton width="100%" height="1.5rem" class="mb-3" />
                        <Skeleton width="90%" height="1.5rem" class="mb-3" />
                        <Skeleton width="95%" height="1.5rem" />
                    </div>
                </div>
                <div v-else>
                    <!-- Display response immediately without typing effect -->
                    <p v-if="is_answer_include_html" 
                       class="m-0 cursor-pointer" 
                       v-html="formattedResponse" 
                       @click="handleCitationClick"></p>
                    
                    <p v-else 
                       class="m-0 cursor-pointer"
                       @click="handleCitationClick">
                        {{formattedResponse}}
                        <i v-if="showError" class="pi pi-exclamation-circle text-red-500 ml-2" 
                           title="Citation not found in page"></i>
                    </p>
                    <small class="absolute bottom-0 right-0 text-500 p-1">
                        <i class="pi pi-times cursor-pointer" @click="handleQandARemove(uuid)"></i>
                    </small>
                </div>
            </div>
        </div>
    </div>
</template>

<script setup lang="js">
    import moment from 'moment';
    import { computed, ref } from 'vue';
    import Avatar from 'primevue/avatar';
    import Skeleton from 'primevue/skeleton';

    const props = defineProps({ 
        chat: { type: Object, required: true }, 
        uuid: { type: String, required: true }
    });
    
    // Computed function to format the response based on the new format
    const formattedResponse = computed(() => {
        if (!props.chat?.response) {
            console.log('QuestionAnswerCard -> No response in chat:', props.chat);
            return '';
        }
        
        try {
            console.log('QuestionAnswerCard -> Processing response:', props.chat.response);
            
            // If response is already an object, use it directly
            let parsedResponse = props.chat.response;
            
            // If it's a string, try to parse it
            if (typeof props.chat.response === 'string') {
                parsedResponse = JSON.parse(props.chat.response);
                console.log('QuestionAnswerCard -> Parsed string response:', parsedResponse);
            }
            
            // If parsedResponse itself is a string (double encoded), try parsing again
            if (typeof parsedResponse === 'string') {
                try {
                    parsedResponse = JSON.parse(parsedResponse);
                    console.log('QuestionAnswerCard -> Double parsed response:', parsedResponse);
                } catch (e) {
                    // If it fails, use the string as is
                    console.log('QuestionAnswerCard -> Using string response as is');
                    return parsedResponse;
                }
            }
            
            // Check if it has the new format with answer_for_chat
            if (parsedResponse.answer_for_chat) {
                console.log('QuestionAnswerCard -> Using answer_for_chat:', parsedResponse.answer_for_chat);
                return parsedResponse.answer_for_chat;
            }
            
            // If it has important_bullet_points, format them as a list
            if (parsedResponse.important_bullet_points && parsedResponse.important_bullet_points.length > 0) {
                const bulletPoints = parsedResponse.important_bullet_points
                    .map(point => `<li>${point}</li>`)
                    .join('');
                return `${parsedResponse.answer_for_chat || ''}<ul>${bulletPoints}</ul>`;
            }
            
            // Fallback to the original response
            console.log('QuestionAnswerCard -> Using fallback response');
            return typeof props.chat.response === 'string' 
                ? props.chat.response 
                : JSON.stringify(props.chat.response);
        } catch (e) {
            console.error('Error formatting response:', e, props.chat.response);
            // If it's not valid JSON, just return the original response
            return props.chat.response;
        }
    });
    
    //Computed function to format the answer, if the string include html tags then it will be rendered as html
    const is_answer_include_html = computed(() => {
        if (!formattedResponse.value) {
            return false;
        }
        
        // Check for common HTML tags or entities
        const htmlRegex = /<\/?(?:div|span|p|a|ul|ol|li|h[1-6]|br|hr|img|b|i|strong|em|table|tr|td|th|thead|tbody)(?:\s+[^>]*)?>/i;
        
        return htmlRegex.test(formattedResponse.value); 
    });

    const emit = defineEmits(['remove']);
    const handleQandARemove = (uuid) => {
        //call backend to remove the QandA and only then remove it from the UI
        console.log('Card -> Removing QandA:', uuid);

        emit('remove', uuid);
    }

    const showError = ref(false);

    const handleCitationClick = async () => {
        try {
            // Show loading state
            showError.value = false;
            const loadingIndicator = document.createElement('div');
            loadingIndicator.id = 'citation-loading';
            loadingIndicator.style.position = 'fixed';
            loadingIndicator.style.top = '10px';
            loadingIndicator.style.right = '10px';
            loadingIndicator.style.padding = '8px 12px';
            loadingIndicator.style.backgroundColor = 'rgba(0, 0, 0, 0.7)';
            loadingIndicator.style.color = 'white';
            loadingIndicator.style.borderRadius = '4px';
            loadingIndicator.style.zIndex = '9999';
            loadingIndicator.textContent = 'Finding citation...';
            document.body.appendChild(loadingIndicator);
            
            let verbatim = '';
            let allCitations = [];
            
            // Try to parse the response as JSON
            try {
                const parsedResponse = JSON.parse(props.chat.response);
                console.log('Parsed response for citations:', parsedResponse);
                
                // Check if we have citations in the new format
                if (parsedResponse.text_used_for_answer && parsedResponse.text_used_for_answer.length > 0) {
                    // Get all citations from the array
                    allCitations = parsedResponse.text_used_for_answer;
                    verbatim = allCitations[0];
                }
            } catch (e) {
                console.log('Failed to parse response as JSON, falling back to old format:', e);
            }
            
            // Fall back to the old format if we couldn't use the new format
            if (allCitations.length === 0 && props.chat.citations && props.chat.citations.length > 0) {
                props.chat.citations.forEach(citation => {
                    if (citation.verbatims && citation.verbatims.length > 0) {
                        citation.verbatims.forEach(v => {
                            if (v.verbatim_text) {
                                allCitations.push(v.verbatim_text);
                            }
                        });
                    }
                });
                
                if (allCitations.length > 0) {
                    verbatim = allCitations[0];
                }
            }
            
            if (!verbatim) {
                console.error('No citation text found');
                showError.value = true;
                
                // Show error notification
                const errorNotification = document.createElement('div');
                errorNotification.style.position = 'fixed';
                errorNotification.style.top = '10px';
                errorNotification.style.right = '10px';
                errorNotification.style.padding = '8px 12px';
                errorNotification.style.backgroundColor = 'rgba(220, 53, 69, 0.9)';
                errorNotification.style.color = 'white';
                errorNotification.style.borderRadius = '4px';
                errorNotification.style.zIndex = '9999';
                errorNotification.style.maxWidth = '80%';
                errorNotification.style.boxShadow = '0 2px 10px rgba(0,0,0,0.2)';
                
                // Create a container for the citation text
                const citationContainer = document.createElement('div');
                citationContainer.style.marginTop = '8px';
                citationContainer.style.padding = '8px';
                citationContainer.style.backgroundColor = 'rgba(255,255,255,0.9)';
                citationContainer.style.color = '#333';
                citationContainer.style.borderRadius = '4px';
                citationContainer.style.maxHeight = '150px';
                citationContainer.style.overflow = 'auto';
                citationContainer.style.fontSize = '14px';
                citationContainer.style.lineHeight = '1.4';
                citationContainer.textContent = verbatim;
                
                errorNotification.innerHTML = '<div>Citation not found in page. You can search for this text:</div>';
                errorNotification.appendChild(citationContainer);
                
                // Add a close button
                const closeButton = document.createElement('div');
                closeButton.innerHTML = '&times;';
                closeButton.style.position = 'absolute';
                closeButton.style.top = '8px';
                closeButton.style.right = '8px';
                closeButton.style.cursor = 'pointer';
                closeButton.style.fontSize = '16px';
                closeButton.style.fontWeight = 'bold';
                closeButton.onclick = () => document.body.removeChild(errorNotification);
                
                errorNotification.appendChild(closeButton);
                document.body.appendChild(errorNotification);
                
                // Auto-dismiss after 10 seconds
                setTimeout(() => {
                    if (document.body.contains(errorNotification)) {
                        document.body.removeChild(errorNotification);
                    }
                }, 10000);
            }
        } catch (error) {
            console.error('Error in handleCitationClick:', error);
            showError.value = true;
        } finally {
            // Remove loading indicator
            if (document.getElementById('citation-loading')) {
                document.body.removeChild(document.getElementById('citation-loading'));
            }
        }
    };
</script>

<style scoped>
.chat-message {
    margin-top: 1.5rem;
    margin-bottom: 1.5rem;
    margin-left: 0.5rem;
    margin-right: 1.5rem;
}

.max-w-25 {
    max-width: 85%;
}

/* Remove previous styles */
div[icon="pi pi-times"] {
    cursor: pointer;
    font-weight: bold;
    padding: 8px;
    transition: color 0.2s;
}

div[icon="pi pi-times"]:hover {
    color: #dc3545;
}

.content-wrapper {
    padding: 0.5rem;
    margin: 0;
}

.answer-text {
    margin: 0;
    line-height: 1.4;
}

/* Make sure the Card content has minimal padding */
:deep(.p-card-content) {
    padding: 0 !important;
}

.header-wrapper {
    padding: 0.5rem;
    margin: 0;
}

.header-text {
    margin: 0;
    padding: 0;
    line-height: 1.4;
}

/* Override PrimeVue's default header padding */
:deep(.p-card-header) {
    padding: 0 !important;
}

.timestamp {
    position: absolute;
    bottom: 2px;
    right: 8px;
    font-size: 0.75rem;
    line-height: 1;
}

/* Add padding to ensure text doesn't overlap with timestamp */
.chat-message p {
    padding-right: 3rem;
}

.cursor-pointer {
    cursor: pointer;
}

/* Update skeleton loading styles */
.skeleton-container {
    width: 100%;
    min-height: 120px;
    padding: 1rem 0;
}

.skeleton-content {
    width: 100%;
    min-width: 300px;
}

:deep(.p-skeleton) {
    background-color: var(--surface-200);
    border-radius: 4px;
    margin-bottom: 0.75rem;
    min-width: 250px;
}

:deep(.p-skeleton::after) {
    content: "";
    position: absolute;
    top: 0;
    right: 0;
    bottom: 0;
    left: 0;
    transform: translateX(-100%);
    background-image: linear-gradient(
        90deg,
        rgba(255, 255, 255, 0) 0,
        rgba(255, 255, 255, 0.2) 20%,
        rgba(255, 255, 255, 0.5) 60%,
        rgba(255, 255, 255, 0)
    );
    animation: shimmer 2s infinite;
}

@keyframes shimmer {
    100% {
        transform: translateX(100%);
    }
}

/* Add animation styles */
.fadein {
    animation: fadein 0.5s ease-in-out;
}

@keyframes fadein {
    from {
        opacity: 0;
        transform: translateY(10px);
    }
    to {
        opacity: 1;
        transform: translateY(0);
    }
}

/* Add Avatar custom styles */
:deep(.custom-avatar) {
    width: 20px !important;
    height: 20px !important;
    background-color: #f8f9fa;
    border: none;
    padding: 2px;
}

:deep(.custom-avatar img) {
    width: 16px !important;
    height: 16px !important;
    object-fit: contain !important;
    margin: 0 !important;
    padding: 0 !important;
}
</style>