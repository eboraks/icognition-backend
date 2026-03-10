# Graph Exploration Tool — Development Plan

**Stack:** PostgreSQL · FastAPI · Vue.js 3 · Cytoscape.js

---

## 1. Project Overview

Extend the existing FastAPI + Vue 3 application with an interactive graph exploration feature. Users search across **entities** and **relationships** already stored in PostgreSQL, visualize results as a force-directed bubble-and-line graph using Cytoscape.js, and inspect properties in a slide-out side panel.

---

## 2. Technology Choices

### 2.1 Graph Visualization — Cytoscape.js (Direct Integration)

Cytoscape.js (`https://js.cytoscape.org/`) will be integrated directly into Vue 3 via a composable — **not** through `vue-cytoscape` or `vue3-cytoscape`, which have stale maintenance and limited Vue 3 Composition API support. Direct integration gives full control over the Cytoscape instance lifecycle and avoids wrapper abstractions.

**Extensions to install:**

| npm Package | Purpose |
|---|---|
| `cytoscape` | Core library |
| `cytoscape-cose-bilkent` | Force-directed layout with compound node support |
| `cytoscape-popper` | Anchor tooltips / popovers to nodes/edges (pairs with Floating UI) |
| `@floating-ui/dom` | Tooltip positioning engine (Popper.js successor) |

### 2.2 Search — PostgreSQL `pg_trgm`

Use the `pg_trgm` extension with GIN indexes for fuzzy, typo-tolerant search across entity names and relationship types. This avoids adding Elasticsearch or any external search engine.

### 2.3 Frontend State & Data Fetching

| Tool | Purpose |
|---|---|
| **Pinia** | Vue 3 store for selected entity/relationship, panel state, graph elements cache |
| **VueUse** | Utility composables (`useDebounceFn` for search input, `useResizeObserver` for canvas) |
| Existing HTTP client (Axios / fetch) | API calls to FastAPI |

---

## 3. Existing Database Schema

The application already has these four tables. **No new tables are needed.**

```
┌──────────────────┐       ┌──────────────────────────┐
│    entities       │       │  entity_relationships     │
│──────────────────│       │──────────────────────────│
│ id           PK  │◄──┐   │ id                   PK  │
│ name             │   ├───│ from_entity_id        FK  │
│ type             │   ├───│ to_entity_id          FK  │
│                  │   │   │ relationship_type         │
└──────────────────┘   │   │ source_document_id    FK ─┼──┐
                       │   └──────────────────────────┘  │
┌──────────────────┐   │   ┌──────────────────────────┐  │
│ entity_documents  │   │   │       document            │  │
│──────────────────│   │   │──────────────────────────│  │
│ entity_id    FK ─┼───┘   │ id                   PK ◄┼──┘
│ document_id  FK ─┼───────│ title                    │
└──────────────────┘       └──────────────────────────┘
```

**Mapping to graph concepts:**

| Graph Concept | Table | Key Columns |
|---|---|---|
| **Node** (bubble) | `entities` | `id`, `name`, `type` |
| **Edge** (line) | `entity_relationships` | `id`, `from_entity_id`, `to_entity_id`, `relationship_type`, `source_document_id` |
| Node ↔ Document link | `entity_documents` | `entity_id`, `document_id` |
| Source document | `document` | `id`, `title` |

### 3.1 Index Additions (Alembic Migration)

Only new **indexes** are needed to support fuzzy search and fast traversal:

```sql
-- Enable trigram extension (run once)
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- ── Fuzzy search ──────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_entity_name_trgm
    ON entities USING GIN (name gin_trgm_ops);

CREATE INDEX IF NOT EXISTS idx_rel_type_trgm
    ON entity_relationships USING GIN (relationship_type gin_trgm_ops);

-- ── Traversal (add only if not already present) ───
CREATE INDEX IF NOT EXISTS idx_rel_from_entity
    ON entity_relationships (from_entity_id);

CREATE INDEX IF NOT EXISTS idx_rel_to_entity
    ON entity_relationships (to_entity_id);

CREATE INDEX IF NOT EXISTS idx_rel_source_doc
    ON entity_relationships (source_document_id);

-- ── Entity type filtering ─────────────────────────
CREATE INDEX IF NOT EXISTS idx_entity_type
    ON entities (type);

-- ── Entity-document join ──────────────────────────
CREATE INDEX IF NOT EXISTS idx_entdoc_entity
    ON entity_documents (entity_id);

CREATE INDEX IF NOT EXISTS idx_entdoc_document
    ON entity_documents (document_id);
```

