<template>
    <div class="grid nested-grid grid-nogutter border-1 border-round border-solid border-2 border-blue-100 surface-200 h-full">
        <div class="col-12 h-full">
            <div class="grid grid-nogutter px-3 py-2" style="height: 60px;">
                <div class="col-6 flex vertical-align-middle">
                    <a class="font-bold pt-2 pl-1" @click="handleDownloadClick"><i class="pi pi-download mr-1"></i>Download...</a>
                </div>
                <div class="col-6 flex justify-content-end">
                    <Button class="text-black-alpha-90 bg-white ml-2 border-blue-100" icon="pi pi-play" @click="handlePlayClick" rounded />
                </div>
            </div>
            
            <div class="grid grid-nogutter border-1 border-round border-solid border-2 mx-3 mb-3 border-blue-100" style="height: calc(100% - 60px - 1rem);">
                <div class="col-12 bg-white p-3 flex flex-column border-round overflow-y-auto relative h-full">
                    <span class="text-xs">{{ author.valueOf() }}</span>
                    <span class="text-xs">Updated {{ updated_at.valueOf() }}</span>
                    <div v-for="item in html_elements_for_original_page" class="text-sm">
                        <h1 v-if="item.element == 'h1'" class="mt-2">{{ item.text }}</h1>
                        <h2 v-if="item.element == 'h2'" class="mt-2">{{ item.text }}</h2>
                        <h3 v-if="item.element == 'h3'" class="mt-1">{{ item.text }}</h3>
                        <h4 v-if="item.element == 'h4'" class="mt-1">{{ item.text }}</h4>
                        <h5 v-if="item.element == 'h5'" class="mt-1">{{ item.text }}</h5>
                        <p v-if="item.element == 'p'">{{ item.text }}</p>
                    </div>
                </div>
            </div>
        </div>
    </div>
</template>
  
<script setup lang="ts">
    import { ref, onBeforeMount, inject } from 'vue';
    import moment, { Moment } from 'moment';
    import pdfMake from 'pdfmake/build/pdfmake';
    import pdfFonts from 'pdfmake/build/vfs_fonts';
    import { ElementTextObject } from '@/components/models/ElementTextObject';
    (pdfMake as any).vfs = pdfFonts.pdfMake.vfs;
    // import TalkifyTTSService from '@/services/TalkifyTTSService';
    // import Talkify from 'talkify-tts-api';
    // import ContentObject from '@/components/models/ContentObject.vue';
    
    const dialogRef = inject("dialogRef") as any;
    let author = ref(dialogRef.value.data.authors[dialogRef.value.data.authors.length - 1]);
    const html_elements_for_original_page = ref(dialogRef.value.data.html_elements);
    let html_elements_for_pdf: ElementTextObject[] = dialogRef.value.data.html_elements;
    let html_to_pdf: [any[] | null] = [null];
    let updated_at = ref(formate_date(dialogRef.value.data.updateAt));

    onBeforeMount(async () => {
      try {
        // const talkify_tts_api_key = TalkifyTTSService.getTalkifyTTSAPIKEY().then(data => {
        //     return data;
        // });
        // const talkify_tts_host = TalkifyTTSService.getTalkifyTTSHost().then(data => {
        //     return data;
        // });
      } catch (err) {
        console.log("Error: ", err);
      }
    });

    

    function add_to_pdf(element: string, text: string): any {
        switch(element) {
            case 'h1':
                return {
                    text: `\n${text}\n`,
                    fontSize: 18
                };
            case 'h2':
                return {
                    text: `\n${text}\n`,
                    fontSize: 16
                };
            case 'h3':
                return {
                    text: `\n${text}\n`,
                    fontSize: 14
                };
            case 'h4':
                return {
                    text: `\n${text}\n`,
                    fontSize: 12
                };
            case 'h5':
                return {
                    text: `\n${text}\n`,
                    fontSize: 10
                };
            case 'p':
                return {
                    text: `\n${text}\n`,
                    fontSize: 10
                };
            default:
                return {
                    text: `${text}`,
                    fontSize: 10
                };
        }
    }
    

    function formate_date(value: Moment) {
        return moment(value).format('hh:mm a, MM-DD-YYYY');
    };

    const handleDownloadClick = async () => {
        console.log(html_elements_for_pdf);
        html_elements_for_pdf.forEach(item => {
            return html_to_pdf.push(add_to_pdf(item.element as string, item.text as string));
        });

        const docDefinition = {
            content: [
                {
                    style: 'header',
                    table: {
                        widths: ['auto'],
                        body: [
                            [html_to_pdf]
                        ]
                    },
                    layout: {
                        defaultBorder: false,
                    }
                }
            ]
        }

        pdfMake.createPdf(docDefinition).download(`${dialogRef.value.data.title.substr(0, 20)}.pdf`);
    }

    const handlePlayClick = async () => {

    }

</script>
  