# OntoExtract: Implementation Plan

**For:** AI Coding Agent  
**Reference:** `docs/architecture-design.md`  
**Source codebase:** iCognition (`/Users/eboraks/Projects/icognition/backend/`)

---

## Overview

Build a standalone FastAPI microservice called **OntoExtract** that extracts structured knowledge graphs from unstructured text, aligned to any pluggable ontology (OWL/RDF/LinkML). The service uses embedding-based schema alignment with LLM re-ranking, 4-stage entity deduplication, Redis-backed batch processing, and PostgreSQL/pgvector for graph storage.

Many components are ported from the iCognition project. When this document says "port from `{file}`", read that file and adapt its patterns — replace Gemini-specific code with LiteLLM, remove user_id scoping (single-tenant v1), and follow the patterns described below.

---

## Project Structure

```
ontoextract/
  pyproject.toml
  alembic.ini
  .env.example
  docker-compose.yml                 # PostgreSQL + Redis
  alembic/
    env.py
    versions/
      001_initial_schema.py
  ontoextract/
    __init__.py
    main.py                          # FastAPI app, lifespan, CORS
    config.py                        # Pydantic Settings
    api/
      __init__.py
      deps.py                        # Dependency injection (db session, services)
      routes/
        __init__.py
        extraction.py                # POST /extract, POST /batch
        jobs.py                      # GET /jobs/{id}, GET /jobs, DELETE /jobs/{id}
        graph.py                     # GET /graph/nodes, /edges, /search, /subgraph
        ontology.py                  # POST /ontology/load, GET /ontology/status
        health.py                    # GET /health
      schemas/
        __init__.py
        extraction.py                # Request/response Pydantic models
        jobs.py
        graph.py
        ontology.py
    models/
      __init__.py
      canonical.py                   # KGCanonicalClass, KGCanonicalProperty
      graph.py                       # KGNode, KGEdge, KGNodeDocument
      jobs.py                        # ExtractionJob, ExtractionResult
      documents.py                   # Document
      ontology.py                    # OntologyConfig
    db/
      __init__.py
      database.py                    # async engine, session factory
    services/
      __init__.py
      ontology_loader.py             # OWL/RDF/LinkML parsers + canonical table seeder
      extraction_service.py          # DSPy entity + relationship extraction
      schema_alignment_service.py    # Embedding search + LLM judge
      kg_adapter.py                  # Node/edge dedup + graph persistence
      embedding_service.py           # LiteLLM embedding wrapper
      wikidata_service.py            # Wikidata API client
      llm_service.py                 # LiteLLM completion wrapper (for judge)
      job_service.py                 # Job CRUD + lifecycle
    pipeline/
      __init__.py
      extraction_pipeline.py         # Full pipeline orchestrator
      chunking.py                    # Text chunking strategies
    workers/
      __init__.py
      arq_worker.py                  # ARQ worker config
      tasks.py                       # Batch processing task functions
    utils/
      __init__.py
      logging.py                     # Structured JSON logger
      text.py                        # normalize_label, clean_text
  tests/
    __init__.py
    conftest.py                      # Fixtures: db session, services, sample data
    test_ontology_loader.py
    test_extraction_service.py
    test_schema_alignment.py
    test_kg_adapter.py
    test_pipeline.py
    test_api/
      test_extraction.py
      test_jobs.py
      test_graph.py
      test_ontology.py
    fixtures/
      sample_schema.ttl              # Small schema.org subset for testing
      sample_biomedical.owl          # Small OWL ontology for testing
      sample_linkml.yaml             # LinkML template for testing
      sample_documents.json          # Test documents with expected outputs
```

---

## Dependencies

Create `pyproject.toml` with:

```toml
[project]
name = "ontoextract"
version = "0.1.0"
description = "Ontology-grounded structured extraction microservice"
requires-python = ">=3.12"
dependencies = [
    # Web framework
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.30.0",
    # Database
    "sqlmodel>=0.0.22",
    "sqlalchemy[asyncio]>=2.0.35",
    "alembic>=1.14.0",
    "pgvector>=0.3.6",
    "asyncpg>=0.30.0",
    # LLM
    "litellm>=1.55.0",
    "dspy>=2.6.0",
    # Ontology parsing
    "rdflib>=7.1.0",
    "linkml-runtime>=1.8.0",
    # Job queue
    "arq>=0.26.1",
    # HTTP client
    "httpx>=0.28.0",
    # Data / utilities
    "pydantic>=2.10.0",
    "pydantic-settings>=2.6.0",
    "numpy>=2.1.0",
    "anyio>=4.7.0",
    "pyyaml>=6.0.2",
    "beautifulsoup4>=4.12.3",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.3.0",
    "pytest-asyncio>=0.24.0",
    "pytest-cov>=6.0.0",
    "httpx",  # for FastAPI TestClient
    "ruff>=0.8.0",
]
```

Use `uv` for all package management (`uv init`, `uv add`, `uv run`).

---

## Implementation Phases

### Phase 1: Foundation

---

#### Task 1: Project Scaffolding + Configuration

**Files to create:**
- `pyproject.toml` (as above)
- `ontoextract/__init__.py`
- `ontoextract/config.py`
- `ontoextract/utils/__init__.py`
- `ontoextract/utils/logging.py`
- `ontoextract/utils/text.py`
- `.env.example`
- `docker-compose.yml`

**`ontoextract/config.py`** — Pydantic Settings class:

```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Database
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/ontoextract"
    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 10

    # Redis
    REDIS_URL: str = "redis://localhost:6379"

    # LLM
    LLM_EXTRACTION_MODEL: str = "openai/gpt-4o-mini"
    LLM_JUDGE_MODEL: str = "openai/gpt-4o-mini"
    LLM_EMBEDDING_MODEL: str = "openai/text-embedding-3-small"
    EMBEDDING_DIMENSIONS: int = 1536

    # Thresholds (from iCognition production values)
    HIGH_CONFIDENCE_THRESHOLD: float = 0.85
    MIN_THRESHOLD: float = 0.50
    SEMANTIC_DEDUP_THRESHOLD: float = 0.88

    # Batch processing
    BATCH_CONCURRENCY: int = 5
    EMBED_BATCH_SIZE: int = 20

    # Extraction limits
    MAX_ENTITIES_PER_DOCUMENT: int = 15
    MAX_RELATIONSHIPS_PER_DOCUMENT: int = 20
    MIN_CONTENT_WORDS: int = 50

    # API
    API_KEY: str = ""

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

settings = Settings()
```

**`ontoextract/utils/text.py`**:
- `normalize_label(text: str) -> str`: lowercase, strip whitespace, collapse spaces
- `clean_text(html_or_text: str) -> str`: strip HTML tags, normalize whitespace

**`ontoextract/utils/logging.py`**:
- Structured JSON logger factory. Pattern: `get_logger(name: str) -> logging.Logger`

**`docker-compose.yml`**: PostgreSQL 16 with pgvector extension + Redis 7.

**Tests:** `settings` loads from env vars, defaults are sane, `normalize_label` is correct.

---

#### Task 2: Database + Models

**Files to create:**
- `ontoextract/db/__init__.py`
- `ontoextract/db/database.py`
- `ontoextract/models/__init__.py`
- `ontoextract/models/canonical.py`
- `ontoextract/models/graph.py`
- `ontoextract/models/documents.py`
- `ontoextract/models/jobs.py`
- `ontoextract/models/ontology.py`

**Port from:** `backend/app/db/database.py` for engine/session setup. `backend/app/models_kg.py` for canonical and graph models.

**`ontoextract/db/database.py`**:
```python
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from ontoextract.config import settings

engine = create_async_engine(
    settings.DATABASE_URL,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_timeout=5,
    pool_recycle=1800,
)

async_session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def get_session() -> AsyncSession:
    async with async_session_factory() as session:
        yield session
```

**`ontoextract/models/canonical.py`** — Port `KGCanonicalClass` and `KGCanonicalProperty` from `backend/app/models_kg.py`:
- Use `SQLModel` base class
- Vector columns: `vector: Optional[Any] = Field(sa_column=Column(Vector(1536)))`
- HNSW index: `Index('ix_canonical_class_vector', 'vector', postgresql_using='hnsw', postgresql_with={'m': 16, 'ef_construction': 64}, postgresql_ops={'vector': 'vector_cosine_ops'})`

**`ontoextract/models/graph.py`** — Port `KGNode`, `KGEdge`, `KGNodeDocument`:
- Remove `user_id` column (single-tenant v1) or make it optional with a default
- Keep all UNIQUE indexes for dedup
- Keep HNSW indexes on vector columns
- Keep `raw_type`, `raw_description` for audit trail

**`ontoextract/models/documents.py`** — New model:
```python
class Document(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    content: str
    content_type: Optional[str] = None  # "text/plain", "text/html"
    title: Optional[str] = None
    source_url: Optional[str] = None
    metadata_: Optional[dict] = Field(default=None, sa_column=Column("metadata", JSON))
    created_at: datetime = Field(default_factory=datetime.utcnow)
```

**`ontoextract/models/jobs.py`** — New models:
```python
class ExtractionJob(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    status: str = "pending"  # pending, running, completed, partially_failed, failed
    ontology_config_id: Optional[int] = Field(foreign_key="ontologyconfig.id")
    total_documents: int
    processed_documents: int = 0
    failed_documents: int = 0
    created_at: datetime = Field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_log: Optional[dict] = Field(default=None, sa_column=Column(JSON))

class ExtractionResult(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    job_id: int = Field(foreign_key="extractionjob.id")
    document_id: int = Field(foreign_key="document.id")
    status: str  # success, failed, skipped
    nodes_created: int = 0
    nodes_reused: int = 0
    edges_created: int = 0
    error_message: Optional[str] = None
    processing_time_ms: Optional[int] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
```

**`ontoextract/models/ontology.py`** — New model:
```python
class OntologyConfig(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    format: str  # "owl", "rdf", "linkml"
    file_path: Optional[str] = None
    classes_count: int = 0
    properties_count: int = 0
    is_active: bool = True
    loaded_at: datetime = Field(default_factory=datetime.utcnow)
```

**Tests:** All models instantiate. Relationships (ForeignKey) are correct. Vector columns accept numpy arrays.

---

#### Task 3: Alembic Migrations

**Files to create:**
- `alembic.ini`
- `alembic/env.py`
- `alembic/versions/001_initial_schema.py`

**`alembic/env.py`**: Async Alembic setup. Import all models so metadata is complete. Use `run_async_migration()` pattern.

**Migration 001**: Single migration creates all tables:
1. `CREATE EXTENSION IF NOT EXISTS vector`
2. `canonical_class` with HNSW index
3. `canonical_property` with HNSW index
4. `kg_node` with UNIQUE + HNSW indexes
5. `kg_edge` with UNIQUE + HNSW indexes
6. `kg_node_document` with composite PK
7. `document`
8. `extraction_job`
9. `extraction_result`
10. `ontology_config`

**Tests:** `alembic upgrade head` and `alembic downgrade base` both succeed on a clean database.

---

#### Task 4: FastAPI App Skeleton