---

## 4. FastAPI — API Specification

All endpoints are prefixed with `/api/v1/graph`. Responses use standard JSON. Pydantic models enforce request/response schemas.

### 4.1 Pydantic Models

```python
from pydantic import BaseModel
from uuid import UUID
from datetime import datetime
from typing import Optional
from enum import Enum

# ── Enums ──────────────────────────────────────────

class SearchResultType(str, Enum):
    entity = "entity"
    relationship = "relationship"

# ── Entity (Node) ─────────────────────────────────

class EntityRead(BaseModel):
    """Full entity detail for the side panel."""
    id: UUID
    name: str
    type: str
    document_count: int                 # COUNT from entity_documents
    documents: list["DocumentSummary"]  # source docs this entity appears in

class EntitySummary(BaseModel):
    """Lightweight entity for graph rendering (Cytoscape node data)."""
    id: UUID
    name: str
    type: str

# ── Relationship (Edge) ───────────────────────────

class RelationshipRead(BaseModel):
    """Full relationship detail for the side panel."""
    id: UUID
    from_entity: EntitySummary
    to_entity: EntitySummary
    relationship_type: str
    source_document: "DocumentSummary"

class RelationshipSummary(BaseModel):
    """Lightweight relationship for graph rendering (Cytoscape edge data)."""
    id: UUID
    from_entity_id: UUID
    to_entity_id: UUID
    relationship_type: str
    source_document_id: UUID

# ── Document ──────────────────────────────────────

class DocumentSummary(BaseModel):
    id: UUID
    title: str

# ── Search ────────────────────────────────────────

class SearchHit(BaseModel):
    id: UUID
    label: str                          # entity.name or relationship_type
    type: str                           # entity.type or "relationship"
    result_type: SearchResultType       # "entity" or "relationship"
    similarity: float                   # 0.0–1.0 trigram score

class SearchResponse(BaseModel):
    query: str
    total: int
    results: list[SearchHit]

# ── Graph / Neighborhood ──────────────────────────

class NeighborhoodResponse(BaseModel):
    """Everything needed to render a subgraph in Cytoscape.js."""
    entities: list[EntitySummary]
    relationships: list[RelationshipSummary]
    center_entity_id: UUID
```

---

### 4.2 Endpoint Reference

---

#### `GET /api/v1/graph/search`

Unified fuzzy search across entities (by name) and relationships (by relationship_type).

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `q` | `str` | *required* | Search query string |
| `result_type` | `str \| null` | `null` | Filter: `"entity"` or `"relationship"` |
| `entity_type` | `str \| null` | `null` | Filter entities by type (e.g. `"Person"`) |
| `limit` | `int` | `20` | Max results (capped at 100) |
| `threshold` | `float` | `0.3` | Minimum trigram similarity score |

**SQL logic:**

```sql
-- Entities matching by name
SELECT id, name AS label, type, 'entity' AS result_type,
       similarity(name, :q) AS sim
FROM entities
WHERE name % :q

UNION ALL

-- Relationships matching by relationship_type
SELECT r.id, r.relationship_type AS label,
       'relationship' AS type,
       'relationship' AS result_type,
       similarity(r.relationship_type, :q) AS sim
FROM entity_relationships r
WHERE r.relationship_type % :q

ORDER BY sim DESC
LIMIT :limit;
```

**Response:** `SearchResponse`

---

#### `GET /api/v1/graph/entities/{entity_id}`

Fetch full entity detail including linked documents (via `entity_documents`).

**SQL logic:**

```sql
-- Entity base
SELECT id, name, type FROM entities WHERE id = :entity_id;

-- Linked documents
SELECT d.id, d.title
FROM document d
JOIN entity_documents ed ON ed.document_id = d.id
WHERE ed.entity_id = :entity_id;
```

