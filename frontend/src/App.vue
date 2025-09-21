<template>
  <div id="siteWrapper" class="clearfix site-wrapper surface-100">
    <Navbar />
    <router-view />
    <Footer />
  </div>
</template>

<script lang="ts">
  import Navbar from './components/Navbar.vue';
  import Footer from './components/Footer.vue';

  export default {
    name: 'app',
    components: {
      'Navbar': Navbar,
      'Footer': Footer,
    }
  };
</script>
