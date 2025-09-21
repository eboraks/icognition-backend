<template>
    <div v-if="props.answer" class="border-round border-1 border-primary-500 mt-1 shadow-2 m-1" style="width: 98%;">
        <div class="line-height-2 p-1 m-1"><span  v-html="props.answer"></span></div>
    </div>
</template>
<script setup lang="ts">
    import { ref, computed, onUpdated } from 'vue';
    const typeValue = ref('');

    // props
    export interface AnswerProps {
        answer?: String;
    }
    const props = withDefaults(defineProps<AnswerProps>(), {
        answer: String
    });

    onUpdated(() => {
        console.log("Answer: ", props.answer);
        if (typeValue.value.length < 1 && props.answer !== undefined) {
            typeEffect();
        }
    });

    const formatedAnswer = computed(() => {
        return props.answer.replace(/^\s*["']|["']\s*$/g, '').replace(/\n/g, '<br />');
    });

    const typeEffect = () => {
    
        if (typeValue.value.length < props.answer.length) {
            typeValue.value += props.answer.charAt(typeValue.value.length);

            //Sleep longer between words
            if (typeValue.value.endsWith(' ')) {
                setTimeout(typeEffect, 100);
            } else {
                setTimeout(typeEffect, 35);
            }
            
        } 
    }
</script>
<style>

     
</style>