**Response:** `EntityRead`

---

#### `GET /api/v1/graph/entities/{entity_id}/neighborhood`

Fetch the 1-hop neighborhood: the entity itself, all directly related entities, and the relationships between them.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `depth` | `int` | `1` | Traversal depth (1 or 2; cap at 2) |
| `limit` | `int` | `50` | Max neighbor entities returned |

**SQL logic (depth=1):**

```sql
-- Get all relationships touching this entity
WITH relevant_rels AS (
    SELECT id, from_entity_id, to_entity_id,
           relationship_type, source_document_id
    FROM entity_relationships
    WHERE from_entity_id = :entity_id
       OR to_entity_id   = :entity_id
    LIMIT :limit
),
-- Collect all entity IDs from those relationships
neighbor_ids AS (
    SELECT DISTINCT unnest(
        ARRAY[from_entity_id, to_entity_id]
    ) AS eid
    FROM relevant_rels
)
-- Return entities
SELECT e.id, e.name, e.type
FROM entities e
JOIN neighbor_ids ni ON e.id = ni.eid;

-- Return relationships (from relevant_rels CTE)
SELECT id, from_entity_id, to_entity_id,
       relationship_type, source_document_id
FROM relevant_rels;
```

**Response:** `NeighborhoodResponse`

---

#### `GET /api/v1/graph/relationships/{relationship_id}`

Fetch full relationship detail including both endpoint entities and the source document.

**SQL logic:**

```sql
SELECT r.id, r.relationship_type, r.source_document_id,
       e1.id AS from_id, e1.name AS from_name, e1.type AS from_type,
       e2.id AS to_id,   e2.name AS to_name,   e2.type AS to_type,
       d.id  AS doc_id,  d.title AS doc_title
FROM entity_relationships r
JOIN entities e1 ON e1.id = r.from_entity_id
JOIN entities e2 ON e2.id = r.to_entity_id
JOIN document d  ON d.id  = r.source_document_id
WHERE r.id = :relationship_id;
```

**Response:** `RelationshipRead`

---

#### `GET /api/v1/graph/entities/{entity_id}/relationships`

List all relationships connected to an entity (for the side panel "connections" tab).

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `direction` | `str` | `"both"` | `"from"`, `"to"`, or `"both"` |
| `limit` | `int` | `50` | Max relationships returned |

**SQL logic:**

```sql
SELECT r.id, r.from_entity_id, r.to_entity_id,
       r.relationship_type, r.source_document_id,
       -- Include the "other" entity's name for display
       CASE
         WHEN r.from_entity_id = :entity_id THEN e2.name
         ELSE e1.name
       END AS other_entity_name
FROM entity_relationships r
JOIN entities e1 ON e1.id = r.from_entity_id
JOIN entities e2 ON e2.id = r.to_entity_id
WHERE (:direction = 'both' AND (r.from_entity_id = :entity_id
                             OR r.to_entity_id = :entity_id))
   OR (:direction = 'from' AND r.from_entity_id = :entity_id)
   OR (:direction = 'to'   AND r.to_entity_id   = :entity_id)
ORDER BY r.relationship_type
LIMIT :limit;
```

**Response:** `list[RelationshipSummary]`

---

#### `GET /api/v1/graph/entities/{entity_id}/documents`

List all documents an entity appears in (via `entity_documents`).

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `limit` | `int` | `50` | Max documents returned |

**SQL logic:**

```sql
SELECT d.id, d.title
FROM document d
JOIN entity_documents ed ON ed.document_id = d.id
WHERE ed.entity_id = :entity_id
ORDER BY d.title
LIMIT :limit;
```

**Response:** `list[DocumentSummary]`

---

#### `POST /api/v1/graph/subgraph`

Batch-fetch a subgraph for multiple entity IDs (used when expanding several entities at once or loading a saved view).

**Request body:**

```python
class SubgraphRequest(BaseModel):
    entity_ids: list[UUID]        # up to 50
    include_relationships: bool = True
```

**SQL logic:**

