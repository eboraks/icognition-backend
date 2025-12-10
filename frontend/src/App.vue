<template>
  <div id="siteWrapper" class="clearfix site-wrapper surface-100">
    <Toast />
    <ConfirmDialog />
    <AppLayout />
  </div>
</template>

<script lang="ts">
  import AppLayout from './components/layout/AppLayout.vue';
  import Toast from 'primevue/toast';
  import ConfirmDialog from 'primevue/confirmdialog';

  export default {
    name: 'app',
    components: {
      'AppLayout': AppLayout,
      'Toast': Toast,
      'ConfirmDialog': ConfirmDialog,
    },
  };
</script>
