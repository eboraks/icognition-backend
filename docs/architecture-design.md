# OntoExtract: Architecture Design Document

**Version:** 1.0  
**Date:** April 2026  
**Status:** Draft for Architecture Review  

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Problem Statement](#2-problem-statement)
3. [Use Cases](#3-use-cases)
4. [Architecture](#4-architecture)
5. [How the Architecture Addresses the Use Cases](#5-how-the-architecture-addresses-the-use-cases)
6. [Data Model](#6-data-model)
7. [Non-functional Requirements](#7-non-functional-requirements)
8. [Technology Stack](#8-technology-stack)
9. [Risks and Mitigations](#9-risks-and-mitigations)
10. [Comparison with OntoGPT](#10-comparison-with-ontogpt)
11. [Appendices](#11-appendices)

---

## 1. Executive Summary

OntoExtract is a microservice that extracts structured knowledge graphs from unstructured text, grounded to a configurable ontology. Given a document and an ontology (OWL, RDF, or LinkML), it produces typed entities, directed relationships, and links them to canonical ontology classes and properties — building a deduplicated, queryable knowledge graph over time.

The core innovation is a **two-phase alignment approach**: vector similarity search narrows thousands of ontology classes to a handful of candidates, then an LLM judge picks the best match with full semantic context. This avoids the scalability bottleneck of serializing entire ontologies into prompts while maintaining high alignment accuracy.

The service is designed for **batch workloads** (hundreds to thousands of documents), supports **any LLM provider** (OpenAI, Anthropic, Google, local models), and persists results in a **PostgreSQL + pgvector** knowledge graph with 4-stage entity deduplication.

---

## 2. Problem Statement

Extracting structured data from text is a well-understood NLP task. What makes it hard in practice is **ontology alignment at scale**:

1. **The prompt size problem.** Ontologies can have hundreds (schema.org: 800+) to hundreds of thousands (SNOMED-CT: 350K+) of classes. Serializing the full schema into an LLM prompt is infeasible for large ontologies and wasteful for small ones.

2. **The consistency problem.** LLMs produce free-text entity types ("tech company", "software firm", "IT corporation") that must map to a single canonical class (`schema:Organization`). Without alignment, the knowledge graph fragments into synonyms.

3. **The deduplication problem.** Processing multiple documents produces the same real-world entities ("Google", "Google LLC", "Alphabet/Google"). Without dedup, the graph fills with disconnected duplicates.

4. **The LLM portability problem.** Production systems need to switch between LLM providers for cost, latency, quality, or compliance reasons. Hardcoding to one provider creates vendor lock-in.

5. **The batch problem.** Processing thousands of documents sequentially is too slow. But naive parallelism hits LLM rate limits and produces race conditions in graph dedup.

OntoExtract addresses all five problems.

---

## 3. Use Cases

### UC1: Batch Document Extraction

**Actor:** Data engineer operating a document processing pipeline  
**Goal:** Extract a structured knowledge graph from a corpus of 500+ documents, aligned to a domain ontology  

**Flow:**
```
                                                    +-----------+
  +---------+      POST /batch      +----------+    | Worker    |    +------------+
  | Client  | -------------------> | API       | -->| Pool      | -->| PostgreSQL |
  |         | <--- 202 {job_id} -- | (FastAPI) |    | (N async  |    | + pgvector |
  |         |                      +----------+     | workers)  |    +------------+
  |         |      GET /jobs/{id}       |           +-----------+
  |         | -----> progress <---------|
  |         |      GET /jobs/{id}/results
  |         | -----> per-doc outcomes --|
  +---------+                          |
```

1. Client submits documents via `POST /batch`. API returns `202 Accepted` with a `job_id`.
2. Job is enqueued to an async Redis queue.
3. Worker pool processes documents concurrently (configurable parallelism via semaphore).
4. Each document passes through: **extract entities** -> **extract relationships** -> **align to ontology** -> **deduplicate against graph** -> **persist**.
5. Per-document failures are isolated — one document's failure does not abort the batch.
6. Client polls `GET /jobs/{job_id}` for progress and `GET /jobs/{job_id}/results` for outcomes.

**Success criteria:**  
- 100+ documents/hour throughput (with GPT-4o-mini)  
- Zero cross-document contamination  
- Transient LLM errors retried automatically  

---

### UC2: Single Document Extraction

**Actor:** Application integrating OntoExtract via API  
**Goal:** Extract and persist KG triples from a single document, synchronously  

**Flow:**
1. `POST /extract` with document text
2. Pipeline runs inline: chunk -> extract -> align -> dedup -> persist
3. Response includes: nodes created/reused, edges created, canonical type mappings

**Success criteria:** < 30s response time. Entities deduplicated against existing graph.

---

### UC3: Ontology Configuration

**Actor:** Ontology engineer or system administrator  
**Goal:** Load a domain ontology so all subsequent extractions align to it  

**Flow:**
```
                +--------------------+
  Ontology      |  Ontology Loader   |
  File          |                    |       +------------------+
  (.owl/.ttl/   | 1. Parse classes   |       | canonical_class  |
   .yaml)  ---->| 2. Parse properties| ----> | canonical_property|
                | 3. Generate embeds |       | (with vectors)   |
                | 4. Upsert to DB   |       +------------------+
                +--------------------+
```

1. `POST /ontology/load` with an ontology file (OWL, RDF/Turtle, or LinkML YAML)
2. Appropriate parser extracts classes (with hierarchy) and properties (with domain/range)
3. Embeddings are generated for each class and property: `"{label}: {description}"`
4. Canonical tables are seeded via upsert (safe for ontology updates)
5. Subsequent extractions dynamically use the loaded ontology's classes as entity types

**Success criteria:** Any standard OWL, RDF/Turtle, or LinkML ontology loads within minutes.

---

### UC4: Knowledge Graph Query

**Actor:** Application developer, analyst  
**Goal:** Search and explore the accumulated knowledge graph  

**Endpoints:**
- `GET /graph/nodes` — filter by type, paginate
- `GET /graph/nodes/{id}/neighborhood` — 1-hop or 2-hop subgraph
- `GET /graph/search?q=...` — semantic vector search across all nodes
- `POST /graph/subgraph` — extract subgraph for a set of node IDs

**Success criteria:** < 200ms query latency for graphs up to 100K nodes.

---

### UC5: Ontology Evolution

**Actor:** Ontology engineer  
**Goal:** Update the ontology without breaking existing graph data  

**Flow:**
1. Upload a new version of the ontology via `POST /ontology/load`
2. Canonical tables are upserted — new classes added, existing updated, none deleted
3. Existing graph nodes retain their `canonical_class_id` and `schema_type_uri`
4. New extractions align to the updated ontology

**Success criteria:** Zero data loss. Audit trail preserves historical alignment decisions.

---

## 4. Architecture

### 4.1 System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        API Layer                             │
│                      (FastAPI)                               │
│  /extract  /batch  /jobs  /graph  /ontology  /health        │
└────┬──────────┬──────────────┬──────────────────┬───────────┘
     │          │              │                  │
     │    ┌─────▼─────┐  ┌────▼────────┐  ┌──────▼──────────┐
     │    │ Job Queue  │  │ Extraction  │  │ Ontology        │
     │    │ Service    │  │ Pipeline    │  │ Management      │
     │    │            │  │             │  │                 │
     │    │ Redis+ARQ  │  │ Chunk       │  │ Parse OWL/RDF/  │
     │    │ N workers  │  │ Extract     │  │ LinkML          │
     │    │ Semaphore  │  │ Align       │  │ Generate embeds │
     │    │ Retry      │  │ Dedup       │  │ Seed canonical  │
     │    └─────┬──────┘  │ Persist     │  │ tables          │
     │          │         └──────┬──────┘  └────────┬────────┘
     │          │                │                   │
     │          └────────────────┼───────────────────┘
     │                          │
     │         ┌────────────────┼────────────────┐
     │         │                │                │
┌────▼─────┐ ┌─▼────────┐ ┌────▼──────┐ ┌───────▼──────┐
│ Schema   │ │ KG       │ │ Embedding │ │ Wikidata     │
│ Alignment│ │ Adapter  │ │ Service   │ │ Service      │
│ Service  │ │          │ │           │ │              │
│          │ │ 4-stage  │ │ LiteLLM   │ │ Entity       │
│ Vector   │ │ dedup    │ │ aembedding│ │ anchoring    │
│ search + │ │ + audit  │ │ batch     │ │ via Wikidata │
│ LLM judge│ │ trail    │ │ async     │ │ API          │
└────┬─────┘ └────┬─────┘ └─────┬─────┘ └───────┬─────┘
     │            │              │                │
     └────────────┼──────────────┼────────────────┘
                  │              │
       ┌──────────▼──────────────▼──────────────┐
       │           Data Layer                    │
       │       PostgreSQL + pgvector             │
       │                                        │
       │  canonical_class  │  kg_node           │
       │  canonical_property│  kg_edge           │
       │  document         │  kg_node_document   │
       │  extraction_job   │  extraction_result  │
       │  ontology_config  │                     │
       │                                        │
       │  HNSW vector indexes (cosine)          │
       └────────────────────────────────────────┘
                  │
       ┌──────────▼────────────────────────────┐
       │        External Integrations           │
       │                                       │
       │  LiteLLM ──> OpenAI / Anthropic /     │
       │              Gemini / Ollama / Groq    │
       │                                       │
       │  Wikidata API ──> Entity anchoring    │
       └───────────────────────────────────────┘
```

### 4.2 Extraction Pipeline

This is the core of the system — the sequence of steps that transforms raw text into ontology-aligned knowledge graph triples.

```
┌──────────────┐
│ Raw Document │
│ (text/HTML)  │
└──────┬───────┘
       │
       ▼
┌──────────────────┐     Docs exceeding LLM context window
│ 1. CHUNK         │     are split into overlapping sentence
│    (if needed)   │     windows. Short docs pass through.
└──────┬───────────┘
       │
       ▼
┌──────────────────┐     DSPy signature with entity types
│ 2. EXTRACT       │     dynamically derived from loaded
│    ENTITIES      │     ontology. Up to 15 per document.
│                  │     Output: [{name, type, description}]
└──────┬───────────┘
       │
       ▼
┌──────────────────┐     Only runs if >= 2 entities found.
│ 3. EXTRACT       │     Constrained to extracted entities.
│    RELATIONSHIPS │     Up to 20 per document.
│                  │     Output: [{from, to, relationship}]
└──────┬───────────┘
       │
       ▼
┌──────────────────┐
│ 4. SCHEMA        │──── The key innovation (see 4.3 below)
│    ALIGNMENT     │
│                  │     Maps raw types → canonical classes
│                  │     Maps raw labels → canonical properties
└──────┬───────────┘
       │
       ▼
┌──────────────────┐     4-stage deduplication ensures the
│ 5. DEDUPLICATE   │     same real-world entity is never
│    & PERSIST     │     duplicated in the graph.
│                  │
│    kg_node       │     Raw LLM output preserved alongside
│    kg_edge       │     canonical mapping (audit trail).
│    kg_node_doc   │
└──────────────────┘
```

### 4.3 Schema Alignment — The Core Innovation

The central challenge: an LLM might extract an entity typed as `"tech company"`, `"software firm"`, or `"IT corporation"`. All three should map to the same canonical class (e.g., `schema:Organization` or a domain-specific `SoftwareCompany`).

**The naive approach** (used by OntoGPT's SPIRES) serializes the entire ontology into the LLM prompt and asks it to pick the right class. This works for ontologies with tens of classes, but fails for large ontologies:

```
❌  Naive: Serialize 800 classes into prompt → prompt overflow, high cost
```

**OntoExtract's approach** uses a two-phase strategy:

```
┌─────────────────────────────────────────────────────┐
│                SCHEMA ALIGNMENT                      │
│                                                     │
│  Raw type: "tech company"                           │
│         │                                           │
│         ▼                                           │
│  ┌─────────────────┐                                │
│  │ Phase 1: EMBED  │  Generate embedding for        │
│  │ & SEARCH        │  "{type}: {description}"       │
│  │                 │                                │
│  │  Vector search  │  Query HNSW index over all     │
│  │  canonical_class│  canonical classes (cosine)    │
│  │  table          │                                │
│  │                 │  Returns top-K candidates       │
│  │                 │  with similarity scores         │
│  └────────┬────────┘                                │
│           │                                         │
│           ▼                                         │
│  ┌────────────────────────────────────────────┐     │
│  │ Phase 2: CONFIDENCE ROUTING                │     │
│  │                                            │     │
│  │  score >= 0.85 ──► AUTO-ACCEPT             │     │
│  │                    No LLM call needed.     │     │
│  │                    Cache for future reuse. │     │
│  │                                            │     │
│  │  0.50 <= score < 0.85 ──► LLM JUDGE       │     │
│  │                    Send entity context +   │     │
│  │                    top-K candidates to LLM.│     │
│  │                    LLM picks best match.   │     │
│  │                                            │     │
│  │  score < 0.50 ──► UNMATCHED               │     │
│  │                    Too far off. Mark as    │     │
│  │                    unmatched (null).       │     │
│  └────────────────────────────────────────────┘     │
│                                                     │
│  For relationships: same flow, but also queries     │
│  Wikidata properties as additional candidates.      │
│  LLM judge can choose: EXISTING / WIKIDATA / NEW   │
└─────────────────────────────────────────────────────┘
```

**Why this works at scale:**

| Property | Prompt serialization | Embedding + LLM judge |
|---|---|---|
| Prompt size | Grows with ontology | Constant (only top-K) |
| Ontology scale | Breaks at 100s of classes | Handles 100K+ via HNSW index |
| LLM cost per entity | One large call (full schema) | Zero for high-confidence; one small call for moderate |
| Similarity signal | Binary (match/no match) | Continuous score (0.0-1.0) |

**The LLM judge** is only invoked for ambiguous cases (moderate confidence). For a typical extraction run, 60-70% of alignments are high-confidence (auto-accepted), 25-30% go to the judge, and <5% are unmatched.

### 4.4 Four-Stage Entity Deduplication

Processing multiple documents inevitably produces references to the same real-world entity. OntoExtract uses a progressive dedup strategy that balances precision and recall:

```
┌───────────────────────────────────────────────────────────────┐
│                  ENTITY DEDUPLICATION                          │
│                                                               │
│  Input: entity {name: "Google LLC", type: "Organization"}     │
│                                                               │
│  Stage 1: EXACT MATCH                                         │
│  ┌─────────────────────────────────────────────┐              │
│  │ Query: (normalize("google llc"), "Organization") │         │
│  │ Method: UNIQUE index lookup — O(1)              │         │
│  │ Match? → Reuse existing node                    │         │
│  └──────────────────────┬──────────────────────┘              │
│                         │ no match                            │
│                         ▼                                     │
│  Stage 2: SEMANTIC MATCH                                      │
│  ┌─────────────────────────────────────────────┐              │
│  │ Embed "Google LLC - Technology company"         │         │
│  │ Vector search: similarity >= 0.88               │         │
│  │ Method: HNSW index — O(log N)                   │         │
│  │ Catches: "Google" vs "Google LLC" vs "Google Inc"│        │
│  │ Match? → Reuse existing node                    │         │
│  └──────────────────────┬──────────────────────┘              │
│                         │ no match                            │
│                         ▼                                     │
│  Stage 3: WIKIDATA MATCH                                      │
│  ┌─────────────────────────────────────────────┐              │
│  │ Search Wikidata API for "Google LLC"            │         │
│  │ Get wikidata_id (e.g., Q95)                     │         │
│  │ Check if any existing node has wikidata_id=Q95  │         │
│  │ Match? → Reuse existing node                    │         │
│  └──────────────────────┬──────────────────────┘              │
│                         │ no match                            │
│                         ▼                                     │
│  Stage 4: CREATE NEW                                          │
│  ┌─────────────────────────────────────────────┐              │
│  │ Insert new KGNode with:                         │         │
│  │   - embedding (for future semantic dedup)       │         │
│  │   - canonical_class_id (from schema alignment)  │         │
│  │   - wikidata_id (for future Wikidata dedup)     │         │
│  │   - raw_type + raw_description (audit trail)    │         │
│  └─────────────────────────────────────────────┘              │
└───────────────────────────────────────────────────────────────┘
```

### 4.5 Batch Processing Architecture

```
Client                 API               Redis/ARQ           Worker Pool         PostgreSQL
  │                     │                    │                    │                    │
  │── POST /batch ────>│                    │                    │                    │
  │                     │── create job ────>│                    │                    │
  │                     │                    │                    │                    │──> extraction_job
  │                     │── enqueue ───────>│                    │                    │
  │<── 202 {job_id} ──│                    │                    │                    │
  │                     │                    │── dequeue ───────>│                    │
  │                     │                    │                    │                    │
  │                     │                    │     ┌─────────────┤                    │
  │                     │                    │     │ Semaphore   │                    │
  │                     │                    │     │ (N=5)       │                    │
  │                     │                    │     │             │                    │
  │                     │                    │     │ doc1 ──────>│── pipeline ──────>│
  │                     │                    │     │ doc2 ──────>│── pipeline ──────>│
  │                     │                    │     │ doc3 ──────>│── pipeline ──────>│
  │                     │                    │     │ doc4 ──────>│── pipeline ──────>│
  │                     │                    │     │ doc5 ──────>│── pipeline ──────>│
  │                     │                    │     │ (doc6 waits)│                    │
  │                     │                    │     └─────────────┤                    │
  │                     │                    │                    │                    │
  │── GET /jobs/{id} ─>│                    │                    │                    │
  │<── {progress} ────│── read progress ──>│                    │                    │
  │                     │                    │                    │── update job ────>│
  │── GET /jobs/{id} ─>│                    │                    │                    │
  │<── {completed} ───│                    │                    │                    │
```

**Concurrency controls:**
- `BATCH_CONCURRENCY` (default: 5): Documents processed concurrently per worker via `asyncio.Semaphore`
- `ARQ_WORKERS` (default: 3): Independent worker processes (horizontally scalable)
- `EMBED_BATCH_SIZE` (default: 20): Embeddings generated concurrently per batch
- Rate limit backoff: Exponential retry (3 attempts, base=2s) on HTTP 429/503

**Error isolation:** Each document is processed in an independent try/except. Transient errors trigger retry; permanent errors are logged and the document is skipped. The job completes as `PARTIALLY_FAILED` if some documents fail.

### 4.6 LLM Provider Abstraction

OntoExtract uses **LiteLLM** as a universal adapter, ensuring no vendor lock-in:

```
┌──────────────────────────────────┐
│        OntoExtract Services       │
│                                  │
│  Extraction ─> DSPy ─┐          │
│                       ├─> LiteLLM ─┬─> OpenAI (gpt-4o-mini)
│  Alignment  ─> LLM  ─┤            ├─> Anthropic (claude-sonnet)
│    Judge     Service  │            ├─> Google (gemini-flash)
│                       │            ├─> Ollama (llama3, local)
│  Embeddings ─────────┘            └─> Groq (llama-3.3-70b)
└──────────────────────────────────┘
```

Three independently configurable model slots:

| Slot | Purpose | Default | Notes |
|---|---|---|---|
| `LLM_EXTRACTION_MODEL` | Entity + relationship extraction | `openai/gpt-4o-mini` | High-volume, cost-sensitive |
| `LLM_JUDGE_MODEL` | Schema alignment re-ranking | `openai/gpt-4o-mini` | Short prompts, low tokens |
| `LLM_EMBEDDING_MODEL` | All vector embeddings | `openai/text-embedding-3-small` | Must be consistent across ontology load and alignment |

**Switching providers** requires only changing environment variables — no code changes.

### 4.7 Ontology Integration

Three parser backends produce a unified representation:

```
                    ┌────────────────┐
  .owl ──> rdflib ──┤                │
                    │  Unified       │──> Generate ──> Upsert to
  .ttl ──> rdflib ──┤  OntologyClass │    Embeddings   canonical_class
                    │  OntologyProp  │                 canonical_property
  .yaml ─> linkml ──┤                │
                    └────────────────┘
```

| Format | Parser | Typical Use |
|---|---|---|
| OWL/XML | rdflib | Enterprise/biomedical (SNOMED, FIBO, Gene Ontology) |
| RDF/Turtle | rdflib | Schema.org, Dublin Core, FOAF |
| LinkML/YAML | linkml-runtime | Custom domain schemas, rapid prototyping |

**Schema-driven extraction:** Once loaded, the ontology's class labels are injected into the extraction prompt. Loading a biomedical ontology with classes `[Drug, Disease, Gene, Protein, ClinicalTrial]` would constrain the extractor to those types — not a generic list.

---

## 5. How the Architecture Addresses the Use Cases

### UC1 (Batch Extraction) → Job Queue + Pipeline + Dedup

| Requirement | Architectural solution |
|---|---|
| Process 500+ documents | ARQ job queue with N async workers (Section 4.5) |
| Throughput over latency | `asyncio.Semaphore` for configurable parallelism |
| No cross-doc contamination | Per-document error isolation in independent try/except |
| Transient error recovery | Exponential backoff retry (3 attempts) on 429/503 |
| Progress visibility | Redis hash for real-time progress, `GET /jobs/{id}` polling |
| Consistent KG | 4-stage dedup (Section 4.4) runs per entity, preventing duplicates even under concurrent processing |

### UC2 (Single Document) → Inline Pipeline

| Requirement | Architectural solution |
|---|---|
| Synchronous response | Same pipeline runs inline (no queue), result returned directly |
| < 30s latency | High-confidence alignments skip LLM judge (auto-accept at >= 0.85); only ambiguous types incur judge latency |
| Dedup against existing graph | Same 4-stage dedup runs against persistent PostgreSQL graph |

### UC3 (Ontology Configuration) → Ontology Loader + Canonical Tables

| Requirement | Architectural solution |
|---|---|
| Support OWL, RDF, LinkML | Three parser backends unified into `OntologyClass` / `OntologyProperty` (Section 4.7) |
| Fast loading | Batch embedding generation via `asyncio.gather` (20 concurrent, 0.5s delay) |
| Schema-driven extraction | Ontology classes dynamically injected into DSPy extraction prompt |
| Safe updates | Upsert-by-URI: new classes added, existing updated, none deleted |

### UC4 (Graph Query) → pgvector + HNSW Indexes

| Requirement | Architectural solution |
|---|---|
| Filter by type | `schema_type_uri` column indexed on `kg_node` |
| Semantic search | HNSW vector index on `kg_node.vector` enables cosine similarity search |
| Neighborhood traversal | `kg_edge` foreign keys to `kg_node` support 1-hop and 2-hop queries |
| < 200ms latency | HNSW approximate nearest neighbor: O(log N) search |

### UC5 (Ontology Evolution) → Audit Trail + Upsert

| Requirement | Architectural solution |
|---|---|
| No data loss on update | Canonical tables upserted (not replaced); existing graph nodes retain `canonical_class_id` |
| Historical alignment preserved | Every node stores `raw_type` + `raw_description` (original LLM output) alongside canonical mapping |
| Forward compatibility | New ontology classes available for future extractions; existing data untouched |

---

## 6. Data Model

### Entity-Relationship Diagram

```
┌──────────────────┐         ┌──────────────────────┐
│ ontology_config  │         │ canonical_class       │
│                  │         │                       │
│ id          PK   │    ┌───>│ id             PK     │
│ name             │    │    │ uri            UNIQUE  │
│ format           │    │    │ label                  │
│ classes_count    │    │    │ description            │
│ properties_count │    │    │ parent_uri             │
│ is_active        │    │    │ vector     VECTOR(1536)│◄── HNSW index
│ loaded_at        │    │    └───────────┬────────────┘
└──────────────────┘    │                │
                        │                │ canonical_class_id
┌──────────────────┐    │    ┌───────────▼────────────┐
│ canonical_property│    │    │ kg_node                 │
│                  │    │    │                         │
│ id          PK   │    │    │ id              PK      │
│ uri        UNIQUE│    │    │ label                   │
│ label            │    │    │ label_normalized        │──┐
│ description      │    │    │ canonical_class_id  FK  │  │ UNIQUE
│ parent_uri       │    │    │ schema_type_uri         │──┘
│ domain_class_uri │    │    │ raw_type         (audit)│
│ range_class_uri  │    │    │ raw_description  (audit)│
│ vector  VEC(1536)│◄── HNSW │ description             │
└────────┬─────────┘    │    │ properties      JSONB   │
         │              │    │ wikidata_id             │
         │              │    │ vector     VECTOR(1536) │◄── HNSW index
         │ canonical_   │    └──────┬──────────────────┘
         │ property_id  │           │
         │              │           │ from_node_id / to_node_id
┌────────▼──────────────┤    ┌──────▼──────────────────┐
│ kg_edge               │    │ kg_node_document         │
│                       │    │                         │
│ id              PK    │    │ node_id      FK, PK     │
│ from_node_id    FK    │    │ document_id  FK, PK     │
│ to_node_id      FK    │    │ created_at              │
│ canonical_property_id │    └──────────┬──────────────┘
│ property_uri          │               │
│ property_label        │    ┌──────────▼──────────────┐
│ raw_relationship_type │    │ document                 │
│ source_document_id FK │    │                         │
│ properties     JSONB  │    │ id            PK        │
│ vector    VECTOR(1536)│    │ content                 │
│ created_at            │    │ content_type            │
│                       │    │ title                   │
│ UNIQUE(from,to,prop,  │    │ source_url              │
│        source_doc)    │    │ metadata       JSONB    │
└───────────────────────┘    │ created_at              │
                             └─────────────────────────┘

┌──────────────────────┐     ┌──────────────────────┐
│ extraction_job        │     │ extraction_result     │
│                      │     │                      │
│ id            PK     │◄────│ id            PK     │
│ status               │     │ job_id         FK    │
│ ontology_config_id FK│     │ document_id    FK    │
│ total_documents      │     │ status               │
│ processed_documents  │     │ nodes_created        │
│ failed_documents     │     │ nodes_reused         │
│ created_at           │     │ edges_created        │
│ started_at           │     │ error_message        │
│ completed_at         │     │ processing_time_ms   │
│ error_log    JSONB   │     │ created_at           │
└──────────────────────┘     └──────────────────────┘
```

### Key Design Decisions

**Audit trail columns:** Every `kg_node` stores both `raw_type`/`raw_description` (what the LLM produced) and `canonical_class_id`/`schema_type_uri` (what the alignment service mapped it to). This enables quality analysis, alignment threshold tuning, and safe ontology migration.

**Denormalized URIs:** `schema_type_uri` on `kg_node` and `property_uri` on `kg_edge` are denormalized from the canonical tables for query performance — avoiding joins on the hot path.

**JSONB properties:** Extensible metadata on nodes and edges for domain-specific attributes without schema changes.

**HNSW index parameters:** `m=16`, `ef_construction=64`, `vector_cosine_ops` — balancing recall (>95%) vs. memory and build time.

---

## 7. Non-functional Requirements

### Performance Targets

| Metric | Target | Bottleneck |
|---|---|---|
| Single-doc extraction | < 30s | LLM API latency |
| Batch throughput | 100+ docs/hour | LLM rate limits |
| Graph query | < 200ms | For graphs up to 100K nodes |
| Ontology loading | < 5 min for 1000 classes | Embedding generation |
| Vector search recall | > 95% | HNSW ef_construction=64 |

### Scalability

- **Horizontal:** Add ARQ workers to increase batch throughput
- **Vertical:** Increase `BATCH_CONCURRENCY` and `DB_POOL_SIZE` per worker
- **Data:** pgvector HNSW indexes handle millions of vectors; periodic REINDEX maintains performance

### Security

- API key authentication on all endpoints (except `/health`)
- LLM API keys in environment variables, never logged
- Parameterized SQL queries (no string interpolation for vector search)
- Single-tenant deployment in v1

### Observability

- Structured JSON logging with correlation IDs per request/job
- Per-job metrics: documents processed, LLM calls, embedding calls, latency per pipeline stage
- Health check endpoint with database and Redis connectivity status

### Reliability

- Per-document error isolation in batch processing
- Exponential backoff retry for transient LLM errors (429, 503)
- Database transaction rollback on persistence failures
- Idempotent document processing (re-processing updates, not duplicates, via dedup)

---

## 8. Technology Stack

| Category | Technology | Justification |
|---|---|---|
| Runtime | Python 3.12+ | Async/await, type hints, LLM ecosystem |
| Web framework | FastAPI | Async-native, auto-generated OpenAPI docs, Pydantic validation |
| Database | PostgreSQL 16 + pgvector | Mature RDBMS with vector search in the same engine (no separate vector DB) |
| Vector search | pgvector HNSW | In-database ANN search; avoids operational complexity of Pinecone/Weaviate |
| ORM | SQLAlchemy 2.0 + SQLModel | Async support, type safety, Alembic migration integration |
| Job queue | ARQ + Redis | Async-native Python queue; lighter than Celery for our async stack |
| LLM abstraction | LiteLLM | 15+ providers, unified API, built-in rate limiting, drop-in switching |
| Extraction | DSPy | Structured signatures with Pydantic output models; LiteLLM backend support |
| Ontology parsing | rdflib + linkml-runtime | Standard OWL/RDF parser + LinkML community standard |
| HTTP client | httpx | Async, timeout management, connection pooling (for Wikidata API) |

---

## 9. Risks and Mitigations

| Risk | L | I | Mitigation |
|---|---|---|---|
| LLM rate limits at batch scale | H | M | Per-provider rate limiter via LiteLLM + configurable `BATCH_CONCURRENCY` + exponential backoff |
| Schema alignment quality for novel domains | M | H | Adjustable thresholds (0.85/0.50); LLM judge re-ranking; Wikidata fallback; alignment audit trail for tuning |
| DSPy output parsing failures | M | M | Pydantic validation with retry; error logged per document, batch continues |
| Embedding consistency across ontology load and alignment | M | H | Enforced text format `"{label}: {description}"` for both seeding and querying; single embedding model config |
| pgvector performance at > 1M vectors | L | M | HNSW indexes; periodic REINDEX; table partitioning if needed |
| Ontology format edge cases | M | L | Test fixtures for each format; graceful skip for unparseable elements |
| Redis single point of failure | L | H | Redis Sentinel/cluster for production; sync fallback for single-doc mode |
| LLM provider deprecation | L | M | LiteLLM abstraction + per-provider integration tests; switch via env var |

---

## 10. Comparison with OntoGPT

OntoGPT (Monarch Initiative) is the closest existing open-source system to OntoExtract. It uses the SPIRES method (Structured Prompt Interrogation and Recursive Extraction of Semantics), published in Bioinformatics 2024. This section compares the two architectures.

### 10.1 Architecture Comparison

```
┌─────────────────────────────────┐    ┌─────────────────────────────────┐
│          OntoGPT                │    │         OntoExtract              │
│                                 │    │                                 │
│  CLI Tool (single process)      │    │  Microservice (multi-worker)    │
│                                 │    │                                 │
│  ┌───────────────────┐          │    │  ┌───────────────────┐          │
│  │ LinkML Template   │          │    │  │ OWL/RDF/LinkML    │          │
│  │ (YAML)            │          │    │  │ Ontology File     │          │
│  └────────┬──────────┘          │    │  └────────┬──────────┘          │
│           │                     │    │           │                     │
│           ▼                     │    │           ▼                     │
│  ┌───────────────────┐          │    │  ┌───────────────────┐          │
│  │ Serialize full    │          │    │  │ Embed all classes  │          │
│  │ schema into       │          │    │  │ & properties into  │          │
│  │ prompt as         │          │    │  │ vector index       │          │
│  │ pseudo-YAML       │          │    │  │ (one-time)         │          │
│  └────────┬──────────┘          │    │  └────────┬──────────┘          │
│           │                     │    │           │                     │
│           ▼                     │    │           ▼                     │
│  ┌───────────────────┐          │    │  ┌───────────────────┐          │
│  │ LLM fills in      │          │    │  │ LLM extracts      │          │
│  │ template values   │          │    │  │ entities (DSPy)   │          │
│  │ (recursive for    │          │    │  │                   │          │
│  │  nested types)    │          │    │  │ Align via vector  │          │
│  └────────┬──────────┘          │    │  │ search + LLM      │          │
│           │                     │    │  │ judge             │          │
│           ▼                     │    │  └────────┬──────────┘          │
│  ┌───────────────────┐          │    │           │                     │
│  │ Parse YAML output │          │    │           ▼                     │
│  │ Normalize via     │          │    │  ┌───────────────────┐          │
│  │ string matching   │          │    │  │ 4-stage dedup     │          │
│  │ (OAK/Gilda)       │          │    │  │ Persist to        │          │
│  └────────┬──────────┘          │    │  │ PostgreSQL graph  │          │
│           │                     │    │  └───────────────────┘          │
│           ▼                     │    │                                 │
│  ┌───────────────────┐          │    │                                 │
│  │ JSON/TSV output   │          │    │                                 │
│  │ (no persistence)  │          │    │                                 │
│  └───────────────────┘          │    │                                 │
└─────────────────────────────────┘    └─────────────────────────────────┘
```

### 10.2 Feature Comparison

| Dimension | OntoGPT | OntoExtract |
|---|---|---|
| **Deployment** | CLI tool, single-process, synchronous | Microservice, multi-worker, async |
| **Ontology formats** | LinkML only | OWL, RDF/Turtle, LinkML |
| **LLM support** | LiteLLM (broad) | LiteLLM (broad) |
| **Extraction method** | Recursive prompt → pseudo-YAML → parse | DSPy structured signatures → Pydantic models |
| **Schema alignment** | Post-hoc string matching (OAK/Gilda) | Embedding vector search + LLM re-ranking judge |
| **Scales to large ontologies?** | No — full schema serialized into every prompt | Yes — vector index decouples ontology size from prompt size |
| **Entity deduplication** | None (per-document, no cross-doc dedup) | 4-stage: exact, semantic, Wikidata, create |
| **Graph storage** | None (outputs JSON/TSV files) | PostgreSQL + pgvector with HNSW indexes |
| **Batch processing** | Sequential, no parallelism, no queue | Redis + ARQ, configurable N-worker parallelism |
| **Entity grounding** | OAK (BioPortal, Gilda, OLS) | Wikidata API (extensible) |
| **Audit trail** | None | Full: raw LLM output stored alongside canonical mapping |
| **Published benchmarks** | BC5CDR: F1=0.44, P=0.69, R=0.32 | None yet |
| **Setup complexity** | `pip install ontogpt` | Docker Compose (PostgreSQL + Redis) |

### 10.3 Key Trade-offs

**OntoGPT excels at:**
- **Recursive extraction** for deeply nested types. SPIRES makes multiple LLM passes for complex structures (e.g., a `ClinicalTrial` containing `Drug` containing `ActiveIngredient`). OntoExtract v1 uses flat extraction.
- **Biomedical grounding** via OAK, which dispatches to BioPortal, Gilda, and OLS — specialized annotators with deep domain coverage.
- **Ease of getting started** — `pip install ontogpt` and a CLI command. No database or Redis.
- **Published benchmarks** — peer-reviewed F1 scores on BC5CDR chemical-disease extraction.

**OntoExtract excels at:**
- **Production-scale batch processing** — hundreds to thousands of documents with parallel workers, error isolation, and progress tracking.
- **Large ontologies** — the embedding-based alignment scales to 100K+ classes without prompt overflow.
- **Persistent, deduplicated knowledge graph** — 4-stage dedup prevents entity fragmentation across documents.
- **Alignment quality for ambiguous types** — continuous similarity scores + LLM judge re-ranking vs. binary string matching.
- **LLM cost optimization** — high-confidence alignments (60-70% of entities) skip the LLM judge entirely.
- **Audit and traceability** — every alignment decision is recorded with the original LLM output.

### 10.4 When to Choose Which

| Scenario | Recommendation |
|---|---|
| One-off extraction from a few documents | OntoGPT (simpler setup) |
| Biomedical domain with OBO ontologies | OntoGPT (OAK grounding) |
| Research prototyping | OntoGPT (CLI, no infra) |
| Production pipeline, 100+ documents | **OntoExtract** |
| Large ontology (100+ classes) | **OntoExtract** |
| Need persistent, queryable KG | **OntoExtract** |
| Multi-provider LLM flexibility in production | **OntoExtract** |
| Non-biomedical domains | **OntoExtract** |

---

## 11. Appendices

### Appendix A: API Endpoint Summary

| Method | Path | Description | Mode |
|---|---|---|---|
| `POST` | `/extract` | Single document extraction (sync) | Sync |
| `POST` | `/batch` | Create batch extraction job | Async (202) |
| `GET` | `/jobs/{id}` | Job status and progress | Polling |
| `GET` | `/jobs/{id}/results` | Per-document extraction results | Read |
| `DELETE` | `/jobs/{id}` | Cancel a running job | Write |
| `POST` | `/ontology/load` | Upload and parse ontology | Admin |
| `GET` | `/ontology/status` | Current ontology stats | Read |
| `GET` | `/ontology/classes` | List canonical classes | Read |
| `GET` | `/ontology/properties` | List canonical properties | Read |
| `GET` | `/graph/nodes` | List/filter graph nodes | Read |
| `GET` | `/graph/nodes/{id}` | Node detail with type info | Read |
| `GET` | `/graph/nodes/{id}/neighborhood` | 1-hop or 2-hop subgraph | Read |
| `GET` | `/graph/edges` | List/filter graph edges | Read |
| `GET` | `/graph/search` | Semantic vector search | Read |
| `POST` | `/graph/subgraph` | Extract subgraph by node IDs | Read |
| `GET` | `/health` | Health check (DB + Redis) | Public |

### Appendix B: Configuration Reference

```bash
# Database
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/ontoextract
DB_POOL_SIZE=5
DB_MAX_OVERFLOW=10

# Job Queue
REDIS_URL=redis://localhost:6379

# LLM Models (LiteLLM format)
LLM_EXTRACTION_MODEL=openai/gpt-4o-mini
LLM_JUDGE_MODEL=openai/gpt-4o-mini
LLM_EMBEDDING_MODEL=openai/text-embedding-3-small
EMBEDDING_DIMENSIONS=1536

# Alignment Thresholds
HIGH_CONFIDENCE_THRESHOLD=0.85    # Auto-accept above this
MIN_THRESHOLD=0.50                # Below this, mark unmatched
SEMANTIC_DEDUP_THRESHOLD=0.88     # Node dedup similarity floor

# Batch Processing
BATCH_CONCURRENCY=5               # Docs concurrent per worker
EMBED_BATCH_SIZE=20               # Embeddings concurrent per batch

# Extraction Limits
MAX_ENTITIES_PER_DOCUMENT=15
MAX_RELATIONSHIPS_PER_DOCUMENT=20
MIN_CONTENT_WORDS=50

# API Security
API_KEY=your-api-key
```

### Appendix C: Glossary

| Term | Definition |
|---|---|
| Canonical class | An ontology class stored with its embedding in the reference table. Used as the alignment target. |
| Canonical property | An ontology property (relationship type) stored with its embedding. Has optional domain/range constraints. |
| Schema alignment | Mapping a raw LLM-extracted type/label to a canonical class/property via embedding similarity + LLM judge. |
| LLM judge | A targeted, low-token LLM call that picks the best canonical match from a shortlist of embedding candidates. |
| Node dedup | The 4-stage process (exact, semantic, Wikidata, create) that prevents duplicate entities in the graph. |
| HNSW | Hierarchical Navigable Small World — an approximate nearest neighbor index for fast vector search. |
| DSPy signature | A structured prompt template that defines typed input/output fields, producing Pydantic-validated output. |
| ARQ | Async Redis Queue — a Python-native async job queue for background task processing. |
| Audit trail | The preservation of raw LLM output (`raw_type`, `raw_description`) alongside the canonical alignment result. |
