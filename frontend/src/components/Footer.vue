<template>
  <footer class="sections bg-white m-auto border-top-2 border-300" id="footer" data-footer-sections="" style="height: 4.5em;">
    <section class="section">
      <div class="content-wrapper">
        <div class="content grid">
          <div class="block m-auto py-6 m-0 font-medium px-4 sm:px-0">
            <span class="text-black-alpha-90">© 2025<router-link to="/"> ICognition LLC</router-link></span>
            <span>&nbsp;<router-link to="terms-of-use">Terms of Use</router-link>&nbsp;|&nbsp;</span>
            <span><router-link to="privacy-policy">Privacy Policy</router-link></span>
          </div>
        </div>
      </div>
    </section>
  </footer>
</template>

<script lang="ts">
    export default {
        name: 'Footer'
    }
</script>