```sql
-- Return all requested entities
SELECT id, name, type
FROM entities
WHERE id = ANY(:entity_ids);

-- Return inter-relationships between the requested entities
SELECT id, from_entity_id, to_entity_id,
       relationship_type, source_document_id
FROM entity_relationships
WHERE from_entity_id = ANY(:entity_ids)
  AND to_entity_id   = ANY(:entity_ids);
```

**Response:** `NeighborhoodResponse`

---

#### `GET /api/v1/graph/documents/{document_id}/entities`

List all entities extracted from a specific document. Useful for "show me everything from this document" exploration.

**SQL logic:**

```sql
SELECT e.id, e.name, e.type
FROM entities e
JOIN entity_documents ed ON ed.entity_id = e.id
WHERE ed.document_id = :document_id;
```

**Response:** `list[EntitySummary]`

---

#### `GET /api/v1/graph/documents/{document_id}/subgraph`

Fetch the full subgraph for a document: all entities from that document and all relationships sourced from it.

**SQL logic:**

```sql
-- Entities linked to the document
SELECT e.id, e.name, e.type
FROM entities e
JOIN entity_documents ed ON ed.entity_id = e.id
WHERE ed.document_id = :document_id;

-- Relationships sourced from the document
SELECT id, from_entity_id, to_entity_id,
       relationship_type, source_document_id
FROM entity_relationships
WHERE source_document_id = :document_id;
```

**Response:** `NeighborhoodResponse`

---

### 4.3 Endpoint Summary Table

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/graph/search` | Fuzzy search entities + relationships |
| `GET` | `/api/v1/graph/entities/{id}` | Full entity with documents |
| `GET` | `/api/v1/graph/entities/{id}/neighborhood` | 1-hop entity graph |
| `GET` | `/api/v1/graph/entities/{id}/relationships` | Entity's connections |
| `GET` | `/api/v1/graph/entities/{id}/documents` | Entity's source documents |
| `GET` | `/api/v1/graph/relationships/{id}` | Full relationship detail |
| `POST` | `/api/v1/graph/subgraph` | Batch subgraph for entity IDs |
| `GET` | `/api/v1/graph/documents/{id}/entities` | All entities from a doc |
| `GET` | `/api/v1/graph/documents/{id}/subgraph` | Full doc subgraph |

---

### 4.4 FastAPI Router Structure

```
app/
├── routers/
│   └── graph/
│       ├── __init__.py
│       ├── router.py          # APIRouter with prefix="/api/v1/graph"
│       ├── schemas.py         # All Pydantic models from §4.1
│       ├── service.py         # Business logic (neighborhood expansion, search)
│       └── queries.py         # Raw SQL or SQLAlchemy query builders
```

---

## 5. Vue 3 + Cytoscape.js Integration

### 5.1 Installation

```bash
npm install cytoscape cytoscape-cose-bilkent
```

### 5.2 Composable: `useCytoscape`

The key pattern is a Vue composable that manages the Cytoscape instance lifecycle, tied to a template ref for the container DOM element. This avoids any third-party Vue wrapper.

```typescript
// composables/useCytoscape.ts
import { ref, onMounted, onBeforeUnmount, watch, type Ref } from 'vue'
import cytoscape, { type Core, type ElementDefinition } from 'cytoscape'
import coseBilkent from 'cytoscape-cose-bilkent'

// Register layout extension once
cytoscape.use(coseBilkent)

export interface UseCytoscapeOptions {
  container: Ref<HTMLElement | null>
  elements: Ref<ElementDefinition[]>
  onEntitySelect?: (entityId: string) => void
  onRelationshipSelect?: (relId: string) => void
  onEntityExpand?: (entityId: string) => void
}

