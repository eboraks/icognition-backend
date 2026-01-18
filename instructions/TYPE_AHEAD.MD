# Implementation Guide: Gmail-Style Ghost Text Type-Ahead

## 1. Overview
The goal is to implement an inline "ghost text" suggestion. This requires two overlapping layers: a background layer showing the suggestion and a foreground transparent layer for user input.

## 2. Vue.js Component (Frontend)
This component uses a **Debounce** mechanism to ensure the backend API is only called after the user stops typing for 300ms.

```vue
<template>
  <div class="typeahead-container">
    <div class="layer ghost-layer">
      <span class="invisible">{{ currentInput }}</span>
      <span class="suggestion-text">{{ suggestion }}</span>
    </div>

    <textarea
      ref="inputField"
      v-model="currentInput"
      @input="onInput"
      @keydown.tab.prevent="acceptSuggestion"
      class="layer input-layer"
      spellcheck="false"
    ></textarea>
  </div>
</template>

<script setup>
import { ref } from 'vue';

const currentInput = ref('');
const suggestion = ref('');
let debounceTimer = null;

/**
 * The Debounce Logic: 
 * Clears the previous timer on every keystroke. 
 * Only executes fetchSuggestion if 300ms pass without a new keystroke.
 */
const onInput = () => {
  suggestion.value = ''; // Clear suggestion while typing
  clearTimeout(debounceTimer);
  
  if (currentInput.value.length > 2) {
    debounceTimer = setTimeout(() => {
      fetchSuggestion();
    }, 300); 
  }
};

const fetchSuggestion = async () => {
  try {
    const response = await fetch(`http://localhost:8000/suggest?text=${encodeURIComponent(currentInput.value)}`);
    const data = await response.json();
    suggestion.value = data.prediction;
  } catch (err) {
    console.error("Type-ahead error:", err);
  }
};

const acceptSuggestion = () => {
  if (suggestion.value) {
    currentInput.value += suggestion.value;
    suggestion.value = '';
  }
};
</script>

<style scoped>
.typeahead-container {
  position: relative;
  width: 100%;
  height: 200px;
  font-family: 'Courier New', Courier, monospace; /* Monospace ensures char-width alignment */
  font-size: 16px;
}

.layer {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  padding: 12px;
  margin: 0;
  border: 1px solid #ddd;
  line-height: 1.5;
  white-space: pre-wrap;
  word-wrap: break-word;
  box-sizing: border-box;
}

.input-layer {
  background: transparent;
  z-index: 2;
  color: rgba(0,0,0,0.9);
  caret-color: black;
  resize: none;
}

.ghost-layer {
  z-index: 1;
  color: transparent; /* Hide the duplicate of what user typed */
  background: white;
  pointer-events: none;
}

.invisible {
  visibility: hidden;
}

.suggestion-text {
  color: #a0a0a0; /* Gray ghost text */
}
</style>



Backend API:

model = genai.GenerativeModel('gemini-2.5-flash-lite')

@app.get("/suggest")
async def get_suggestion(text: str):
    if not text:
        return {"prediction": ""}

    # Strictly instruct Gemini to provide only the completion
    prompt = (
        f"You are a text completion engine. Continue the text: '{text}'. "
        "Provide only the missing characters or words to complete the thought. "
        "Do not repeat the input. Do not explain yourself."
    )
    
    response = model.generate_content(
        prompt,
        generation_config=genai.types.GenerationConfig(
            max_output_tokens=10,
            temperature=0.0, # Zero temperature for deterministic results
        )
    )
    
    return {"prediction": response.text.strip()}