**Files to create:**
- `ontoextract/main.py`
- `ontoextract/api/__init__.py`
- `ontoextract/api/deps.py`
- `ontoextract/api/routes/__init__.py`
- `ontoextract/api/routes/health.py`
- `ontoextract/api/schemas/__init__.py`

**`ontoextract/main.py`**:
```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from ontoextract.api.routes import health

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: verify DB connection, verify Redis connection
    yield
    # Shutdown: close pools

app = FastAPI(title="OntoExtract", version="0.1.0", lifespan=lifespan)
app.include_router(health.router)
```

**`ontoextract/api/deps.py`**:
- `get_db_session()`: Yields async session from factory
- `verify_api_key()`: FastAPI dependency for API key auth
- Service factory functions

**`ontoextract/api/routes/health.py`**:
```python
@router.get("/health")
async def health_check():
    return {"status": "healthy", "version": "0.1.0"}
```

**Tests:** `GET /health` returns 200 with correct payload.

---

### Phase 2: Core Services

---

#### Task 5: Embedding Service

**File to create:** `ontoextract/services/embedding_service.py`

**Port from:** `backend/app/services/embedding_service.py` — adapt the embedding generation and batch patterns.

**Key class:**
```python
from dataclasses import dataclass
import litellm

@dataclass
class EmbeddingResult:
    embedding: list[float]
    dimensions: int
    model_used: str
    success: bool
    error: Optional[str] = None

class EmbeddingService:
    def __init__(self, model: str, dimensions: int):
        self.model = model
        self.dimensions = dimensions

    async def generate_embedding(self, text: str) -> EmbeddingResult:
        """Generate a single embedding via LiteLLM."""
        response = await litellm.aembedding(
            model=self.model,
            input=[text],
            dimensions=self.dimensions,
        )
        return EmbeddingResult(
            embedding=response.data[0]["embedding"],
            dimensions=self.dimensions,
            model_used=self.model,
            success=True,
        )

    async def generate_embeddings_batch(self, texts: list[str]) -> list[EmbeddingResult]:
        """Generate embeddings concurrently in batches."""
        results = []
        for i in range(0, len(texts), settings.EMBED_BATCH_SIZE):
            batch = texts[i:i + settings.EMBED_BATCH_SIZE]
            batch_results = await asyncio.gather(
                *[self.generate_embedding(t) for t in batch],
                return_exceptions=True,
            )
            results.extend(batch_results)
            if i + settings.EMBED_BATCH_SIZE < len(texts):
                await asyncio.sleep(0.5)  # Rate limit friendliness
        return results
```

**Tests:** Mock `litellm.aembedding`. Verify batch concurrency and rate limit delay.

---

#### Task 6: LLM Service

**File to create:** `ontoextract/services/llm_service.py`

**Purpose:** Wrapper for LiteLLM completions, used by the schema alignment service's LLM judge.

**Port from:** Replace `google.genai.Client` calls in `backend/app/services/schema_alignment_service.py` with:

```python
import litellm

class LLMService:
    def __init__(self, model: str):
        self.model = model

    async def complete(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.0,
        max_tokens: int = 100,
    ) -> str:
        """Single LLM completion call via LiteLLM."""
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        response = await litellm.acompletion(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content.strip()
```

**Tests:** Mock `litellm.acompletion`. Verify message construction and response parsing.

---

#### Task 7: Wikidata Service

**File to create:** `ontoextract/services/wikidata_service.py`

**Port from:** `backend/app/services/wikidata_service.py` — direct port with minimal changes.

Copy the entire service. It uses `httpx.AsyncClient`, returns `WikidataEntity` and `WikidataProperty` dataclasses, has proper error handling and timeouts (10s). No Gemini or iCognition-specific dependencies.

**Key methods to port:**
- `search_entities(query, limit=5) -> list[WikidataEntity]`
- `search_properties(query, limit=5) -> list[WikidataProperty]`
- `get_entity_details(wikidata_id) -> Optional[WikidataEntity]`

**Tests:** Mock `httpx.AsyncClient`. Verify entity/property search, timeout handling.

---

#### Task 8: Ontology Loader Service

**File to create:** `ontoextract/services/ontology_loader.py`

**Port from:** `backend/scripts/seed_ontology.py` for the RDF parser and seeding logic.

**Key class:**
```python
@dataclass
class OntologyClass:
    uri: str
    label: str
    description: str
    parent_uri: Optional[str] = None

@dataclass
class OntologyProperty:
    uri: str
    label: str
    description: str
    parent_uri: Optional[str] = None
    domain_class_uri: Optional[str] = None
    range_class_uri: Optional[str] = None

class OntologyLoaderService:
    def __init__(self, embedding_service: EmbeddingService):
        self.embedding_service = embedding_service

    def parse_rdf(self, file_path: str) -> tuple[list[OntologyClass], list[OntologyProperty]]:
        """Parse RDF/Turtle ontology using rdflib.
        Port from: seed_ontology.py parse_schema_classes() and parse_schema_properties()
        """
        ...

    def parse_owl(self, file_path: str) -> tuple[list[OntologyClass], list[OntologyProperty]]:
        """Parse OWL ontology using rdflib.
        Extends parse_rdf to also handle owl:Class, owl:ObjectProperty, owl:DatatypeProperty.
        """
        ...

    def parse_linkml(self, file_path: str) -> tuple[list[OntologyClass], list[OntologyProperty]]:
        """Parse LinkML YAML schema using linkml-runtime.
        Maps schema.classes -> OntologyClass, schema.slots -> OntologyProperty.
        """
        from linkml_runtime.utils.schemaloader import SchemaLoader
        schema = SchemaLoader(file_path).resolve()
        classes = [
            OntologyClass(
                uri=f"{schema.id}/{cls.name}",
                label=cls.name,
                description=cls.description or "",
                parent_uri=cls.is_a if cls.is_a else None,
            )
            for cls in schema.classes.values()
        ]
        ...

    async def load_ontology(
        self, file_path: str, format: str, session: AsyncSession
    ) -> OntologyConfig:
        """Parse ontology, generate embeddings, seed canonical tables.
        Port the seeding logic from seed_ontology.py:
        - Embedding text format: "{label}: {description[:500]}"
        - Batch size: EMBED_BATCH_SIZE (default 20)
        - Upsert by URI (INSERT ON CONFLICT UPDATE)
        """
        ...
```