export function useCytoscape(options: UseCytoscapeOptions) {
  const cy = ref<Core | null>(null)

  // ── Style definitions ──────────────────────────
  const graphStyle: cytoscape.Stylesheet[] = [
    {
      selector: 'node',
      style: {
        'label': 'data(name)',
        'width': 'mapData(degree, 1, 10, 30, 80)',
        'height': 'mapData(degree, 1, 10, 30, 80)',
        'font-size': '12px',
        'text-valign': 'bottom',
        'text-margin-y': 8,
        'color': '#374151',
      }
    },
    {
      selector: 'edge',
      style: {
        'width': 2,
        'line-color': '#D1D5DB',
        'target-arrow-color': '#D1D5DB',
        'target-arrow-shape': 'triangle',
        'curve-style': 'bezier',
        'label': 'data(relationship_type)',
        'font-size': '10px',
        'text-rotation': 'autorotate',
      }
    },
    {
      selector: ':selected',
      style: {
        'border-width': 3,
        'border-color': '#2563EB',
        'background-color': '#3B82F6',
      }
    },
    {
      selector: 'node.highlighted',
      style: {
        'background-color': '#F59E0B',
        'border-width': 2,
        'border-color': '#D97706',
      }
    }
  ]

  // ── Initialize ─────────────────────────────────
  function init() {
    if (!options.container.value) return

    cy.value = cytoscape({
      container: options.container.value,
      elements: options.elements.value,
      style: graphStyle,
      layout: {
        name: 'cose-bilkent',
        animate: 'end',
        animationDuration: 500,
      },
      minZoom: 0.2,
      maxZoom: 5,
      wheelSensitivity: 0.3,
    })

    // ── Event bindings ────────────────────────────
    // Single click on entity node
    cy.value.on('tap', 'node', (evt) => {
      options.onEntitySelect?.(evt.target.id())
    })

    // Single click on relationship edge
    cy.value.on('tap', 'edge', (evt) => {
      options.onRelationshipSelect?.(evt.target.id())
    })

    // Double-click to expand neighborhood
    cy.value.on('dbltap', 'node', (evt) => {
      options.onEntityExpand?.(evt.target.id())
    })

    // Click canvas background to deselect
    cy.value.on('tap', (evt) => {
      if (evt.target === cy.value) {
        options.onEntitySelect?.('')  // signal deselection
      }
    })
  }

  // ── Public methods ─────────────────────────────
  function addElements(elements: ElementDefinition[]) {
    if (!cy.value) return
    cy.value.add(elements)
    runLayout()
  }

  function runLayout() {
    cy.value?.layout({
      name: 'cose-bilkent',
      animate: 'end',
      animationDuration: 500,
      fit: true,
    }).run()
  }

  function focusEntity(entityId: string) {
    if (!cy.value) return
    const node = cy.value.getElementById(entityId)
    cy.value.animate({
      center: { eles: node },
      zoom: 2,
    }, { duration: 400 })
    node.select()
  }

  function resetView() {
    cy.value?.fit(undefined, 50)
  }

  function clearGraph() {
    cy.value?.elements().remove()
  }

  // ── Reactive element updates ───────────────────
  watch(options.elements, (newElements) => {
    if (!cy.value) return
    cy.value.elements().remove()
    cy.value.add(newElements)
    runLayout()
  }, { deep: true })

  // ── Lifecycle ──────────────────────────────────
  onMounted(() => init())
  onBeforeUnmount(() => {
    cy.value?.destroy()
    cy.value = null
  })

  return {
    cy,
    addElements,
    focusEntity,
    resetView,
    runLayout,
    clearGraph,
  }
}
```

### 5.3 Data Transformer Utility

Converts API response shapes into Cytoscape's `ElementDefinition[]` format:

```typescript
// utils/graphTransform.ts
import type { ElementDefinition } from 'cytoscape'
import type { EntitySummary, RelationshipSummary } from '@/types/graph'

// Color map for entity types
const entityTypeColors: Record<string, string> = {
  Person:       '#4F46E5',
  Company:      '#059669',
  Organization: '#059669',
  Document:     '#D97706',
  Location:     '#DC2626',
  Event:        '#7C3AED',
}

