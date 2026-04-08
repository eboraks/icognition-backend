import type { ElementDefinition } from 'cytoscape'
import type { EntitySummary, RelationshipSummary, DocumentSummary } from '@/types/graph'
import { getNodeColor } from '@/utils/graphStyles'

export function transformToCytoscapeElements(
  entities: EntitySummary[],
  relationships: RelationshipSummary[],
  documents: DocumentSummary[] = [],
  entityDocumentLinks: { entityId: number; documentId: number }[] = [],
): ElementDefinition[] {
  const cyNodes: ElementDefinition[] = entities.map((e) => ({
    group: 'nodes' as const,
    data: {
      id: String(e.id),
      name: e.name,
      type: e.type,
      canonicalType: e.canonical_type || null,
      wikidataId: e.wikidata_id || null,
      nodeKind: 'entity',
      color: getNodeColor(e.type),
    },
  }))

  const docNodes: ElementDefinition[] = documents.map((d) => ({
    group: 'nodes' as const,
    data: {
      id: `doc-${d.id}`,
      name: d.title,
      type: 'document',
      nodeKind: 'document',
      color: getNodeColor('document'),
    },
  }))

  const cyEdges: ElementDefinition[] = relationships.map((r) => ({
    group: 'edges' as const,
    data: {
      id: `rel-${r.id}`,
      source: String(r.from_entity_id),
      target: String(r.to_entity_id),
      relationship_type: r.relationship_type,
    },
  }))

  const docEdges: ElementDefinition[] = entityDocumentLinks.map((link) => ({
    group: 'edges' as const,
    data: {
      id: `edoc-${link.entityId}-${link.documentId}`,
      source: String(link.entityId),
      target: `doc-${link.documentId}`,
      relationship_type: 'appears_in',
    },
  }))

  return [...cyNodes, ...docNodes, ...cyEdges, ...docEdges]
}