**RDF Parser** — Port directly from `seed_ontology.py`:
- `parse_schema_classes(g: Graph)` extracts RDFS.Class with uri, label (rdfs:label), description (rdfs:comment), parent_uri (rdfs:subClassOf)
- `parse_schema_properties(g: Graph)` extracts RDF.Property with uri, label, description, domain (schema:domainIncludes), range (schema:rangeIncludes)
- Use the same namespace handling for schema.org URIs

**OWL Parser** — Extend RDF parser:
- Also match `owl:Class` (in addition to `rdfs:Class`)
- Also match `owl:ObjectProperty` and `owl:DatatypeProperty`
- Map `rdfs:domain` and `rdfs:range` (not just schema:domainIncludes)

**Seeding** — Port from `seed_ontology.py`:
- Embedding text: `f"{label}: {description[:500]}"`
- Batch embed with `embedding_service.generate_embeddings_batch()`
- Upsert to `canonical_class` and `canonical_property` using `ON CONFLICT (uri) DO UPDATE`

**Tests:**
- Parse `fixtures/sample_schema.ttl` → verify correct class/property counts
- Parse `fixtures/sample_biomedical.owl` → verify OWL-specific constructs
- Parse `fixtures/sample_linkml.yaml` → verify LinkML mapping
- Verify embedding text format matches `"{label}: {description}"`

---

#### Task 9: Schema Alignment Service

**File to create:** `ontoextract/services/schema_alignment_service.py`

**Port from:** `backend/app/services/schema_alignment_service.py` — this is the most critical port.

**What to copy verbatim:**
- `AlignmentResult` dataclass
- `ENTITY_TYPE_DESCRIPTIONS` dict (but make it loadable from ontology config)
- The `_class_cache` pattern
- All three threshold constants (use `settings.*` instead of hardcoded)
- The vector search SQL query: `1 - (vector <=> CAST(:query_vector AS vector))`
- The LLM judge prompt templates for both class and property alignment

**What to change:**
1. Replace `genai.Client.aio.models.generate_content(...)` with `llm_service.complete(prompt, temperature=0.0, max_tokens=...)`:
   - Class judge: `max_tokens=50` (from iCognition)
   - Property judge: `max_tokens=100` (from iCognition)

2. Replace `embedding_service.generate_embedding(text, task_type=...)` with the new LiteLLM-based `embedding_service.generate_embedding(text)`

3. Make `ENTITY_TYPE_DESCRIPTIONS` dynamic: load class labels + descriptions from the `canonical_class` table instead of hardcoding

**Key methods to port:**
- `align_entity_type(session, entity_name, raw_type, description, top_k=5) -> AlignmentResult`
- `align_relationship(session, raw_relationship_type, from_entity, to_entity, from_type_uri, to_type_uri, top_k=5) -> AlignmentResult`
- `align_entities_batch(session, entities) -> list[dict]`
- `align_relationships_batch(session, relationships, entity_type_map) -> list[dict]`
- `_search_canonical_classes(session, query_vector, top_k) -> list[tuple]`
- `_search_canonical_properties(session, query_vector, top_k, domain_uri, range_uri) -> list[tuple]`
- `_judge_entity_class(entity_name, raw_type, description, candidates) -> str`
- `_judge_relationship_property(raw_label, from_entity, to_entity, candidates, wikidata_candidates) -> str`

**LLM Judge Prompt (entity class)** — Port from iCognition:
```
Given an entity "{entity_name}" of raw type "{raw_type}" with description "{description}",
which of these canonical classes is the best match?

Candidates:
1. {label} ({uri}) - similarity {score:.2f}
2. ...

Respond with ONLY the number of the best match, or "none" if none fit.
```

**LLM Judge Prompt (relationship property)** — Port from iCognition:
```
Given the relationship "{from_entity} --[{raw_label}]--> {to_entity}",
which canonical property best represents this relationship?

Candidates (from embedding search):
{numbered list with labels, URIs, similarity scores}

Wikidata candidates:
{numbered list from wikidata_service.search_properties()}

Respond with one of:
EXISTING: {label}
WIKIDATA: {property_id} | {label}
NEW: {label} | {one-sentence description}
```

**Tests:**
- Test high-confidence auto-accept (similarity >= 0.85, no LLM call)
- Test moderate-confidence LLM judge invocation (0.50-0.85)
- Test low-confidence unmatched (< 0.50, no LLM call)
- Test cache hit (same raw_type returns cached result)
- Test Wikidata fallback for relationships
- Test NEW property creation flow

---

#### Task 10: KG Adapter

**File to create:** `ontoextract/services/kg_adapter.py`

**Port from:** `backend/app/services/kg_adapter.py` — direct port of the dedup + persistence logic.

**Key class:**
```python
class KGAdapter:
    def __init__(
        self,
        schema_alignment_service: SchemaAlignmentService,
        embedding_service: EmbeddingService,
        wikidata_service: WikidataService,
    ):
        ...

    async def process_document_kg(
        self,
        session: AsyncSession,
        document_id: int,
        raw_entities: list[dict],
        raw_relationships: list[dict],
    ) -> dict:
        """Main entry point. Port from kg_adapter.py process_document_kg().
        Returns: {nodes_created, nodes_reused, edges_created}
        """
        ...
```

