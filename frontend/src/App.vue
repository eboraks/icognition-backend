<template>
  <div id="siteWrapper" class="clearfix site-wrapper surface-100">
    <AppLayout />
  </div>
</template>

<script lang="ts">
  import AppLayout from './components/layout/AppLayout.vue';

  export default {
    name: 'app',
    components: {
      'AppLayout': AppLayout,
    },
  };
</script>
