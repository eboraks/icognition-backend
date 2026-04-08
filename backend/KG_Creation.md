# Knowledge Graph Creation Pipeline

## Overview

The KG pipeline extracts entities and relationships from bookmarked documents, aligns them to schema.org ontology, and persists them as a knowledge graph. It runs as an **independent background task** — decoupled from the content summary pipeline so users get their summary without waiting for KG processing.

## Architecture

```
Document (user bookmarks a page)
    |
    |--- Task 1: Content Summary (user-facing, fast)
    |--- Task 2: Legacy Entity Extraction (filtering)
    |--- Task 3: Embedding Generation (search)
    |--- Task 4: KG Pipeline (this document) <-- independent background task
```

### Files

| File | Role |
|------|------|
| `services/kg_pipeline.py` | Orchestrator — entry point for the background task |
| `services/kg_adapter.py` | Node/edge creation with dedup and Wikidata enrichment |
| `services/schema_alignment_service.py` | Maps raw types to schema.org via embeddings + LLM judge |
| `services/wikidata_service.py` | External API for entity anchoring and property lookup |
| `services/dspy_entity_service.py` | DSPy prompts for entity/relationship extraction |
| `models_kg.py` | SQLModel definitions for all KG tables |
| `scripts/seed_ontology.py` | One-time seeding of canonical schema.org classes/properties |

---

## Pipeline Flow

### Step 1: Entity Extraction (DSPy)

**File:** `dspy_entity_service.py` — `ExtractEntities` signature

Extracts up to 15 entities from document text. Each entity has:
- `name` — entity label
- `type` — one of: person, organization, institution, location, event, technology, product, science, medical_condition, organism, regulation, financial, creative_work, concept
- `description` — 1-sentence role in the document (< 15 words)

Key extraction rules:
- Authors included: individual authors → `person`, editorial boards → `organization`
- Photographers, dates, mastheads are ignored

### Step 2: Relationship Extraction (DSPy)

**File:** `dspy_entity_service.py` — `ExtractEntityRelationships` signature

Extracts up to 20 directed relationships between the extracted entities. Each relationship has:
- `from_entity` — subject entity name
- `to_entity` — object entity name
- `relationship_type` — snake_case label (e.g. `works_for`, `author_of`)

Key extraction rules:
- **Factual accuracy:** Must be explicitly stated in text, no hallucination
- **Neutral language:** `advocates_military_action` not `wants_to_bomb`
- **Direction matters:** from_entity is the subject performing the action
- **No bidirectional dupes:** If A trades_with B, don't also add B trades_with A
- **Reusable types:** General labels like `leads`, `member_of`, `competes_with`

### Step 3: Schema Alignment

**File:** `schema_alignment_service.py`

Maps raw LLM types to canonical schema.org classes and properties.

#### Entity Type Alignment

For each entity, aligns `raw_type` to a `kg_canonical_class` entry:

1. **Cache check** — if this `raw_type` was resolved before at high confidence, return cached result
2. **Embedding search** — query text is `"{raw_type}: {type_description}"` (e.g. `"person: Key individuals, people, human beings"`). This format matches the seed embedding format `"{label}: {description}"` used in `kg_canonical_class` vectors
3. **High confidence (similarity >= 0.85)** — accept directly, cache result
4. **Below 0.85** — LLM judge (Gemini Flash Lite) picks the best class given full entity context (name + raw_type + description + candidate list)

`ENTITY_TYPE_DESCRIPTIONS` provides the stable type descriptions for the embedding query. These mirror the entity type definitions in the extraction prompt.

**Context-dependent types:** `location` is never cached because the LLM judge needs entity context to distinguish Country vs City vs Continent vs Place.

#### Relationship Alignment

For each relationship, aligns `relationship_type` to a canonical property:

1. **Embedding search** — query `kg_canonical_property` (schema.org + previously created properties)
2. **High confidence (>= 0.85)** — accept directly
3. **Below 0.85** — LLM judge picks from three sources:
   - **EXISTING** — pick from schema.org/custom canonical properties
   - **WIKIDATA** — pick a Wikidata property (e.g. P69 "educated at"), persisted for reuse
   - **NEW** — create a new `icognition.ai` property as last resort

#### Property URI Hierarchy

| Source | URI Pattern | Example |
|--------|------------|---------|
| Schema.org | `https://schema.org/{prop}` | `https://schema.org/worksFor` |
| Wikidata | `https://www.wikidata.org/wiki/Property:{id}` | `https://www.wikidata.org/wiki/Property:P69` |
| iCognition | `https://icognition.ai/property/{label}` | `https://icognition.ai/property/trades_with` |

New properties (Wikidata and iCognition) are embedded and inserted into `kg_canonical_property` so future documents can match them via embedding search — the ontology is self-extending.

### Step 4: Node Creation (KG Adapter)

**File:** `kg_adapter.py` — `_find_or_create_node()`

Multi-level dedup strategy to avoid duplicate nodes:

