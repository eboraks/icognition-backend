import { defineStore } from 'pinia';

interface DocRow {
  id: string | number;
  title: string;
  updatedAt: string;
  sourceUrl?: string;
  sourceHost?: string;
  summary?: string;
  keyPoints?: string[];
}

export const useLibraryStore = defineStore('library', {
  state: () => ({
    documents: [] as DocRow[],
    loading: false,
    searchText: '',
    filters: {} as any,
  }),
  getters: {
    filteredDocuments(state): DocRow[] {
      const q = (state.searchText || '').toLowerCase();
      if (!q) return state.documents;
      return state.documents.filter((d) =>
        d.title.toLowerCase().includes(q) || (d.summary || '').toLowerCase().includes(q)
      );
    },
  },
  actions: {
    async fetchDocuments() {
      // Placeholder: integrate real API; keep stub for now
      this.loading = true;
      try {
        if (this.documents.length === 0) {
          this.documents = [
            { 
              id: 1, 
              title: 'Elon Musk says AI will take all our jobs', 
              updatedAt: '12/22/2024 08:34am', 
              sourceUrl: 'https://newsorg.com', 
              sourceHost: 'newsorg.com', 
              type: 'web',
              summary: 'Lorem ipsum dolor sit amet, consectetur adipiscing elit. Sed do eiusmod tempor incididunt ut labore et dolore magna aliqua. Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris.', 
              keyPoints: [
                'AI will replace most human jobs in the next decade',
                'Universal basic income may become necessary',
                'Education systems need to adapt to new reality'
              ] 
            },
            { 
              id: 2, 
              title: 'Essay', 
              updatedAt: '12/22/2024 08:34am', 
              sourceUrl: 'https://mediaite.com', 
              sourceHost: 'mediaite.com',
              type: 'web'
            },
            { 
              id: 3, 
              title: 'History of Persepolis', 
              updatedAt: '12/22/2024 08:34am', 
              sourceUrl: 'https://mediaite.com', 
              sourceHost: 'mediaite.com',
              type: 'web'
            },
            { 
              id: 4, 
              title: 'Another Web Article', 
              updatedAt: '12/22/2024 08:34am', 
              sourceUrl: 'https://mediaite.com', 
              sourceHost: 'mediaite.com',
              type: 'web'
            },
            { 
              id: 5, 
              title: 'Jane Goodall Once Walked Right Up to Most Dangerous Alpha Chimp', 
              updatedAt: '12/21/2024 10:15am', 
              sourceUrl: 'https://nationalgeographic.com', 
              sourceHost: 'nationalgeographic.com',
              type: 'web',
              summary: 'Dr. Jane Goodall shares her remarkable experience approaching a dominant chimpanzee in the wild, demonstrating her deep understanding of primate behavior and her fearless dedication to research.',
              keyPoints: [
                'Goodall approached the alpha chimp without fear',
                'Her understanding of chimp behavior was key to safety',
                'This incident demonstrated her unique research methods'
              ]
            }
          ];
        }
      } finally {
        this.loading = false;
      }
    },
    setSearch(text: string) {
      this.searchText = text;
    },
    setFilters(f: any) {
      this.filters = f;
    },
  },
});


