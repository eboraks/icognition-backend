// Graph exploration TypeScript types — mirrors backend graph_schemas.py
// Backend reads from KG tables (kg_node, kg_edge, kg_node_document)

export interface EntitySummary {
  id: number
  name: string
  type: string // raw_type from extraction (person, organization, location, etc.)
  canonical_type?: string | null // schema.org class label (Person, Country, City)
  wikidata_id?: string | null
}

export interface DocumentSummary {
  id: number
  title: string
}

export interface EntityRead {
  id: number
  name: string
  type: string
  canonical_type?: string | null
  schema_type_uri?: string | null
  wikidata_id?: string | null
  description?: string | null
  document_count: number
  documents: DocumentSummary[]
}

export interface RelationshipSummary {
  id: number
  from_entity_id: number
  to_entity_id: number
  relationship_type: string // property_label (canonical or raw)
  property_uri?: string | null
}

export interface RelationshipRead {
  id: number
  from_entity: EntitySummary
  to_entity: EntitySummary
  relationship_type: string
  property_uri?: string | null
  raw_relationship_type?: string | null
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

export interface ThemeSummary {
  id: number
  label: string
  description?: string | null
  doc_count: number
  color?: string | null
}

export interface ResearchSessionSummary {
  id: number
  brief: string
  status: string
  created_at: string
  doc_count: number
}
