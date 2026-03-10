import axios from 'axios';
import { getAuth } from 'firebase/auth';
import type {
  SearchResponse, EntityRead, NeighborhoodResponse,
  RelationshipRead, RelationshipSummary, DocumentSummary,
  DocumentRead,
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

