import axios from 'axios';
import { getAuth } from 'firebase/auth';
import type {
  SearchResponse, EntityRead, NeighborhoodResponse,
  RelationshipRead, RelationshipSummary, DocumentSummary,
  DocumentRead, ThemeSummary, ResearchSessionSummary,
} from '@/types/graph';

const apiBaseUrl: string = import.meta.env.VITE_APP_API_BASE_URL || '';

const apiClient = axios.create({
  baseURL: apiBaseUrl,
  headers: {
    'Content-Type': 'application/json',
  },
});

apiClient.interceptors.request.use(async (config) => {
  const auth = getAuth();
  const user = auth.currentUser;
  if (user) {
    const token = await user.getIdToken();
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
}, (error) => {
  return Promise.reject(error);
});

export interface TreeNodeData {
  type: 'document' | 'entity_type' | 'entity';
  id?: number | null;
  title?: string;
  name?: string;
  entity_type?: string;
  icon?: string;
}

export interface FilterTreeNode {
  key: string;
  label: string;
  icon?: string;
  data?: TreeNodeData;
  children?: FilterTreeNode[];
}

export type FilterTreeData = FilterTreeNode[];

export interface ContextualMessageResponse {
  message: string;
  actions: Array<{ id: string; label: string }>;
  entity?: {
    id: number;
    name: string;
    type: string;
    description?: string;
  };
  document?: {
    id: number;
    title: string;
  };
  document_count?: number;
}

export interface ActionResponse {
  message: string;
  resources?: Array<{ id: number; title: string }>;
  actions?: Array<{ id: string; label: string }>;
}

export interface EntityRef {
  id: number;
  name: string;
  type: string;
}

export interface EntityRelationshipItem {
  from_entity: EntityRef;
  relationship_type: string;
  to_entity: EntityRef;
}

export interface EntityRelationshipsResponse {
  entity: EntityRef & { description?: string };
  relationships: EntityRelationshipItem[];
}

export const knowledgeService = {
  getFilterTree(): Promise<{ data: FilterTreeData }> {
    return apiClient.get('/api/v1/knowledge/filter-tree');
  },

  getContextualMessage(entityId?: number, documentId?: number): Promise<{ data: ContextualMessageResponse }> {
    return apiClient.post('/api/v1/knowledge/contextual-message', {
      entity_id: entityId || null,
      document_id: documentId || null,
    });
  },

  handleAction(
    actionId: string,
    entityId?: number,
    documentId?: number
  ): Promise<{ data: ActionResponse }> {
    return apiClient.post('/api/v1/knowledge/action', {
      action_id: actionId,
      entity_id: entityId || null,
      document_id: documentId || null,
    });
  },

  getEntityRelationships(entityId: number): Promise<{ data: EntityRelationshipsResponse }> {
    return apiClient.get(`/api/v1/knowledge/entity/${entityId}/relationships`);
  },

  // ── Discovery Hub endpoints ──────────────────────

  getDiscoveryGraph(params?: {
    source?: string;
    theme?: number;
    research?: number;
    limit?: number;
  }): Promise<{ data: NeighborhoodResponse }> {
    return apiClient.get('/api/v1/knowledge/graph/discovery', { params });
  },

  getResearchSessions(): Promise<{ data: { research_sessions: ResearchSessionSummary[] } }> {
    return apiClient.get('/api/v1/knowledge/research-sessions');
  },

  getResearchSession(sessionId: number): Promise<{ data: any }> {
    return apiClient.get(`/api/v1/knowledge/research-sessions/${sessionId}`);
  },

  deleteResearchSession(sessionId: number): Promise<{ data: any }> {
    return apiClient.delete(`/api/v1/knowledge/research-sessions/${sessionId}`);
  },

  getDocumentSources(): Promise<{ data: { sources: { site_name: string; count: number }[] } }> {
    return apiClient.get('/api/v1/knowledge/graph/sources');
  },

  // ── Theme endpoints ────────────────────────────────

  getThemes(): Promise<{ data: { themes: ThemeSummary[] } }> {
    return apiClient.get('/api/v1/knowledge/themes');
  },

  getThemeDocuments(themeId: number): Promise<{ data: DocumentSummary[] }> {
    return apiClient.get(`/api/v1/knowledge/themes/${themeId}/documents`);
  },

  reassignDocument(fromThemeId: number, body: { document_id: number; to_theme_id: number }): Promise<{ data: { ok: boolean } }> {
    return apiClient.post(`/api/v1/knowledge/themes/${fromThemeId}/reassign`, body);
  },

  reclusterThemes(): Promise<{ data: { themes_created: number; themes_updated: number; documents_assigned: number } }> {
    return apiClient.post('/api/v1/knowledge/themes/recluster');
  },

  updateTheme(themeId: number, body: { label?: string; color?: string }): Promise<{ data: { ok: boolean } }> {
    return apiClient.put(`/api/v1/knowledge/themes/${themeId}`, body);
  },

  // ── Graph exploration endpoints ──────────────────

  graphSearch(q: string, params?: {
    result_type?: string;
    entity_type?: string;
    limit?: number;
    threshold?: number;
  }): Promise<{ data: SearchResponse }> {
    return apiClient.get('/api/v1/knowledge/graph/search', { params: { q, ...params } });
  },

  getGraphEntity(entityId: number): Promise<{ data: EntityRead }> {
    return apiClient.get(`/api/v1/knowledge/graph/entities/${entityId}`);
  },

  getNeighborhood(entityId: number, params?: {
    depth?: number;
    limit?: number;
  }): Promise<{ data: NeighborhoodResponse }> {
    return apiClient.get(`/api/v1/knowledge/graph/entities/${entityId}/neighborhood`, { params });
  },

  getGraphRelationship(relationshipId: number): Promise<{ data: RelationshipRead }> {
    return apiClient.get(`/api/v1/knowledge/graph/relationships/${relationshipId}`);
  },

  getGraphEntityRelationships(entityId: number, params?: {
    direction?: string;
    limit?: number;
  }): Promise<{ data: RelationshipSummary[] }> {
    return apiClient.get(`/api/v1/knowledge/graph/entities/${entityId}/relationships`, { params });
  },

  getGraphEntityDocuments(entityId: number, limit?: number): Promise<{ data: DocumentSummary[] }> {
    return apiClient.get(`/api/v1/knowledge/graph/entities/${entityId}/documents`, { params: { limit } });
  },

  getSubgraph(entityIds: number[], includeRelationships = true): Promise<{ data: NeighborhoodResponse }> {
    return apiClient.post('/api/v1/knowledge/graph/subgraph', {
      entity_ids: entityIds,
      include_relationships: includeRelationships,
    });
  },

  getGraphDocument(documentId: number): Promise<{ data: DocumentRead }> {
    return apiClient.get(`/api/v1/knowledge/graph/documents/${documentId}`);
  },

  getDocumentSubgraph(documentId: number): Promise<{ data: NeighborhoodResponse }> {
    return apiClient.get(`/api/v1/knowledge/graph/documents/${documentId}/subgraph`);
  },
};

