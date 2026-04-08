"""
Schema Alignment Service — maps raw LLM entity types and relationship labels
to canonical schema.org classes and properties via embedding similarity search
with LLM re-ranking for ambiguous cases.

Strategy:
  1. Embed the raw type/description
  2. Vector search kg_canonical_class / kg_canonical_property for top-K candidates
  3. If top-1 cosine similarity >= HIGH_CONFIDENCE_THRESHOLD → accept directly
  4. If top-1 >= MIN_THRESHOLD → LLM judges from top candidates
  5. If all candidates < MIN_THRESHOLD → LLM judges (may still find a valid match)
"""

import json
from dataclasses import dataclass
from typing import Optional, List

from google import genai
from google.genai import types

from sqlalchemy import text, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models_kg import KGCanonicalProperty
from app.services.embedding_service import EmbeddingService, get_embedding_service
from app.services.wikidata_service import get_wikidata_service
from app.utils.logging import get_logger

logger = get_logger(__name__)

# Cosine similarity thresholds
HIGH_CONFIDENCE_THRESHOLD = 0.85  # Accept top-1 without LLM re-ranking
MIN_THRESHOLD = 0.50              # Below this, skip LLM judge — too far off

# Entity type descriptions — mirrors the extraction prompt definitions.
# Used to build richer embedding queries that match the seed format
# ("{label}: {description}") in kg_canonical_class vectors.
ENTITY_TYPE_DESCRIPTIONS: dict[str, str] = {
    "person": "Key individuals, people, human beings",
    "organization": "Companies, institutions, government bodies, editorial boards",
    "institution": "Academic or governmental institutions",
    "location": "Important places, countries, cities, regions, geographic areas",
    "event": "Specific events or happenings",
    "technology": "Technologies, frameworks, or technical concepts",
    "product": "Products, services, or manufactured goods",
    "science": "Scientific disciplines, theories, research fields",
    "medical_condition": "Diseases, disorders, symptoms, health conditions",
    "organism": "Biological species, animals, plants, microorganisms",
    "regulation": "Laws, policies, standards, treaties",
    "financial": "Financial instruments, markets, economic concepts",
    "creative_work": "Books, films, artworks, publications, TV shows",
    "concept": "Abstract ideas, principles, or themes",
}


@dataclass
class AlignmentResult:
    """Result of aligning a raw type/label to a canonical schema.org entry."""
    canonical_id: Optional[int]
    uri: Optional[str]
    label: Optional[str]
    similarity_score: float
    matched: bool  # True if a canonical match was found