export function transformToCytoscapeElements(
  entities: EntitySummary[],
  relationships: RelationshipSummary[]
): ElementDefinition[] {

  const cyNodes: ElementDefinition[] = entities.map((e) => ({
    group: 'nodes' as const,
    data: {
      id: e.id,
      name: e.name,           // mapped to 'label' style via data(name)
      type: e.type,
      color: entityTypeColors[e.type] || '#6B7280',
    },
  }))

  const cyEdges: ElementDefinition[] = relationships.map((r) => ({
    group: 'edges' as const,
    data: {
      id: r.id,
      source: r.from_entity_id,       // Cytoscape uses 'source'
      target: r.to_entity_id,         // Cytoscape uses 'target'
      relationship_type: r.relationship_type,
      source_document_id: r.source_document_id,
    },
  }))

  return [...cyNodes, ...cyEdges]
}
```

### 5.4 Graph Explorer Component

```vue
<!-- components/GraphExplorer.vue -->
<script setup lang="ts">
import { ref, computed } from 'vue'
import { useCytoscape } from '@/composables/useCytoscape'
import { useGraphStore } from '@/stores/graphStore'
import { transformToCytoscapeElements } from '@/utils/graphTransform'
import SearchBar from './SearchBar.vue'
import DetailPanel from './DetailPanel.vue'
import GraphControls from './GraphControls.vue'

const graphStore = useGraphStore()
const containerRef = ref<HTMLElement | null>(null)

// Transform API data into Cytoscape element format
const elements = computed(() =>
  transformToCytoscapeElements(
    graphStore.entities,
    graphStore.relationships
  )
)

// Initialize Cytoscape via composable
const { focusEntity, resetView, runLayout } = useCytoscape({
  container: containerRef,
  elements,
  onEntitySelect: (id) => {
    if (id) graphStore.selectEntity(id)
    else graphStore.clearSelection()
  },
  onRelationshipSelect: (id) => graphStore.selectRelationship(id),
  onEntityExpand: (id) => graphStore.expandEntity(id),
})
</script>

<template>
  <div class="graph-explorer">
    <!-- Search bar (top) -->
    <SearchBar
      class="graph-explorer__search"
      @select="(id, type) =>
        graphStore.handleSearchSelect(id, type, focusEntity)"
    />

    <!-- Graph canvas (center) -->
    <div ref="containerRef" class="graph-explorer__canvas" />

    <!-- Controls (bottom-left overlay) -->
    <GraphControls
      class="graph-explorer__controls"
      @fit="resetView"
      @relayout="runLayout"
    />

    <!-- Detail side panel (right) -->
    <DetailPanel
      v-if="graphStore.selectedElement"
      class="graph-explorer__panel"
      :element="graphStore.selectedElement"
      :element-type="graphStore.selectedType"
      @close="graphStore.clearSelection"
    />
  </div>
</template>

<style scoped>
.graph-explorer {
  position: relative;
  width: 100%;
  height: 100vh;
  display: grid;
  grid-template-columns: 1fr auto;
  grid-template-rows: auto 1fr;
}

.graph-explorer__search {
  grid-column: 1 / -1;
  z-index: 10;
}

.graph-explorer__canvas {
  grid-column: 1;
  grid-row: 2;
  min-height: 0; /* critical for Cytoscape to size correctly */
}

.graph-explorer__controls {
  position: absolute;
  bottom: 1rem;
  left: 1rem;
  z-index: 10;
}

.graph-explorer__panel {
  grid-column: 2;
  grid-row: 2;
  width: 360px;
  border-left: 1px solid #e5e7eb;
  overflow-y: auto;
}
</style>
```

### 5.5 Pinia Store

```typescript
// stores/graphStore.ts
import { defineStore } from 'pinia'
import { ref } from 'vue'
import { graphApi } from '@/api/graph'
import type {
  EntitySummary, RelationshipSummary,
  EntityRead, RelationshipRead
} from '@/types/graph'