**Node dedup methods to port** (from `kg_adapter.py`):
1. `_find_or_create_node(session, entity) -> tuple[KGNode, bool]`
   - Stage 1: Query by `(label_normalized, schema_type_uri)` unique index
   - Stage 2: `_find_semantic_match(session, query_vector, schema_type_uri)` — vector search with threshold from `settings.SEMANTIC_DEDUP_THRESHOLD`
   - Stage 3: `_lookup_wikidata(name)` — search Wikidata, check `kg_node.wikidata_id`
   - Stage 4: Create new node with embedding
2. `_generate_node_embedding(node) -> list[float]` — embed `"{label} - {description}"`
3. `_find_semantic_match(session, query_vector, schema_type_uri) -> Optional[KGNode]`
4. `_enrich_node_with_wikidata(node, name)` — set `wikidata_id`, update label/description

**Edge persistence** (from `kg_adapter.py`):
1. Check unique constraint `(from_node_id, to_node_id, property_uri, source_document_id)`
2. Generate edge embedding: `"{from_label} {property_label} {to_label}"`
3. Insert `KGEdge` with canonical property linkage
4. Insert `KGNodeDocument` junction records

**Remove from iCognition version:** `user_id` filtering in all queries.

**Tests:**
- Test exact match dedup (same entity name + type)
- Test semantic match dedup (similar but not identical names)
- Test Wikidata match dedup
- Test new node creation
- Test edge dedup per document
- Test batch processing of multiple entities

---

### Phase 3: Extraction Pipeline

---

#### Task 11: Extraction Service (DSPy)

**File to create:** `ontoextract/services/extraction_service.py`

**Port from:** `backend/app/services/dspy_entity_service.py`

**Key changes from iCognition:**
1. Replace `dspy.LM("gemini/...")` with `dspy.LM(settings.LLM_EXTRACTION_MODEL)` — DSPy supports LiteLLM model strings natively
2. Make entity types dynamic from loaded ontology classes

**Class structure:**
```python
import dspy
import anyio

class ExtractEntities(dspy.Signature):
    """Extract named entities from the given text.
    Instructions are set dynamically based on loaded ontology.
    """
    text: str = dspy.InputField(desc="The source text to extract entities from")
    entities: list[dict] = dspy.OutputField(
        desc="List of entities, each with 'name', 'type', and 'description'"
    )

class ExtractEntityRelationships(dspy.Signature):
    """Extract relationships between the given entities from the text.
    Port the signature instructions from dspy_entity_service.py.
    """
    text: str = dspy.InputField()
    entity_names: list[str] = dspy.InputField()
    relationships: list[dict] = dspy.OutputField(
        desc="List of relationships, each with 'from_entity', 'to_entity', 'relationship_type'"
    )

class ExtractionService:
    def __init__(self, ontology_classes: list[str] = None):
        self.lm = dspy.LM(
            settings.LLM_EXTRACTION_MODEL,
            max_tokens=8192,
        )
        self.entity_types = ontology_classes or [
            "person", "organization", "location", "event", "concept"
        ]
        # Build dynamic instructions incorporating ontology types
        self._build_signatures()

    def _build_signatures(self):
        """Create DSPy signatures with entity types from loaded ontology."""
        type_list = ", ".join(self.entity_types)
        instructions = f"""Extract up to {settings.MAX_ENTITIES_PER_DOCUMENT} named entities.
        Entity types: {type_list}
        Each entity must have: name, type (from the list above), description (<15 words).
        Focus on MAIN entities. Quality over quantity."""
        self.entity_extractor = dspy.Predict(
            ExtractEntities.with_instructions(instructions)
        )

    async def extract_entities(self, text: str) -> list[dict]:
        """Extract entities from text. Port from dspy_entity_service.py."""
        if len(text.split()) < settings.MIN_CONTENT_WORDS:
            return []
        # Use anyio.to_thread for sync DSPy in async context
        def _extract():
            with dspy.context(lm=self.lm):
                result = self.entity_extractor(text=text)
                return result.entities
        return await anyio.to_thread.run_sync(_extract)

    async def extract_relationships(
        self, text: str, entity_names: list[str]
    ) -> list[dict]:
        """Extract relationships. Port from dspy_entity_service.py."""
        if len(entity_names) < 2:
            return []
        def _extract():
            with dspy.context(lm=self.lm):
                result = self.relationship_extractor(
                    text=text, entity_names=entity_names
                )
                return result.relationships
        return await anyio.to_thread.run_sync(_extract)
```

**Tests:**
- Mock DSPy LM. Verify entity extraction structure.
- Verify min word count guard.
- Verify relationship extraction requires >= 2 entities.
- Verify dynamic entity types from ontology.

---

#### Task 12: Text Chunking

**File to create:** `ontoextract/pipeline/chunking.py`

**Port from:**
- `backend/app/services/embedding_service.py` for `RecursiveCharacterTextSplitter` usage
- OntoGPT's sentence-window strategy for extraction chunking

```python
from dataclasses import dataclass

@dataclass
class TextChunk:
    text: str
    index: int
    start_char: int
    end_char: int

class TextChunker:
    def __init__(
        self,
        max_chunk_size: int = 4000,  # tokens approx
        overlap: int = 500,
    ):
        self.max_chunk_size = max_chunk_size
        self.overlap = overlap

    def chunk_text(self, text: str) -> list[TextChunk]:
        """Split text into overlapping chunks for extraction.
        Uses sentence boundaries to avoid splitting mid-sentence.
        """
        ...

    def needs_chunking(self, text: str) -> bool:
        """Check if text exceeds chunk size threshold."""
        return len(text.split()) > self.max_chunk_size

def merge_entities_across_chunks(
    chunk_entities: list[list[dict]],
) -> list[dict]:
    """Merge entities from multiple chunks.
    Dedup by exact name match (case-insensitive).
    Keep the entity with the richest description.
    """
    ...
```

