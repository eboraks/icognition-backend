// Graph exploration TypeScript types — mirrors backend graph_schemas.py

export interface EntitySummary {
  id: number
  name: string
  type: string
}

export interface DocumentSummary {
  id: number
  title: string
}

export interface EntityRead {
  id: number
  name: string
  type: string
  description?: string | null
  document_count: number
  documents: DocumentSummary[]
}

export interface RelationshipSummary {
  id: number
  from_entity_id: number
  to_entity_id: number
  relationship_type: string
}

export interface RelationshipRead {
  id: number
  from_entity: EntitySummary
  to_entity: EntitySummary
  relationship_type: string
  source_documents: DocumentSummary[]
}

export interface SearchHit {
  id: number
  label: string
  type: string
  result_type: 'entity' | 'relationship' | 'document'
  similarity: number
}

export interface SearchResponse {
  query: string
  total: number
  results: SearchHit[]
}

export interface DocumentRead {
  id: number
  title: string
  url?: string | null
  ai_markdown_content?: string | null
  entities: EntitySummary[]
}

export interface EntityDocumentLink {
  entity_id: number
  document_id: number
}

export interface NeighborhoodResponse {
  entities: EntitySummary[]
  relationships: RelationshipSummary[]
  documents: DocumentSummary[]
  entity_document_links: EntityDocumentLink[]
  center_entity_id?: number | null
}
