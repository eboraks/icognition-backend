<script>
import Popup from './components/Popup.vue'

console.log('App.vue loaded');

export default {
  name: 'App',
  components: {
    Popup
  },
  mounted() {
    console.log('App.vue mounted');
  }
}
</script>

<template>
  <Popup></Popup>
</template>

<style scoped>
/* No specific styles needed */
</style>
