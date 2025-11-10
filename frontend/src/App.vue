<template>
  <div id="siteWrapper" class="clearfix site-wrapper surface-100">
    <!-- Use AppLayout for app routes, Navbar/Footer for website routes -->
    <template v-if="isAppRoute">
      <AppLayout />
    </template>
    <template v-else>
      <Navbar />
      <router-view />
      <Footer />
    </template>
  </div>
</template>

<script lang="ts">
  import { computed } from 'vue';
  import { useRoute } from 'vue-router';
  import Navbar from './components/Navbar.vue';
  import Footer from './components/Footer.vue';
  import AppLayout from './components/layout/AppLayout.vue';

  export default {
    name: 'app',
    components: {
      'Navbar': Navbar,
      'Footer': Footer,
      'AppLayout': AppLayout,
    },
    setup() {
      const route = useRoute();
      const appRoutes = ['library', 'learning-qa', 'knowledge-explorer', 'docxray'];
      const isAppRoute = computed(() => {
        return route.name && appRoutes.includes(route.name as string);
      });
      return { isAppRoute };
    }
  };
</script>