**Tests:** Chunk a long document, verify overlap. Verify entity merging dedup.

---

#### Task 13: Extraction Pipeline Orchestrator

**File to create:** `ontoextract/pipeline/extraction_pipeline.py`

**Port from:** `backend/app/services/kg_pipeline.py` (`process_document_kg_background`)

```python
class ExtractionPipeline:
    def __init__(
        self,
        extraction_service: ExtractionService,
        schema_alignment_service: SchemaAlignmentService,
        kg_adapter: KGAdapter,
        chunker: TextChunker,
    ):
        ...

    async def process_document(
        self, session: AsyncSession, document_id: int, content: str
    ) -> dict:
        """Full pipeline for one document.

        Steps (port from kg_pipeline.py):
        1. Chunk text if needed
        2. Extract entities from each chunk
        3. Merge entities across chunks (dedup by name)
        4. Extract relationships (using merged entity list)
        5. Schema alignment (align_entities_batch + align_relationships_batch)
        6. KG persistence (kg_adapter.process_document_kg)
        7. Return {nodes_created, nodes_reused, edges_created}
        """
        # Step 1: Chunk
        if self.chunker.needs_chunking(content):
            chunks = self.chunker.chunk_text(content)
        else:
            chunks = [TextChunk(text=content, index=0, start_char=0, end_char=len(content))]

        # Step 2: Extract entities from each chunk
        chunk_entities = []
        for chunk in chunks:
            entities = await self.extraction_service.extract_entities(chunk.text)
            chunk_entities.append(entities)

        # Step 3: Merge across chunks
        entities = merge_entities_across_chunks(chunk_entities)

        if not entities:
            return {"nodes_created": 0, "nodes_reused": 0, "edges_created": 0}

        # Step 4: Extract relationships
        entity_names = [e["name"] for e in entities]
        relationships = await self.extraction_service.extract_relationships(
            content, entity_names
        )

        # Step 5 + 6: Alignment + persistence (handled inside kg_adapter)
        result = await self.kg_adapter.process_document_kg(
            session, document_id, entities, relationships
        )

        return result
```

**Tests:** Full integration test with mocked LLM. Verify chunked vs non-chunked paths.

---

### Phase 4: Batch Processing

---

#### Task 14: Job Service

**File to create:** `ontoextract/services/job_service.py`

```python
class JobService:
    async def create_job(
        self, session: AsyncSession, document_ids: list[int], ontology_config_id: int
    ) -> ExtractionJob:
        """Create a new extraction job."""
        ...

    async def get_job(self, session: AsyncSession, job_id: int) -> Optional[ExtractionJob]:
        ...

    async def update_job_progress(
        self, session: AsyncSession, job_id: int,
        processed: int = 0, failed: int = 0
    ):
        ...

    async def complete_job(self, session: AsyncSession, job_id: int, status: str):
        ...

    async def save_result(
        self, session: AsyncSession, job_id: int, document_id: int,
        status: str, nodes_created: int = 0, nodes_reused: int = 0,
        edges_created: int = 0, error_message: str = None,
        processing_time_ms: int = None,
    ) -> ExtractionResult:
        ...

    async def get_job_results(
        self, session: AsyncSession, job_id: int
    ) -> list[ExtractionResult]:
        ...
```

**Tests:** Job creation, progress updates, result aggregation.

---

#### Task 15: ARQ Worker

**Files to create:**
- `ontoextract/workers/arq_worker.py`
- `ontoextract/workers/tasks.py`

**`ontoextract/workers/tasks.py`**:
```python
import asyncio
import time
from ontoextract.config import settings

async def process_batch_job(ctx: dict, job_id: int):
    """ARQ task: process all documents in a batch job.

    Concurrency controlled by asyncio.Semaphore(BATCH_CONCURRENCY).
    Per-document error isolation.
    """
    session_factory = ctx["session_factory"]
    pipeline = ctx["pipeline"]
    job_service = ctx["job_service"]

    async with session_factory() as session:
        job = await job_service.get_job(session, job_id)
        await job_service.update_job_status(session, job_id, "running")

        document_ids = await job_service.get_job_document_ids(session, job_id)
        semaphore = asyncio.Semaphore(settings.BATCH_CONCURRENCY)

        async def process_one(doc_id: int):
            async with semaphore:
                start = time.monotonic()
                try:
                    async with session_factory() as doc_session:
                        doc = await doc_session.get(Document, doc_id)
                        result = await pipeline.process_document(
                            doc_session, doc_id, doc.content
                        )
                        elapsed_ms = int((time.monotonic() - start) * 1000)
                        await job_service.save_result(
                            doc_session, job_id, doc_id, "success",
                            result["nodes_created"], result["nodes_reused"],
                            result["edges_created"], processing_time_ms=elapsed_ms,
                        )
                except Exception as e:
                    elapsed_ms = int((time.monotonic() - start) * 1000)
                    async with session_factory() as err_session:
                        await job_service.save_result(
                            err_session, job_id, doc_id, "failed",
                            error_message=str(e), processing_time_ms=elapsed_ms,
                        )

        await asyncio.gather(*[process_one(did) for did in document_ids])

        # Finalize job
        async with session_factory() as final_session:
            results = await job_service.get_job_results(final_session, job_id)
            failed = sum(1 for r in results if r.status == "failed")
            status = "completed" if failed == 0 else "partially_failed"
            await job_service.complete_job(final_session, job_id, status)
```

