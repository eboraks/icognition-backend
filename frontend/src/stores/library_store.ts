import { defineStore } from 'pinia';
import { useDocumentStore } from './documents_store';

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
      this.loading = true;
      try {
        // Get real documents from documentStore instead of using mock data
        const documentStore = useDocumentStore();
        
        // Transform documentStore documents to library store format
        this.documents = documentStore.docs.map(doc => ({
          id: doc.id,
          title: doc.title || 'Untitled',
          updatedAt: doc.updateAt ? doc.updateAt.format('YYYY-MM-DD') : new Date().toISOString(),
          sourceUrl: doc.url,
          sourceHost: doc.url ? new URL(doc.url).hostname : undefined,
          summary: doc.is_about,
          keyPoints: doc.tldr || [],
          type: 'web'
        }));
        
        console.log('Library store updated with real documents:', this.documents.length);
      } catch (error) {
        console.error('Error fetching documents for library store:', error);
        // Fallback to empty array if there's an error
        this.documents = [];
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