class SchemaAlignmentService:
    """Aligns raw entity types and relationship labels to schema.org canonical entries."""

    def __init__(self, embedding_service: Optional[EmbeddingService] = None):
        self.embedding_service = embedding_service or get_embedding_service()
        self.wikidata_service = get_wikidata_service()
        self.genai_client = genai.Client(api_key=settings.GOOGLE_API_KEY)
        self.judge_model = settings.GEMINI_FLASH_LITE_MODEL
        # Cache for class alignment results: (raw_type, chosen_label) → AlignmentResult
        # Avoids repeated embedding + LLM judge for the same raw_type + result combo
        self._class_cache: dict[str, AlignmentResult] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def align_entity_type(
        self,
        session: AsyncSession,
        entity_name: str,
        raw_type: str,
        description: str = "",
        top_k: int = 5,
    ) -> AlignmentResult:
        """
        Find the best schema.org class for a raw entity.

        Strategy:
        1. Embedding search on raw_type → get top-K candidates
        2. If top-1 >= HIGH_CONFIDENCE → accept directly
        3. Otherwise → LLM judge picks from candidates given full entity context

        Args:
            session:      Active DB session.
            entity_name:  Entity name (e.g. "Google").
            raw_type:     LLM-assigned type (e.g. "organization").
            description:  LLM-assigned description.
            top_k:        Number of candidates to retrieve.

        Returns:
            AlignmentResult with canonical class info (or matched=False).
        """
        # Check cache — avoids embedding + LLM judge for repeated types
        if raw_type in self._class_cache:
            cached = self._class_cache[raw_type]
            logger.debug(f"Class alignment cache hit for '{entity_name}' (raw_type='{raw_type}'): {cached.label}")
            return cached

        # Match the embedding format used by seed_ontology.py: "{label}: {description}"
        # Using the entity type description (not the entity's own description) gives
        # stable, high-quality matches — "person: Key individuals, people, human beings"
        # matches "Person: A person (alive, dead, undead, or fictional)." reliably.
        human_type = raw_type.replace("_", " ")
        type_desc = ENTITY_TYPE_DESCRIPTIONS.get(raw_type, "")
        query_text = f"{human_type}: {type_desc}" if type_desc else human_type
        candidates = await self._search_canonical_classes(session, query_text, top_k)

        if not candidates:
            logger.warning(f"Class alignment: no candidates for raw_type='{raw_type}' entity='{entity_name}'")
            return AlignmentResult(None, None, None, 0.0, matched=False)

        top = candidates[0]
        top_candidates = [(c["label"], round(c["similarity"], 3)) for c in candidates]
        logger.info(
            f"Class alignment for '{entity_name}' (raw_type='{raw_type}'): "
            f"top candidates = {top_candidates}"
        )

        # Types that need per-entity LLM judging (subclass selection depends on context)
        context_dependent_types = {"location"}

        # High confidence — accept directly and cache
        if top["similarity"] >= HIGH_CONFIDENCE_THRESHOLD:
            logger.debug(f"High-confidence match: {top['label']} ({top['similarity']:.3f})")
            result = AlignmentResult(
                canonical_id=top["id"],
                uri=top["uri"],
                label=top["label"],
                similarity_score=top["similarity"],
                matched=True,
            )
            if raw_type not in context_dependent_types:
                self._class_cache[raw_type] = result
            return result

        # Below high confidence — LLM judge picks from candidates.
        # The LLM sees the full entity context (name + description) and can
        # make nuanced distinctions (e.g. "Iran" → Country vs "Moscow" → City).
        judge_result = await self._llm_judge_class(
            entity_name=entity_name,
            raw_type=raw_type,
            description=description,
            candidates=candidates,
        )
        if judge_result:
            return judge_result

        # LLM judge failed — fall back to top embedding match if decent
        if top["similarity"] >= MIN_THRESHOLD:
            return self._pick_best(candidates)

        return AlignmentResult(None, None, None, top["similarity"], matched=False)

    async def align_relationship(
        self,
        session: AsyncSession,
        raw_relationship_type: str,
        from_entity_name: str = "",
        to_entity_name: str = "",
        from_type_uri: Optional[str] = None,
        to_type_uri: Optional[str] = None,
        top_k: int = 10,
    ) -> AlignmentResult:
        """
        Find the best canonical property for a raw relationship.

        Strategy:
        1. Embedding search → get top-K candidates from kg_canonical_property
        2. If top-1 >= HIGH_CONFIDENCE → accept directly
        3. If top-1 >= MIN_THRESHOLD → LLM judge picks or creates new
        4. If top-1 < MIN_THRESHOLD → LLM judge creates new canonical property

        Args:
            session:                Active DB session.
            raw_relationship_type:  LLM-assigned label (e.g. "works_for").
            from_entity_name:       Name of the source entity (for LLM context).
            to_entity_name:         Name of the target entity (for LLM context).
            from_type_uri:          Schema URI of the source node (for domain filtering).
            to_type_uri:            Schema URI of the target node (for range filtering).
            top_k:                  Number of candidates to retrieve.

        Returns:
            AlignmentResult with canonical property info (or matched=False).
        """
        # Match the embedding format used by seed_ontology.py: "{label}: {description}"
        # Build a richer query using relationship context for better similarity scores.
        human_label = raw_relationship_type.replace("_", " ")
        context = f"{from_entity_name} {human_label} {to_entity_name}".strip()
        query_text = f"{human_label}: {context}" if context else human_label
        candidates = await self._search_canonical_properties(
            session, query_text, top_k,
            domain_uri=from_type_uri,
            range_uri=to_type_uri,
        )

        top_candidates = [(c["label"], round(c["similarity"], 3)) for c in candidates[:5]]
        logger.info(
            f"Property alignment for '{raw_relationship_type}': "
            f"top candidates = {top_candidates}"
        )

        top = candidates[0] if candidates else None

        # High confidence — accept directly
        if top and top["similarity"] >= HIGH_CONFIDENCE_THRESHOLD:
            logger.debug(f"High-confidence property match: {top['label']} ({top['similarity']:.3f})")
            return AlignmentResult(
                canonical_id=top["id"],
                uri=top["uri"],
                label=top["label"],
                similarity_score=top["similarity"],
                matched=True,
            )

        # Moderate or low confidence — LLM judge picks or creates new
        judge_result = await self._llm_judge_relationship(
            session=session,
            raw_relationship_type=raw_relationship_type,
            from_entity_name=from_entity_name,
            to_entity_name=to_entity_name,
            candidates=candidates[:5] if candidates else [],
        )
        if judge_result:
            return judge_result

        # LLM judge failed — fall back to top embedding match if available
        if top and top["similarity"] >= MIN_THRESHOLD:
            return self._pick_best(candidates)

        return AlignmentResult(None, None, None, 0.0, matched=False)

    # ------------------------------------------------------------------
    # Batch helpers
    # ------------------------------------------------------------------

    async def align_entities_batch(
        self,
        session: AsyncSession,
        entities: List[dict],
    ) -> List[dict]:
        """
        Align a list of raw entities. Adds 'alignment' key to each dict.

        Each entity dict must have: name, type, description
        """
        for entity in entities:
            result = await self.align_entity_type(
                session,
                entity_name=entity["name"],
                raw_type=entity["type"],
                description=entity.get("description", ""),
            )
            entity["alignment"] = result
        return entities

    async def align_relationships_batch(
        self,
        session: AsyncSession,
        relationships: List[dict],
        entity_type_map: dict[str, Optional[str]],
    ) -> List[dict]:
        """
        Align a list of raw relationships. Adds 'alignment' key to each dict.

        Args:
            relationships: List of dicts with from_entity, to_entity, relationship_type.
            entity_type_map: Mapping of entity name → schema_type_uri (may be None).
        """
        for rel in relationships:
            from_uri = entity_type_map.get(rel["from_entity"])
            to_uri = entity_type_map.get(rel["to_entity"])
            result = await self.align_relationship(
                session,
                raw_relationship_type=rel["relationship_type"],
                from_entity_name=rel["from_entity"],
                to_entity_name=rel["to_entity"],
                from_type_uri=from_uri,
                to_type_uri=to_uri,
            )
            rel["alignment"] = result
        return relationships

    # ------------------------------------------------------------------
    # LLM judge
    # ------------------------------------------------------------------

    async def _llm_judge_class(
        self,
        entity_name: str,
        raw_type: str,
        description: str,
        candidates: List[dict],
    ) -> Optional[AlignmentResult]:
        """
        Use LLM to pick the best schema.org class from embedding candidates.

        The LLM sees the full entity context (name, type, description) plus
        the candidate classes with their descriptions — it can make nuanced
        distinctions that pure embedding similarity misses.
        """
        candidate_lines = "\n".join(
            f"  {i+1}. {c['label']} ({c['uri']}) — similarity: {c['similarity']:.3f}"
            for i, c in enumerate(candidates)
        )

        prompt = f"""You are a schema.org ontology expert. Given an entity extracted from a document,
pick the BEST matching schema.org class from the candidates below.

Entity:
  Name: {entity_name}
  Raw type: {raw_type}
  Description: {description}

Candidate schema.org classes:
{candidate_lines}

Instructions:
- Pick the most specific class that accurately describes this entity.
- For countries (e.g. "Iran", "Australia"), prefer "Country" over "Place".
- For cities (e.g. "Moscow", "Beijing"), prefer "City" over "Place".
- For continents (e.g. "Europe", "Africa"), prefer "Continent" over "Place".
- If none of the candidates are appropriate, respond with "none".
- Respond with ONLY the class label (e.g. "Country") or "none". No explanation."""

        try:
            response = await self.genai_client.aio.models.generate_content(
                model=self.judge_model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.0,
                    max_output_tokens=50,
                ),
            )

            chosen_label = response.text.strip().strip('"').strip("'")
            logger.info(f"LLM judge for '{entity_name}': chose '{chosen_label}'")

            if chosen_label.lower() == "none":
                return AlignmentResult(None, None, None, 0.0, matched=False)

            # Find the chosen candidate (normalize underscores/spaces)
            chosen_normalized = chosen_label.lower().replace("_", " ")
            for c in candidates:
                if c["label"].lower().replace("_", " ") == chosen_normalized:
                    return AlignmentResult(
                        canonical_id=c["id"],
                        uri=c["uri"],
                        label=c["label"],
                        similarity_score=c["similarity"],
                        matched=True,
                    )

            # LLM returned a label not in candidates — log and return None
            logger.warning(
                f"LLM judge returned '{chosen_label}' which is not in candidates for '{entity_name}'"
            )
            return None

        except Exception as e:
            logger.warning(f"LLM judge failed for '{entity_name}': {e}")
            return None

    async def _llm_judge_relationship(
        self,
        session: AsyncSession,
        raw_relationship_type: str,
        from_entity_name: str,
        to_entity_name: str,
        candidates: List[dict],
    ) -> Optional[AlignmentResult]:
        """
        Use LLM to pick the best canonical property from combined candidates:
        - Existing canonical properties (schema.org + previously created)
        - Wikidata properties (searched by raw relationship label)

        If none fit, the LLM proposes a NEW icognition property as last resort.
        """
        # Search Wikidata for property candidates
        human_label = raw_relationship_type.replace("_", " ")
        wikidata_props = await self.wikidata_service.search_properties(human_label, limit=5)

        # Build combined candidate list for the LLM
        existing_lines = "\n".join(
            f"  EXISTING {i+1}. {c['label']} ({c['uri']})"
            for i, c in enumerate(candidates)
        ) if candidates else "  (none)"

        wikidata_lines = "\n".join(
            f"  WIKIDATA {i+1}. {p.label} ({p.property_id}) — {p.description or 'no description'}"
            for i, p in enumerate(wikidata_props)
        ) if wikidata_props else "  (none)"

        prompt = f"""You are an ontology expert building a knowledge graph.
Given a relationship extracted from a document, pick the best canonical property
from the sources below, or propose a NEW one as a last resort.

Extracted relationship:
  From: {from_entity_name}
  Relationship: {human_label}
  To: {to_entity_name}

Source 1 — Existing canonical properties (schema.org + custom):
{existing_lines}

Source 2 — Wikidata properties:
{wikidata_lines}

Instructions:
- Prefer EXISTING properties if they accurately capture the relationship.
- If no existing property fits but a WIKIDATA property does, pick that.
- Only propose NEW if neither source has an appropriate match.
- New properties must be GENERAL, REUSABLE, and NEUTRAL.
  - GOOD: "trades_with", "educated_at", "covers_topic"
  - BAD: "made_cheese_trade_deal_with", "wants_to_bomb"
- Keep labels in snake_case, 2-4 words.

Respond in EXACTLY one of these formats:
EXISTING: <label>
WIKIDATA: <property_id> | <label>
NEW: <label> | <one-sentence description>

Examples:
EXISTING: author
WIKIDATA: P69 | educated at
NEW: trades_with | Indicates a trade or commercial agreement between two entities."""

        try:
            response = await self.genai_client.aio.models.generate_content(
                model=self.judge_model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.0,
                    max_output_tokens=100,
                ),
            )

            answer = response.text.strip()
            logger.info(f"LLM judge for relationship '{raw_relationship_type}': {answer}")

            if answer.upper().startswith("EXISTING:"):
                chosen_label = answer.split(":", 1)[1].strip().strip('"').strip("'")
                # Normalize: LLM may return underscores, candidates use spaces
                chosen_normalized = chosen_label.lower().replace("_", " ")
                for c in candidates:
                    if c["label"].lower().replace("_", " ") == chosen_normalized:
                        return AlignmentResult(
                            canonical_id=c["id"],
                            uri=c["uri"],
                            label=c["label"],
                            similarity_score=c["similarity"],
                            matched=True,
                        )
                logger.warning(
                    f"LLM judge chose existing '{chosen_label}' but not in candidates"
                )
                return None

            elif answer.upper().startswith("WIKIDATA:"):
                wd_part = answer.split(":", 1)[1].strip()
                if "|" in wd_part:
                    prop_id, prop_label = [s.strip() for s in wd_part.split("|", 1)]
                else:
                    prop_id = wd_part.strip()
                    prop_label = None

                # Find the matching Wikidata property for description
                wd_description = None
                for wp in wikidata_props:
                    if wp.property_id.upper() == prop_id.upper():
                        prop_label = prop_label or wp.label
                        wd_description = wp.description
                        break

                if not prop_label:
                    prop_label = prop_id

                # Persist as a canonical property with Wikidata URI
                label_normalized = prop_label.strip().lower().replace(" ", "_")
                uri = f"https://www.wikidata.org/wiki/Property:{prop_id}"
                description = wd_description or f"Wikidata property: {prop_label}"

                result = await self._create_canonical_property(
                    session, label_normalized, description, uri=uri
                )
                return result

            elif answer.upper().startswith("NEW:"):
                new_part = answer.split(":", 1)[1].strip()
                if "|" in new_part:
                    new_label, new_description = [s.strip() for s in new_part.split("|", 1)]
                else:
                    new_label = new_part.strip()
                    new_description = f"Relationship: {new_label.replace('_', ' ')}"

                new_label = new_label.strip().lower().replace(" ", "_")
                result = await self._create_canonical_property(
                    session, new_label, new_description
                )
                return result

            else:
                logger.warning(f"LLM judge returned unexpected format: {answer}")
                return None

        except Exception as e:
            logger.warning(f"LLM judge failed for relationship '{raw_relationship_type}': {e}")
            return None

    async def _create_canonical_property(
        self,
        session: AsyncSession,
        label: str,
        description: str,
        uri: Optional[str] = None,
    ) -> Optional[AlignmentResult]:
        """
        Create a new canonical property. Uses the given URI or generates an
        icognition.ai URI. Generates an embedding and inserts into
        kg_canonical_property. If a property with the same URI already exists,
        returns the existing one.
        """
        if uri is None:
            uri = f"https://icognition.ai/property/{label}"

        # Check if this property already exists
        existing = await session.execute(
            select(KGCanonicalProperty).where(KGCanonicalProperty.uri == uri)
        )
        existing_prop = existing.scalars().first()
        if existing_prop:
            logger.debug(f"Canonical property already exists: {uri}")
            return AlignmentResult(
                canonical_id=existing_prop.id,
                uri=existing_prop.uri,
                label=existing_prop.label,
                similarity_score=1.0,
                matched=True,
            )

        # Generate embedding matching seed format: "{label}: {description}"
        embed_text = f"{label.replace('_', ' ')}: {description}"
        vector = None
        try:
            embed_result = await self.embedding_service.generate_embedding(
                text=embed_text,
                task_type="RETRIEVAL_DOCUMENT",
            )
            if embed_result.success:
                vector = embed_result.embedding
        except Exception as e:
            logger.warning(f"Failed to embed new property '{label}': {e}")

        # Insert the new canonical property
        new_prop = KGCanonicalProperty(
            uri=uri,
            label=label.replace("_", " "),
            description=description,
            vector=vector,
        )
        session.add(new_prop)
        await session.flush()

        logger.info(f"Created new canonical property: {uri} — {description}")

        return AlignmentResult(
            canonical_id=new_prop.id,
            uri=new_prop.uri,
            label=new_prop.label,
            similarity_score=1.0,
            matched=True,
        )

    # ------------------------------------------------------------------
    # Vector search internals
    # ------------------------------------------------------------------

    async def _search_canonical_classes(
        self,
        session: AsyncSession,
        query_text: str,
        top_k: int,
    ) -> List[dict]:
        """Search kg_canonical_class by embedding similarity."""
        embedding_result = await self.embedding_service.generate_embedding(
            text=query_text,
            task_type="RETRIEVAL_QUERY",
        )
        if not embedding_result.success:
            logger.warning(f"Embedding generation failed for class query: {query_text[:80]}")
            return []

        query_vector = json.dumps(embedding_result.embedding)

        stmt = text("""
            SELECT
                id,
                uri,
                label,
                1 - (vector <=> CAST(:query_vector AS vector)) AS similarity
            FROM kg_canonical_class
            WHERE vector IS NOT NULL
            ORDER BY vector <=> CAST(:query_vector AS vector)
            LIMIT :limit
        """)
        result = await session.execute(stmt, {"query_vector": query_vector, "limit": top_k})
        rows = result.fetchall()

        return [
            {"id": r.id, "uri": r.uri, "label": r.label, "similarity": r.similarity}
            for r in rows
        ]

    async def _search_canonical_properties(
        self,
        session: AsyncSession,
        query_text: str,
        top_k: int,
        domain_uri: Optional[str] = None,
        range_uri: Optional[str] = None,
    ) -> List[dict]:
        """Search kg_canonical_property by embedding similarity, optionally filtered by domain/range."""
        embedding_result = await self.embedding_service.generate_embedding(
            text=query_text,
            task_type="RETRIEVAL_QUERY",
        )
        if not embedding_result.success:
            logger.warning(f"Embedding generation failed for property query: {query_text[:80]}")
            return []

        query_vector = json.dumps(embedding_result.embedding)

        # Build optional domain/range filters
        where_clauses = ["vector IS NOT NULL"]
        params: dict = {"query_vector": query_vector, "limit": top_k}

        if domain_uri:
            where_clauses.append("(domain_class_uri IS NULL OR domain_class_uri = :domain_uri)")
            params["domain_uri"] = domain_uri
        if range_uri:
            where_clauses.append("(range_class_uri IS NULL OR range_class_uri = :range_uri)")
            params["range_uri"] = range_uri

        where_str = " AND ".join(where_clauses)

        stmt = text(f"""
            SELECT
                id,
                uri,
                label,
                1 - (vector <=> CAST(:query_vector AS vector)) AS similarity
            FROM kg_canonical_property
            WHERE {where_str}
            ORDER BY vector <=> CAST(:query_vector AS vector)
            LIMIT :limit
        """)
        result = await session.execute(stmt, params)
        rows = result.fetchall()

        return [
            {"id": r.id, "uri": r.uri, "label": r.label, "similarity": r.similarity}
            for r in rows
        ]

    # ------------------------------------------------------------------
    # Selection logic
    # ------------------------------------------------------------------

    def _pick_best(self, candidates: List[dict]) -> AlignmentResult:
        """
        Fallback: pick the best candidate based on similarity score alone.
        Used for relationship alignment and when LLM judge fails.
        """
        top = candidates[0]
        score = top["similarity"]

        if score < MIN_THRESHOLD:
            logger.debug(f"No match: top candidate {top['label']} scored {score:.3f} < {MIN_THRESHOLD}")
            return AlignmentResult(None, None, None, score, matched=False)

        if score >= HIGH_CONFIDENCE_THRESHOLD:
            logger.debug(f"High-confidence match: {top['label']} ({score:.3f})")
        else:
            # Moderate confidence — accept for now, LLM re-ranking can be added as enhancement
            logger.debug(f"Moderate-confidence match: {top['label']} ({score:.3f})")

        return AlignmentResult(
            canonical_id=top["id"],
            uri=top["uri"],
            label=top["label"],
            similarity_score=score,
            matched=True,
        )


# ---------------------------------------------------------------------------
# Global singleton
# ---------------------------------------------------------------------------

_schema_alignment_service: Optional[SchemaAlignmentService] = None


def get_schema_alignment_service() -> SchemaAlignmentService:
    global _schema_alignment_service
    if _schema_alignment_service is None:
        _schema_alignment_service = SchemaAlignmentService()
    return _schema_alignment_service