export const useGraphStore = defineStore('graph', () => {
  // ── Graph data ────────────────────────────
  const entities = ref<EntitySummary[]>([])
  const relationships = ref<RelationshipSummary[]>([])

  // ── Selection state ───────────────────────
  const selectedElement = ref<EntityRead | RelationshipRead | null>(null)
  const selectedType = ref<'entity' | 'relationship' | null>(null)

  // ── Actions ───────────────────────────────
  async function selectEntity(entityId: string) {
    selectedType.value = 'entity'
    selectedElement.value = await graphApi.getEntity(entityId)
  }

  async function selectRelationship(relId: string) {
    selectedType.value = 'relationship'
    selectedElement.value = await graphApi.getRelationship(relId)
  }

  function clearSelection() {
    selectedElement.value = null
    selectedType.value = null
  }

  async function expandEntity(entityId: string) {
    const neighborhood = await graphApi.getNeighborhood(entityId)

    // Merge without duplicates
    const existingEntityIds = new Set(entities.value.map((e) => e.id))
    const existingRelIds = new Set(relationships.value.map((r) => r.id))

    entities.value.push(
      ...neighborhood.entities.filter((e) => !existingEntityIds.has(e.id))
    )
    relationships.value.push(
      ...neighborhood.relationships.filter((r) => !existingRelIds.has(r.id))
    )
  }

  async function handleSearchSelect(
    id: string,
    type: 'entity' | 'relationship',
    focusFn: (id: string) => void
  ) {
    if (type === 'entity') {
      await expandEntity(id)
      focusFn(id)
      await selectEntity(id)
    } else {
      await selectRelationship(id)
    }
  }

  return {
    entities, relationships, selectedElement, selectedType,
    selectEntity, selectRelationship, clearSelection,
    expandEntity, handleSearchSelect,
  }
})
```

---

## 6. Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                     Vue.js 3 Frontend                   │
│                                                         │
│  ┌────────────┐  ┌────────────────────┐  ┌───────────┐ │
│  │ SearchBar  │  │   GraphExplorer    │  │  Detail   │ │
│  │ (fuzzy     │  │   <div ref>        │  │  Panel    │ │
│  │  input)    │  │   └ cytoscape()    │  │  (props)  │ │
│  └─────┬──────┘  └────────┬───────────┘  └─────▲─────┘ │
│        │                  │                    │       │
│        ▼                  ▼                    │       │
│      Pinia Store  ←──── useCytoscape() ────────┘       │
│        │            (composable)                        │
└────────┼────────────────────────────────────────────────┘
         │  Axios / fetch
         ▼
┌────────────────────────────────────────────────────────┐
│                  FastAPI Backend                        │
│                                                        │
│  GET  /api/v1/graph/search?q=...                       │
│  GET  /api/v1/graph/entities/{id}                      │
│  GET  /api/v1/graph/entities/{id}/neighborhood         │
│  GET  /api/v1/graph/entities/{id}/relationships        │
│  GET  /api/v1/graph/entities/{id}/documents            │
│  GET  /api/v1/graph/relationships/{id}                 │
│  POST /api/v1/graph/subgraph                           │
│  GET  /api/v1/graph/documents/{id}/subgraph            │
│                                                        │
│  router.py → service.py → queries.py (asyncpg / SA)   │
└────────────────────┬───────────────────────────────────┘
                     │
                     ▼
┌────────────────────────────────────────────────────────┐
│                    PostgreSQL                           │
│  entities | entity_relationships | entity_documents     │
│  document | pg_trgm + GIN indexes                      │
└────────────────────────────────────────────────────────┘
```

---

## 7. User Interaction Flow

```
User types in search bar
        │
        ▼
GET /search?q=...&limit=20  ──→  Dropdown shows grouped results
        │                         (Entities section / Relationships section)
        │
User clicks a result
        │
        ├── If ENTITY:
        │     GET /entities/{id}/neighborhood
        │     → Merge entities + relationships into Pinia store
        │     → Cytoscape reactively adds elements & runs layout
        │     → Camera animates to center on selected entity
        │     GET /entities/{id}
        │     → Side panel opens with: name, type, source documents list
        │
        └── If RELATIONSHIP:
              GET /relationships/{id}
              → Side panel opens showing:
                relationship_type, from_entity, to_entity, source document
              → Both endpoint entities highlighted in graph

User double-clicks an entity node in the graph
        │
        GET /entities/{id}/neighborhood
        → New neighbors merge into existing graph
        → Layout re-runs incrementally

User clicks empty canvas
        │
        → Side panel closes, selection cleared
```

---

## 8. Key Implementation Notes

### Cytoscape.js Container Sizing