1. **Exact match** — `(label_normalized, schema_type_uri, user_id)` unique index lookup
2. **Semantic match** — embed `"{name} - {description}"`, vector search against existing nodes (cosine similarity >= 0.88)
3. **Wikidata dedup** — search Wikidata by name, get `wikidata_id` (e.g. Q22686 for Trump), check if any existing node has that ID
4. **Create new** — use Wikidata canonical label (e.g. "Donald Trump" instead of "Trump"), store `wikidata_id`, generate embedding

This handles the "Trump" / "Donald Trump" / "President Trump" problem — all resolve to Q22686 and merge into one node.

### Step 5: Edge Creation (KG Adapter)

**File:** `kg_adapter.py` — Phase 2 of `process_document_kg()`

1. Collect all edges that pass dedup check: `(from_node_id, to_node_id, property_uri, source_document_id)`
2. **Batch-embed** all edge texts concurrently: `"{from_label} {property_label} {to_label}"`
3. Insert all `KGEdge` records with embeddings

---

## Database Schema

### Canonical Tables (pre-populated by `seed_ontology.py`)

**`kg_canonical_class`** — Schema.org class reference
- `uri` (unique) — e.g. `https://schema.org/Person`
- `label` — e.g. `Person`
- `description` — e.g. `A person (alive, dead, undead, or fictional).`
- `parent_uri` — schema.org class hierarchy
- `vector` (1536-dim, HNSW index) — embedding of `"{label}: {description}"`

**`kg_canonical_property`** — Schema.org + Wikidata + iCognition properties
- `uri` (unique) — schema.org, Wikidata, or icognition.ai URI
- `label`, `description`
- `domain_class_uri`, `range_class_uri` — optional type constraints
- `vector` (1536-dim, HNSW index)

### Instance Tables (populated during document processing)

**`kg_node`** — Knowledge graph nodes
- `label`, `label_normalized` — display name and dedup key
- `canonical_class_id` (FK → kg_canonical_class) — schema.org class alignment
- `schema_type_uri` — e.g. `https://schema.org/Person`
- `raw_type`, `raw_description` — original LLM output (audit trail)
- `wikidata_id` — e.g. `Q22686` for global entity anchoring
- `vector` (1536-dim) — embedding of `"{name} - {description}"` for semantic dedup
- `user_id` — tenant isolation
- **Unique index:** `(label_normalized, schema_type_uri, user_id)`

**`kg_edge`** — Directed relationships
- `from_node_id`, `to_node_id` (FKs → kg_node)
- `canonical_property_id` (FK → kg_canonical_property)
- `property_uri`, `property_label` — canonical property info
- `raw_relationship_type` — original LLM output
- `source_document_id` — provenance
- `vector` (1536-dim) — embedding for semantic edge search
- **Unique index:** `(from_node_id, to_node_id, property_uri, source_document_id)`

**`kg_node_document`** — Junction table: which documents mention a node
- `(node_id, document_id)` — composite PK

---

## Embedding Format Consistency

The canonical classes/properties are embedded during seeding with the format:
```
"{label}: {description}"
e.g. "Person: A person (alive, dead, undead, or fictional)."
```

The alignment service must use the **same format** for queries to get good similarity scores. Mismatched formats (e.g. bare `"person"` vs `"Person: A person..."`) produce low scores even for obvious matches.

| Context | Format | Example |
|---------|--------|---------|
| Canonical class seed | `"{label}: {description}"` | `"Person: A person (alive, dead, undead, or fictional)."` |
| Class alignment query | `"{raw_type}: {type_description}"` | `"person: Key individuals, people, human beings"` |
| Node semantic dedup | `"{name} - {description}"` | `"Donald Trump - 45th president of the United States"` |
| Edge embedding | `"{from} {property} {to}"` | `"Donald Trump leads United States"` |

---

## Performance Optimizations

1. **Decoupled background task** — KG pipeline doesn't block the user-facing content summary
2. **Class alignment cache** — after first `person` entity resolves at high confidence, all subsequent person entities skip embedding + LLM judge
3. **Batch edge embeddings** — all edge texts embedded concurrently via `asyncio.gather` instead of sequentially
4. **Label normalization** — LLM judge comparison normalizes underscores/spaces to avoid false mismatches

---

## LLM Judge Details

Two LLM judge functions, both using Gemini Flash Lite at temperature 0.0:

### Class Judge (`_llm_judge_class`)
- **Input:** entity name, raw_type, description, top-K candidates from embedding search
- **Output:** one class label or "none"
- **Used for:** location → Country/City/Place distinction, any type below 0.85 confidence

### Relationship Judge (`_llm_judge_relationship`)
- **Input:** from_entity, to_entity, raw relationship type, top-K candidates + Wikidata property search results
- **Output:** one of three formats:
  - `EXISTING: {label}` — use existing canonical property
  - `WIKIDATA: {property_id} | {label}` — use Wikidata property (persisted for reuse)
  - `NEW: {label} | {description}` — create new icognition.ai property
- **Key instructions:** properties must be general, reusable, and use neutral language

---

## Future: Separate Service

`kg_pipeline.py` is designed for extraction into a standalone service:
- Has its own DB session (doesn't share with content pipeline)
- Single entry point: `process_document_kg_background(document_id, user_id)`
- All dependencies are injectable
- Only needs: document content, user_id, access to DB + Gemini API + Wikidata API
