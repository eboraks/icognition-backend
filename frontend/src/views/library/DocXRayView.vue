<script lang="ts">
  import QuestionAnswerCard from '@/components/QuestionAnswerCard.vue';
  export default {
    name: 'DocXRayView',
    components: {
      'QuestionAnswerCard': QuestionAnswerCard
    }
  }
</script>

<script setup lang="ts" >
  import { ref, h, onBeforeMount, watch } from 'vue';
  import { marked } from 'marked';
  import { useRouter } from 'vue-router';
  import { useCustomQandA } from '@/composables/useCustomQandA.ts';
  import { useDocQuesAnswers } from '@/composables/useDocQuesAnswers.ts';
  import { useDocXRay } from '@/composables/useDocXRay.ts';
  import moment, { Moment } from 'moment';
  import { QuestionsAnswersStore } from '@/stores/questions_answers_store.ts';
  import * as pdfFonts from '@/components/models/vfs_fonts';
  import  pdfMake from "pdfmake/build/pdfmake";
  import { ElementTextObject } from '@/components/models/ElementTextObject';
  import { Citation } from '@/components/models/Citation';
  import { AskQuestionAnswerInterface } from '@/components/models/AskQuestionAnswerInterface';
  (<any>pdfMake).vfs = pdfFonts.default;
  // import TalkifyTTSService from '@/services/TalkifyTTSService';
  // import Talkify from 'talkify-tts-api';

  const qa_store = QuestionsAnswersStore();
  const { isAskPending, askQuestion, answerResponse } = useCustomQandA();
  const { qas, qasPending, getDocQuestionsAnswers } = useDocQuesAnswers();
  const { doc, original_elements, xRayIsPending, getDocumetXRay } = useDocXRay();
  const answer = ref('');
  let author = ref();
  const blank_uuid = '';
  const breadcrumb_home = ref({
    icon: 'pi pi-home',
    route: '/library'
  });
  const breadcrumb_items = ref([
    { label: 'Document XRay' }
  ]);
  const buttonToggleSplitterPanelRight = ref(true);
  const citations = ref<Citation[]>();
  const highlightedFromWhere = ref();
  const highlightedText = ref('');
  const highlightedTextList = ref<any[]>([]);
  const highlightNotesValue = ref('');
  const htmlElementsForPage = ref<any[] | null>([]);
  const htmlElementsForPDF = ref<any[] | null>([]);
  let htmlToPDF: [Object | null] = [null];
  const menuHighlight = ref();
  let publication_date = ref();
  const router = useRouter();
  const qanda_div = ref<Document | undefined>(undefined);
  const question = ref('');
  let scrollToElement = 0;
  const scrollRef = ref<any>(null);
  let tooltiptext = 'Citation';

  onBeforeMount(async () => {
      try {
        await getDocumetXRay(router.currentRoute.value.params.id as string);
        console.log("Document: ", doc.value);
        console.log("Original Elements: ", original_elements.value);
        htmlElementsForPage.value = htmlElementsForPDF.value = original_elements.value;
        author = ref(doc.value?.authors);
        //Citation is driving the vnode to be updated
        citations.value = doc.value?.summary_citations;

        //Generate document for html
        publication_date = ref(formate_date((doc.value?.publicationDate as Moment)));

        qa_store.init(router.currentRoute.value.params.id as string, 'document');
        await qa_store.fetchQuestionsAnswers();
        console.log("Questions and Answers from store: ", qa_store.config.list);
      } catch (err) {
        console.log("Error: ", err);
      }
  });

  const renderMarkdown = (content?: string) => {
    if (!content) return '';
    const renderer = new marked.Renderer();
    renderer.link = ({ href, title, text }) => `<a href="${href}" target="_blank" rel="noopener noreferrer" class="text-primary hover:underline" title="${title || ''}">${text}</a>`;
    marked.setOptions({ renderer });
    return marked.parse(content);
  };

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

  const build_citation_span = (element: ElementTextObject, citations: Citation[], tooltiptext: string) => {
    let text = element.text as string;
    let citations_texts: any[] = [];
    citations.forEach((citation) => {
      citation.verbatims?.forEach((verbatim) => {
        citations_texts.push(verbatim.verbatim_text);
        if (text.includes(verbatim.verbatim_text as string)) {
          text = text.replace(new RegExp(verbatim.verbatim_text as string, 'gi'), `|${verbatim.verbatim_text}|`);
        }
      })
      
    }); 
    let text_array = text.split('|');
      //Iterate and create the elements with h(, { class: 'mt-2', innerHTML: element.text });
    let nodes: any[] = [];
    let citation_exits = false;
    
    text_array.forEach((item) => {
      
      if (item.trim() != '') {
        if (citations_texts.includes(item)) {
          
          //ref: scrollRef is used to scroll to the element
          let node = h('span', { class: 'bg-highlight tooltip', id: 'section-'+scrollToElement, ref: scrollRef }, [item, h('span', { class: 'tooltiptext' }, tooltiptext)]);
          nodes.push(node);
          
          scrollToElement++;
          citation_exits = true;
        } else {
          nodes.push(h('span', { class: 'mt-2', innerHTML: item }));
        }
      }
    });
    //Return the element with the citation hightlighted
    if (citation_exits) {
      return (h(element.element as string, { class: 'mt-2', id: 'section-'+scrollToElement }, nodes));
    } else {
      return (h(element.element as string, { class: 'mt-2' }, nodes));
    }
  }

  const vnode = () => {
    let children: any[] = [];
    htmlElementsForPage.value?.forEach((element) => {
      children.push(markCitations(element, tooltiptext));
    });
    return h(
      'div',
      { id: 'document', class: '' },
      [ children ]
    );
  }

  //Watch for the scrollRef to be updated and scroll to the element
  //If the scrollRef is not updated then wait for 300 millisecond and try again for 5 times
  watch(scrollRef, async() => {
    if (scrollRef.value == null) {
      let loopCounter = 0;
        while (loopCounter < 5 && scrollRef.value == null) {
          console.log("scrollRef is null, waiting for 300 ms and trying again");
          await new Promise(resolve => setTimeout(resolve, 300));
          scrollRef.value?.scrollIntoView({ behavior: "smooth", block: "center" });
          loopCounter++;
        }
    } else {
      console.log("Scrolling to element: ", scrollRef.value);
      scrollRef.value.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  });

  function formate_date(value: Moment) {
    return moment(value).format('hh:mm a, MM-DD-YYYY');
  };

  const handleDownloadClick = async () => {
    htmlElementsForPDF.value?.forEach(item => {
      return htmlToPDF.push(add_to_pdf(item.element, item.text));
    });

    const docDefinition = {
      content: [
        {
          style: 'header',
          table: {
            widths: ['auto'],
            body: [
              [htmlToPDF]
            ]
          },
          layout: {
            defaultBorder: false,
          }
        }
      ]
    }
    pdfMake.createPdf(docDefinition).download(`${(doc.value?.title as string).substr(0, 20)}.pdf`);
  }

  const handleHighlightNotesAdd = async () => {
    if (highlightNotesValue.value != '' && highlightNotesValue.value != null) {
      handleHighlightClick();
    }
    menuHighlight.value.toggle();
  }

  const handleHighlightClick = async () => {
    
    htmlElementsForPage.value?.forEach(element => {
      if (element.text == highlightedFromWhere.value) {
        if (element.text.includes(highlightedText.value)) {
          let first_half = element.text.substr(0, element.text.indexOf(highlightedText.value));
          let second_half = element.text.substr(element.text.indexOf(highlightedText.value) + highlightedText.value.length, element.text.length);
          element.text = first_half + `<span class="bg-highlight tooltip" id="section-${scrollToElement}">${highlightedText.value}<span class="tooltiptext">${highlightNotesValue.value}</span></span>` + second_half;
          console.log("handled highlight click element.text: ", element.text);
        }
      }
    });
    
    highlightedTextList.value.push({
      id: '#section-' + scrollToElement,
      contents: highlightedText,
      notes: highlightNotesValue.value,
      updated: new Date()
    });
    scrollToElement += 1;
  }

  function getSelectedText() {
    let text= '';
    if (((document as Document).getSelection() as Selection).toString() != 'undefined') {
      text = ((document as Document).getSelection() as Selection).toString();
    }
    return text;
  }

  const handleAsk = async () => {
    console.log("Asking question: ", question.value, " document_id: ", doc.value?.id as string);
    if (!question) {
      answer.value = 'Please enter a question';
      return;
    }
    qa_store.addQuestion(question.value);
    //sleep for 100 ms
    await new Promise(resolve => setTimeout(resolve, 200));
    const lastQandAElement = qanda_div.value?.lastElementChild;
    console.log("lastQandAElement: ", lastQandAElement);
    (lastQandAElement as Element).scrollIntoView({ behavior: "smooth"});

    question.value = '';
  }

  watch(qanda_div, async () => {
    console.log("watch qanda_div: ", qanda_div.value);
    if (qanda_div.value != null) {
      const lastQandAElement = qanda_div.value.lastElementChild;
      console.log("lastQandAElement: ", lastQandAElement);
      lastQandAElement?.scrollIntoView({ behavior: "smooth"});
    }
  });

  function markCitations(element: ElementTextObject, tooltiptext: string) {
    if (citations.value != null) {
      let found_citations: any[] = [];
      citations.value.forEach((citation: any, index: number) => {
        citation.verbatims.forEach((verbatim: any) => {
          if (element.text?.includes(verbatim.verbatim_text)) {
            found_citations.push(citation);
          }
        });
      });

      if (found_citations.length > 0) {
        let citiation_instances = [];
        
        citiation_instances.push(build_citation_span(element, found_citations, tooltiptext));
        return citiation_instances;
      } else {
        return h(element.element as string, { class: 'mt-2', innerHTML: element.text })
      }
      
    } else {
      return h(element.element as string, { class: 'mt-2', innerHTML: element.text })
    }
  }

  const toggleCitation = async (qanda: AskQuestionAnswerInterface) => {
    // By assinging the value to the Ref cititation it will trigger the vnode to be updated
    citations.value = qanda.citations;
    tooltiptext = qanda.question as string;
  }

  const toggleHighlightMenu = (event: Event) => {
    // We need to get the highlighted text prior to opening the popover or we lose the data.
    highlightedText.value = getSelectedText();
    highlightedFromWhere.value = (((document as Document).getSelection() as Selection).focusNode as Node).textContent;
    menuHighlight.value.toggle(event);
  };

</script>

<template>
  <!-- The height is calculated based on the full page - header(55.2px) - footer(72px) for padding on top and bottom -->
  <div id="body-library" class="grid nested-grid grid-nogutter p-0" style="height: calc(100% - 3.45em - 4.5em);">
    <div class="col-12 p-0 h-full">
      <div class="grid nested-grid grid-nogutter bg-white">
        <div class="max-w-100rem mx-auto w-full">
          <div class="px-3 py-2 flex flex-column">
            <Breadcrumb :home="breadcrumb_home" :model="breadcrumb_items">
              <template #item="{ item, props }">
                <router-link v-slot="{ href, navigate }" :to="item.route" custom>
                  <a :href="href" v-bind="props.action" @click="navigate">
                    <span :class="[item.icon, 'text-color-secondary text-sm']"></span>
                    <span class="text-color-secondary text-sm">{{ item.label }}</span>
                  </a>
                </router-link>
              </template>
            </Breadcrumb>
            <div class="flex flex-row">
              <i v-if="doc?.source_type == 'web'" class="pi pi-web"></i>
              <i v-else class="pi pi-pdf"></i>
              <h3>{{ doc?.title }}</h3>
            </div>
          </div>
        </div>
      </div>
    
      <Splitter class="grid nested-grid grid-nogutter max-w-100rem mx-auto my-2 px-3 splitter-height">
        <SplitterPanel :class="{ 'splitter-panel-container-full': !buttonToggleSplitterPanelRight }" class="col-12 p-0" :size="50" :minSize="1">
          <div class="card h-full">
            <Tabs value="0" class="h-full">
              <TabList>
                <Tab value="0">Overview</Tab>
                <Tab value="1">Ask iCognition</Tab>
                <Tab value="2">Notations</Tab>
              </TabList>
              <TabPanels>
                <TabPanel value="0">
                  <div class="w-full h-full bg-white border-1 border-300">
                    <div class="overflow-y-auto px-2 py-3" style="height: calc(100% - 49.6px);">
                      <h4 class="pb-2">Summary</h4>
                      <p class="line-height-2 summary-content" v-if="doc != null && doc.is_about != null">{{ doc.is_about }}</p>
                      <div v-if="doc != null && doc.aiMarkdownContent">
                        <h4 class="pt-3">Key Points:</h4>
                        <div class="key-points-content" v-html="renderMarkdown(doc.aiMarkdownContent)"></div>
                      </div>
                      <div v-if="doc != null && qa_store.config.list.size > 0">
                        <h4 class="pt-3">Questions answered by this document</h4>
                          <ul>
                            <li v-for="[uuid, item] in qa_store.config.list">
                              {{ item?.answer }}
                            </li>
                          </ul>
                      </div>
                    </div>
                  </div>
                </TabPanel>
                <TabPanel value="1">
                  <div class="flex-column h-full bg-white border-1 border-300">
                    <div class="overflow-y-auto px-2 py-2" ref="qanda_div" style="height: calc(100% - 2.75em);">
                      <div class="panel mb-3">
                        <div class="card">
                          <Card class="border-1 border-round border-300 bg-white shadow-3">
                            <template #header>
                            </template>
                            <template #content class="p-0">
                              <div class="bg-300 flex flex-column">
                                <div class="flex-row mx-3">
                                  <p class="flex-grow-1 py-1 text-sm text-black-alpha-90 border-round">You can ask the AI for a variety of information about this document such as:</p>
                                  <ul>
                                    <li>Create an outline summary of this document</li>
                                    <li>What questions are answered by this article?</li>
                                  </ul>
                                </div>
                              </div>
                            </template>
                          </Card>
                        </div>
                      </div>
                      <div v-for="[uuid, item] in qa_store.config.list">
                        <QuestionAnswerCard :qanda="item" :uuid=uuid @highlight_citiation="toggleCitation" />
                      </div>
                    </div>
                    <div class="flex p-2 bg-white border-top-1 border-300" style="height: 2.75em;">
                      <InputText @keyup.enter="handleAsk" class="flex-grow-1 p-1" type="text" v-model="question" />
                      <Button class="flex-shrink-0 px-3 py-1 ml-1 bg-primary-500 text-white" icon="pi pi-arrow-right" @click="handleAsk" />
                    </div>
                  </div>
                </TabPanel>
                <TabPanel value="2">
                  <div class="flex-column h-full bg-white border-1 border-300">
                    <div class="overflow-y-auto px-2 py-2">
                      <div class="panel mb-3">
                        <div v-for="item in highlightedTextList" class="mb-3">
                          <p class="text-sm">{{ moment(item.updated).format('DD MMM YYYY h:mm a') }}</p>
                          <p class="text-sm"><a :href="item.id">{{ item.notes }}</a></p>
                        </div>
                      </div>
                    </div>
                  </div>
                </TabPanel>
              </TabPanels>
            </Tabs>
          </div>
        </SplitterPanel>
        <SplitterPanel :class="{ 'hidden': !buttonToggleSplitterPanelRight }" class="col-12 p-0" :size="50">
          <div class="card h-full border-1 border-300">
            <div class="col-12 py-0 bg-white border-bottom-1 border-300">
              <div class="col-6 p-0 inline-flex">
                <!-- <a class="font-bold pt-2 pl-1 mr-3" :href="doc.url" target="_blank"><i class="pi pi-pen-to-square"></i> Open Original</a> -->
                <!-- <a class="font-bold pt-2 pl-1" @click="handleDownloadClick"><i class="pi pi-download mr-1"></i>Download...</a> -->
                <h3>Document Content</h3>
              </div>
              <div class="col-6 p-0 inline-flex justify-content-end">
                <Button type="button" icon="pi pi-comment" class="text-black-alpha-90 bg-white my-1 border-200" @click="toggleHighlightMenu" rounded aria-haspopup="true" aria-controls="overlay_menu" style="height: 2.5em; width: 2.5em;" />
                <Popover ref="menuHighlight" class="mt-2">
                  <div class="grid flex flex-column w-[25rem]">
                    <div class="col-12">
                      <p>Add Notation</p>
                      <Textarea v-model="highlightNotesValue" rows="4" cols="30" />
                    </div>
                    <div class="col-12 pt-0 flex justify-content-end">
                      <Button type="button" label="Add Note" class="bg-primary-800" @click="handleHighlightNotesAdd"></Button>
                    </div>
                  </div>
                </Popover>
                <!-- <Button class="text-black-alpha-90 bg-white ml-2 my-1 border-blue-100" icon="pi pi-cog" @click="buttonToggleSplitterPanelRight = !buttonToggleSplitterPanelRight" rounded  style="height: 2.5em; width: 2.5em;" /> -->
              </div>
            </div>
            
            <div class="col-12 border-1 border-round border-solid mb-3 border-blue-100 overflow-y-auto" style="height: calc(100% - 48.8px);">
              <div class="col-12 bg-white px-3 py-2 flex flex-column border-round">
                <div class="flex-row">
                  <span class="text-sm" v-if="author != null" v-for="item in author">{{ item }} </span>
                </div>
                
                <span class="text-sm mb-3">Published {{ publication_date }}</span>
                <div v-if="xRayIsPending" class="flex flex-flow justify-content-center">
                  <i class="pi pi-spin pi-spinner" style="font-size: 2rem"></i>
                </div>
                <!-- key citations tell Vue to listen to changes on citiations -->
                <div><vnode :key="citations"/></div>
              </div>
            </div>
          </div>
        </SplitterPanel>
      </Splitter>
    </div>
  </div>
</template>

<style scoped>
.summary-content, .key-points-content {
  font-family: 'Roboto Mono', monospace;
}
</style>