Cytoscape reads the container's dimensions at init time. The container **must** have an explicit size via CSS before `cytoscape()` is called. Using `min-height: 0` in a grid/flex child and ensuring the parent has a defined height prevents the classic "zero-height canvas" bug.

### Incremental Layout

When expanding an entity's neighborhood, avoid re-laying-out the entire graph from scratch. Use `cy.layout({ ... }).run()` with `fit: false` and `animate: 'end'` so existing nodes hold approximate positions and only new nodes settle in.

### Entity Styling by Type

Define a color map and apply it via a Cytoscape style function using the `data(color)` field set in the transformer:

```typescript
{
  selector: 'node',
  style: {
    'background-color': 'data(color)',
  }
}
```

### Debounced Search

Use VueUse's `useDebounceFn` (or a manual `setTimeout`) to debounce the search input by ~300ms before hitting the API. Display results in a dropdown overlay with keyboard navigation.

### Relationship Deduplication

When merging neighborhoods from multiple expansions, deduplicate by `id` using a `Set` in the Pinia store before pushing to the reactive array.

### Side Panel — Entity Detail

When an entity is selected, the panel should show three sections: **Identity** (name, type), **Source Documents** (fetched from `entity_documents` → `document`), and **Relationships** (fetched from `entity_relationships`).

---

## 9. Development Phases

### Phase 1 — Backend Foundation (Week 1)

- Alembic migration for `pg_trgm` extension and new GIN/B-tree indexes on existing tables.
- Implement FastAPI router with `search`, `entities/{id}`, `entities/{id}/neighborhood`, and `relationships/{id}` endpoints.
- Write pytest tests for each endpoint.

### Phase 2 — Vue Integration & Graph MVP (Weeks 2–3)

- Install `cytoscape` and `cytoscape-cose-bilkent`.
- Build `useCytoscape` composable.
- Build `GraphExplorer` page component with canvas, search bar, and side panel.
- Wire search bar → API → Pinia store → Cytoscape reactive update.
- Implement entity click → side panel with detail + documents.

### Phase 3 — Interactivity & Polish (Week 4)

- Double-click-to-expand neighbors.
- Entity type-based color coding.
- Graph controls: zoom-to-fit, re-layout, reset.
- Keyboard shortcuts: `/` to focus search, `Esc` to close panel.
- Loading spinners, empty states, error handling.
- Document subgraph view (load all entities from a document).

### Phase 4 — Performance & Scale (Week 5)

- Cap visible entities at ~500; add "load more neighbors" affordance.
- Server-side pagination on neighborhood endpoint.
- Add Redis or in-memory LRU caching for hot neighborhoods.
- `EXPLAIN ANALYZE` on critical queries; optimize.

### Phase 5 — Advanced Features (Week 6+)

- Filters panel: toggle entity types and relationship types on/off.
- Shortest path between two selected entities (recursive CTE).
- Export subgraph as PNG (`cy.png()`) or JSON.
- Document-centric view: "Show me the full graph from this document."

---

## 10. Package Summary

```
Frontend (npm):
  cytoscape               ^3.30
  cytoscape-cose-bilkent   ^4.1
  pinia                    ^2      (if not already installed)
  @vueuse/core             ^11     (if not already installed)

Backend (pip):
  fastapi                  existing
  asyncpg / sqlalchemy     existing
  alembic                  existing
  pydantic                 ^2
```

---

## 11. Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| Cytoscape canvas renders at 0x0 | Ensure container has explicit CSS dimensions before init; use `onMounted` + `nextTick`. |
| Large neighborhoods crash browser | Cap `limit` param at 50 neighbors per expansion; paginate server-side. |
| Search returns too many low-quality matches | Tune `pg_trgm.similarity_threshold` (start at 0.3); add type filter chips. |
| Layout thrashing on repeated expansions | Use incremental layout with `fit: false`; batch multiple expansions before re-layout. |
| `vue-cytoscape` wrappers are unmaintained | Direct integration via composable avoids this entirely. |
| Duplicate relationships between same entities from different docs | Group or aggregate in the UI; show doc source as edge tooltip. |
