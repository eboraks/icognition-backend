<template>
  <div class="home-view-content">
    <section class="section bg-white md:px-8 xs:px-4 sm:py-6">
      <div class="content-wrapper">
        <div class="content grid nested-grid sm:px-6">
          <div class="col-12 lg:col-6">
            <div class="grid">
              <div class="col-12 pb-5">
                <div class="flex flex-column justify-content-center">
                  <div class="text-2xl text-black-alpha-80 font-bold line-height-2">
                    <h2 class="line-height-1">For people with dyslexia, iCognition changes the rules of the game.</h2>
                  </div>
                </div>
              </div>
              <div class="col-12 py-2">
                <div class="flex flex-column justify-content-center">
                  <div class="text-xl text-black-alpha-80 line-height-3 md:pr-6">
                    <h4>Advance your studies and career with an AI assistant designed to supercharge dyslexic thinking.&nbsp;</h4>
                  </div>
                </div>
              </div>
            </div>
          </div>
          <div class="col-12 lg:col-6">
            <div class="grid">
              <div class="col-12">
                <div class="intrinsic">
                  <div class="intrinsic-inner">
                    <div ref="video" class="relative" style="opacity: 1;" id="">
                      <img data-src="/src/assets/images/videosplash.png" data-load="false" data-image-focal-point="0.5,0.5" class="loaded" data-image-dimensions="100x57" data-parent-ratio="1.8" style="font-size: 0px; left: 0px; top: -1.15px; width: 100%; height: 100%; position: relative;" data-image-resolution="750w" src="/src/assets/images/videosplash.png" data-video="http://www.youtube.com/embed/fsoXJmnV_Ns">
                      <a aria-label="Play" class="video-icon absolute" style="right: 42.5%; top: 36%;" tabindex="0" @click="handleYouTubeClick"><i class="pi pi-youtube" style="font-size: 4rem"></i></a>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
    <section class="section bg-primary-500 md:px-8 xs:px-4 py-3">
      <div class="content-wrapper">
        <div class="content grid sm:px-6">
          <div class="col-12 md:col-6">
            <div class="flex flex-column justify-content-center">
              <div class="text-2xl line-height-3 text-black-alpha-80 md:pr-6">
                <p class="sqsrte-large" style="white-space:pre-wrap;">Interested in early access or more information? Add your email to the waitlist!  </p>
              </div>
            </div>
          </div>
          <div class="col-12 md:col-6">
            <div class="form-wrapper">
              <form autocomplete="on" class="react-form-contents" ref="form">
                <div class="field-list">
                  <div class="form-item field email required" id="email" data-dynamic-strings="">
                    <label for="user_email">
                      <div class="text-black-alpha-90">
                        <span>Full Name & Email &nbsp;</span>
                        <span class="description required text-xs text-black-alpha-80">(required)</span>
                      </div>
                    </label>
                    <input v-model="form_name" aria-invalid="false" aria-required="true" autocomplete="name" class="w-full p-2 text-lg" id="user_name" placeholder="Full Name" type="text" name="user_name">
                    <input v-model="form_email" aria-invalid="false" aria-required="true" autocomplete="email" class="w-full p-2 text-lg" id="user_email" placeholder="email@company.com" type="email" name="user_email">
                  </div>
                </div>
                <div class="form-button-wrapper pt-2">
                  <Button type="submit" label="Send" aria-label="Send" value="Send" class="button" @click="handleSendClick" />
                </div>
              </form>
            </div>
          </div>
        </div>  
      </div>
    </section>
    <section class="section sm:p-5 p-2">
      <div class="content-wrapper">
        <div class="content grid sm:px-6">
          <div class="col-12">
            <div class="flex justify-content-center">
              <div class="text-2xl text-black-alpha-90 text-center line-height-2 bold">
                <h2>How does it work?</h2>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
    <section class="section px-3">
      <div class="content-wrapper">
        <div class="content grid">
          <div class="col-12 md:col-6 lg:col-4 md:px-4">
            <Card>
              <template #header>
                <img alt="user header" class="w-full" src="/src/assets/images/illus1.png" />
              </template>
              <template #title>
                <span class="line-height-2">Build your personal library</span>
              </template>
              <template #content>
                <p class="m-0">
                  Begin by selecting web pages, PDFs, and other documents that interest you. When you add them to your library, iCognition gets to work building your personal knowledge base.
                </p>
              </template>
            </Card>
          </div>
          <div class="col-12 md:col-6 lg:col-4 md:px-4">
            <Card>
              <template #header>
                <img alt="user header" class="w-full" src="/src/assets/images/illus3.png" />
              </template>
              <template #title>
                <span class="line-height-2">Read less and understand more</span>
              </template>
              <template #content>
                <p class="m-0">
                  iCognition summarizes the text and puts the essentials into easy-to-read bullet points that also have integrated audio controls.
                </p>
              </template>
            </Card>
          </div>
          <div class="col-12 md:col-6 lg:col-4 md:px-4">
            <Card>
              <template #header>
                <img alt="user header" class="w-full" src="/src/assets/images/illus5.png" />
              </template>
              <template #title>
                <span class="line-height-2">Supercharge dyslexic thinking</span>
              </template>
              <template #content>
                <p class="m-0">
                  iCognition empowers big-picture thinking by connecting articles to the big picture.
                </p>
              </template>
            </Card>
          </div>
          <div class="col-12 md:col-6 lg:col-4 md:px-4">
            <Card>
              <template #header>
                <img alt="user header" class="w-full" src="/src/assets/images/illus4.png" />
              </template>
              <template #title>
                <span class="line-height-2">Peace of mind</span>
              </template>
              <template #content>
                <p class="m-0">
                  iCognition auto-categorizes your personal library based on information from its content. The AI-powered search feature makes it easy to find information when you need it. iCognition is designed to organize information in a way that makes it accessible for people with dyslexia.
                </p>
              </template>
            </Card>
          </div>
          <div class="col-12 md:col-6 lg:col-4 md:px-4">
            <Card>
              <template #header>
                <img alt="user header" class="w-full" src="/src/assets/images/illus2.png" />
              </template>
              <template #title>
                <span class="line-height-2">Study buddy</span>
              </template>
              <template #content>
                <p class="m-0">
                  iCognition is also your study buddy, allowing you to use Generative AI to ask questions based on the documents in your library.
                </p>
              </template>
            </Card>
          </div>
        </div>
      </div>
    </section>
    <section class="section bg-black-alpha-90 border-top-6 border-primary-400">
      <div class="content-wrapper">
        <div class="content grid text-center text-4xl text-black font-medium m-auto content-transform-text">
          <div class="block m-auto py-5 m-0">
            <h3 class="line-height-1">Transform tedious text into bright insight with iCognition – the ultimate super-boost for dyslexic learners!&nbsp;</h3>
          </div>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
  import { ref } from "vue";
  import emailjs from '@emailjs/browser';
  import Card from 'primevue/card';
  import Button from 'primevue/button';

  const form = ref(null);
  const form_email = ref('');
  const form_name = ref('');
  const video = ref<HTMLElement | null>(null);
  // Remove redundant DOM queries and calculations as AppLayout will handle header/footer
  // const firstSection = document.querySelector('.page-section') as HTMLElement;
  // const header = document.querySelector('.header');
  // const mobileOverlayNav = document.querySelector('.header-menu');
  // const sectionBackground = firstSection ? firstSection.querySelector('.section-background') as HTMLElement : null;
  // const headerHeight = header ? header.getBoundingClientRect().height : 0;
  // const firstSectionHasBackground = firstSection ? firstSection.className.indexOf('has-background') >= 0 : false;
  // const isFirstSectionInset = firstSection ? firstSection.className.indexOf('background-width--inset') >= 0 : false;
  // const isLayoutEngineSection = firstSection ? firstSection.className.indexOf('layout-engine-section') >= 0 : false;

  // if (firstSection) {
  //   firstSection.style.paddingTop = headerHeight + 'px';
  // }
  // if (sectionBackground && isLayoutEngineSection) {
  //   if (isFirstSectionInset) {
  //     sectionBackground.style.top = headerHeight + 'px';
  //   } else {
  //     sectionBackground.style.top = '';
  //   }
  // }

const handleSendClick = async () => {
  console.log('Send Clicked', form_email.value);
  let params = {
      to_name: 'iCognition',
      from_name: form_name.value,
      user_email: form_email.value,
      message: 'Hello world',
    }

    emailjs
      .send('service_dzt964k', 'template_6e6k0m7', 
      params, {
        publicKey: 'RPWYe_cHikHCgVsm1',
        limitRate: {
          throttle: 2
        }
      })
      .then(
        (response) => {
          console.log('SUCCESS!', response.status, response.text);
        },
        (error) => {
          console.log('FAILED...', error);
        },
      );
  }

  const handleYouTubeClick = async () => {
    try {
      const videoIFrame = '<iframe width="560" height="315" src="https://www.youtube.com/embed/fsoXJmnV_Ns?autoplay=1" title="" frameBorder="0"   allow="accelerometer; autoplay; clipboard-write; encrypted-in; gyroscope; picture-in-picture; web-share"  allowFullScreen></iframe>';
      (video.value as HTMLElement).innerHTML = videoIFrame;
    } catch (error: any) {
        console.log(error.value)
    }
  }
  //# sourceURL=headerPositioning.js
</script>

<style scoped>
/* Add any specific styles for the HomeView content here if needed */
</style>