**`ontoextract/workers/arq_worker.py`**:
```python
from arq import create_pool
from arq.connections import RedisSettings
from ontoextract.config import settings
from ontoextract.workers.tasks import process_batch_job

class WorkerSettings:
    functions = [process_batch_job]
    redis_settings = RedisSettings.from_dsn(settings.REDIS_URL)

    @staticmethod
    async def on_startup(ctx):
        # Initialize DB session factory, pipeline, services
        ...

    @staticmethod
    async def on_shutdown(ctx):
        # Close pools
        ...
```

**Run worker:** `uv run arq ontoextract.workers.arq_worker.WorkerSettings`

**Tests:** Mock pipeline, verify semaphore limits concurrency, verify error isolation.

---

#### Task 16: API Endpoints — Extraction + Jobs

**Files to create:**
- `ontoextract/api/routes/extraction.py`
- `ontoextract/api/routes/jobs.py`
- `ontoextract/api/schemas/extraction.py`
- `ontoextract/api/schemas/jobs.py`

**Extraction endpoints:**

```python
# POST /extract — synchronous single-document extraction
@router.post("/extract", response_model=ExtractionResponse)
async def extract_document(
    request: ExtractionRequest,  # {content, content_type?, title?, source_url?, metadata?}
    session: AsyncSession = Depends(get_db_session),
    pipeline: ExtractionPipeline = Depends(get_pipeline),
):
    # 1. Create Document record
    # 2. Run pipeline.process_document()
    # 3. Return result

# POST /batch — async batch job creation
@router.post("/batch", response_model=BatchJobResponse, status_code=202)
async def create_batch_job(
    request: BatchRequest,  # {documents: [{content, title?, ...}]}
    session: AsyncSession = Depends(get_db_session),
    job_service: JobService = Depends(get_job_service),
    redis_pool = Depends(get_redis_pool),
):
    # 1. Create Document records for each input
    # 2. Create ExtractionJob
    # 3. Enqueue to ARQ: await redis_pool.enqueue_job("process_batch_job", job.id)
    # 4. Return {job_id, status: "pending", total_documents}
```

**Job endpoints:**

```python
# GET /jobs/{job_id}
@router.get("/jobs/{job_id}", response_model=JobStatusResponse)
async def get_job_status(job_id: int, ...):
    # Return job with progress

# GET /jobs/{job_id}/results
@router.get("/jobs/{job_id}/results", response_model=list[ExtractionResultResponse])
async def get_job_results(job_id: int, ...):
    # Return per-document results

# DELETE /jobs/{job_id}
@router.delete("/jobs/{job_id}")
async def cancel_job(job_id: int, ...):
    # Mark job as cancelled (ARQ doesn't support mid-task cancellation natively)
```

**Tests:** TestClient integration tests for all endpoints.

---

### Phase 5: Graph Query API

---

#### Task 17: Graph Query Service

**File to create:** `ontoextract/services/graph_service.py`

**Port from:** `backend/app/services/graph_service.py`

**Key methods:**
```python
class GraphService:
    async def list_nodes(
        self, session: AsyncSession,
        type_uri: str = None, limit: int = 50, offset: int = 0
    ) -> list[KGNode]:
        ...

    async def get_node(self, session: AsyncSession, node_id: int) -> Optional[KGNode]:
        ...

    async def get_neighborhood(
        self, session: AsyncSession, node_id: int, hops: int = 1
    ) -> dict:
        """Return adjacent nodes and edges (1-hop or 2-hop).
        Port from graph_service.py get_neighborhood().
        """
        ...

    async def search_nodes(
        self, session: AsyncSession, query: str, limit: int = 10
    ) -> list[dict]:
        """Semantic vector search across kg_node.
        Embed query, search HNSW index, return with similarity scores.
        """
        ...

    async def extract_subgraph(
        self, session: AsyncSession, node_ids: list[int]
    ) -> dict:
        """Return all edges between the given node set."""
        ...
```

**Tests:** Query with type filters, semantic search with mocked embeddings, neighborhood traversal.

---

#### Task 18: Graph API Endpoints

**Files to create:**
- `ontoextract/api/routes/graph.py`
- `ontoextract/api/schemas/graph.py`

```python
@router.get("/graph/nodes")
async def list_nodes(type_uri: str = None, limit: int = 50, offset: int = 0, ...):
    ...

@router.get("/graph/nodes/{node_id}")
async def get_node(node_id: int, ...):
    ...

@router.get("/graph/nodes/{node_id}/neighborhood")
async def get_neighborhood(node_id: int, hops: int = 1, ...):
    ...

@router.get("/graph/edges")
async def list_edges(property_uri: str = None, limit: int = 50, offset: int = 0, ...):
    ...

@router.get("/graph/search")
async def search_graph(q: str, limit: int = 10, ...):
    ...

@router.post("/graph/subgraph")
async def extract_subgraph(request: SubgraphRequest, ...):  # {node_ids: [1, 2, 3]}
    ...
```

**Tests:** API integration tests with populated test graph.

---

### Phase 6: Ontology Management API

---

#### Task 19: Ontology API Endpoints

**Files to create:**
- `ontoextract/api/routes/ontology.py`
- `ontoextract/api/schemas/ontology.py`

```python
@router.post("/ontology/load", response_model=OntologyLoadResponse)
async def load_ontology(
    file: UploadFile,
    format: str = Query(..., regex="^(owl|rdf|linkml)$"),
    name: str = Query(...),
    session: AsyncSession = Depends(get_db_session),
    loader: OntologyLoaderService = Depends(get_ontology_loader),
):
    """Upload and parse an ontology file.
    Saves file to disk, parses, generates embeddings, seeds canonical tables.
    """
    ...

@router.get("/ontology/status", response_model=OntologyStatusResponse)
async def get_ontology_status(...):
    """Return current active ontology config with class/property counts."""
    ...

@router.get("/ontology/classes", response_model=list[CanonicalClassResponse])
async def list_classes(limit: int = 100, offset: int = 0, ...):
    ...

@router.get("/ontology/properties", response_model=list[CanonicalPropertyResponse])
async def list_properties(limit: int = 100, offset: int = 0, ...):
    ...
```

**Tests:** Upload sample ontology files in each format, verify parsing and seeding.

---

#### Task 20: Integration Testing + Docker Setup

**Files to create/update:**
- `tests/test_integration.py`
- `docker-compose.yml` (finalize)
- Register all routers in `main.py`

**Integration test** — End-to-end flow:
```python
async def test_full_pipeline():
    """
    1. Load sample ontology (POST /ontology/load with sample_schema.ttl)
    2. Verify classes loaded (GET /ontology/status)
    3. Extract single document (POST /extract)
    4. Verify nodes created (GET /graph/nodes)
    5. Verify edges created (GET /graph/edges)
    6. Semantic search (GET /graph/search?q=...)
    7. Submit batch (POST /batch with 3 docs)
    8. Poll until complete (GET /jobs/{id})
    9. Verify results (GET /jobs/{id}/results)
    10. Verify graph grew (GET /graph/nodes count increased)
    """
```

**Docker Compose** (finalize):
```yaml
services:
  db:
    image: pgvector/pgvector:pg16
    ports: ["5432:5432"]
    environment:
      POSTGRES_DB: ontoextract
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres

  redis:
    image: redis:7-alpine
    ports: ["6379:6379"]

  api:
    build: .
    ports: ["8000:8000"]
    depends_on: [db, redis]
    env_file: .env

  worker:
    build: .
    command: uv run arq ontoextract.workers.arq_worker.WorkerSettings
    depends_on: [db, redis]
    env_file: .env
```

---

## Configuration Reference

```bash
# .env.example

# Database
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/ontoextract
DB_POOL_SIZE=5
DB_MAX_OVERFLOW=10

# Redis
REDIS_URL=redis://localhost:6379

# LLM (use LiteLLM model strings)
LLM_EXTRACTION_MODEL=openai/gpt-4o-mini
LLM_JUDGE_MODEL=openai/gpt-4o-mini
LLM_EMBEDDING_MODEL=openai/text-embedding-3-small
EMBEDDING_DIMENSIONS=1536

# Provider API keys (set whichever you're using)
OPENAI_API_KEY=sk-...
# ANTHROPIC_API_KEY=sk-ant-...
# GOOGLE_API_KEY=AI...

# Alignment thresholds
HIGH_CONFIDENCE_THRESHOLD=0.85
MIN_THRESHOLD=0.50
SEMANTIC_DEDUP_THRESHOLD=0.88

# Batch processing
BATCH_CONCURRENCY=5
EMBED_BATCH_SIZE=20

# Extraction limits
MAX_ENTITIES_PER_DOCUMENT=15
MAX_RELATIONSHIPS_PER_DOCUMENT=20
MIN_CONTENT_WORDS=50

# API security
API_KEY=your-api-key-here
```

---

## Testing Commands

```bash
# Setup
docker compose up -d db redis
uv run alembic upgrade head

# Run all tests
uv run pytest tests/ -v

# Run specific test suites
uv run pytest tests/test_ontology_loader.py -v
uv run pytest tests/test_schema_alignment.py -v
uv run pytest tests/test_pipeline.py -v
uv run pytest tests/test_api/ -v

# Run integration tests (requires running DB + Redis)
uv run pytest tests/test_integration.py -v

# Start the API server
uv run uvicorn ontoextract.main:app --reload

# Start the ARQ worker
uv run arq ontoextract.workers.arq_worker.WorkerSettings

# Load an ontology (via API)
curl -X POST http://localhost:8000/ontology/load \
  -F "file=@schema.ttl" \
  -F "format=rdf" \
  -F "name=schema.org"

# Extract a single document
curl -X POST http://localhost:8000/extract \
  -H "Content-Type: application/json" \
  -d '{"content": "Albert Einstein developed the theory of relativity..."}'
```

---

## iCognition Source File Reference

These files from the iCognition codebase should be read when implementing each task:

| OntoExtract File | Port From | Key Patterns |
|---|---|---|
| `services/schema_alignment_service.py` | `backend/app/services/schema_alignment_service.py` | Thresholds, vector search SQL, LLM judge prompts, cache |
| `services/kg_adapter.py` | `backend/app/services/kg_adapter.py` | 4-stage dedup, batch embedding, audit trail |
| `services/extraction_service.py` | `backend/app/services/dspy_entity_service.py` | DSPy signatures, anyio async bridging, word count guard |
| `services/embedding_service.py` | `backend/app/services/embedding_service.py` | Batch pattern, EmbeddingResult dataclass |
| `services/wikidata_service.py` | `backend/app/services/wikidata_service.py` | Direct port (httpx, dataclasses) |
| `services/ontology_loader.py` | `backend/scripts/seed_ontology.py` | rdflib parsing, embedding text format, batch seeding |
| `models/canonical.py` | `backend/app/models_kg.py` | KGCanonicalClass, KGCanonicalProperty |
| `models/graph.py` | `backend/app/models_kg.py` | KGNode, KGEdge, KGNodeDocument |
| `db/database.py` | `backend/app/db/database.py` | Async engine, session factory, pool settings |
| `config.py` | `backend/app/core/config.py` | Pydantic Settings pattern |
