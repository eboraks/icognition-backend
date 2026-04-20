"""
KG Adapter — converts DSPy entity/relationship extraction results into
kg_node / kg_edge / kg_node_document records with schema.org alignment.

This runs alongside the existing DspyEntityAdapter (dual-write pattern).
"""

import asyncio
from typing import List, Dict, Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func, text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.models_kg import KGNode, KGEdge, KGNodeDocument
from app.services.schema_alignment_service import (
    SchemaAlignmentService,
    get_schema_alignment_service,
)
from app.services.embedding_service import get_embedding_service
from app.services.wikidata_service import get_wikidata_service, WikidataEntity
from app.utils.logging import get_logger

logger = get_logger(__name__)


class KGAdapter:
    """
    Adapter that takes raw DSPy extraction results, aligns them to schema.org,
    and persists as kg_node / kg_edge records.
    """

    def __init__(self, session: AsyncSession):
        self.session = session
        self.alignment_service = get_schema_alignment_service()
        self.embedding_service = get_embedding_service()
        self.wikidata_service = get_wikidata_service()

    async def process_document_kg(
        self,
        user_id: str,
        document_id: int,
        raw_entities: List[Dict[str, Any]],
        raw_relationships: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Full pipeline: align + dedup + persist nodes and edges.

        Args:
            user_id:            Firebase UID.
            document_id:        Source document ID.
            raw_entities:       DSPy entities (name, type, description).
            raw_relationships:  DSPy relationships (from_entity, to_entity, relationship_type).

        Returns:
            Summary dict with counts.
        """
        if not raw_entities:
            return {"nodes_created": 0, "nodes_reused": 0, "edges_created": 0}

        # --- Phase 1: Nodes ---
        # Align all entity types to schema.org classes
        aligned_entities = await self.alignment_service.align_entities_batch(
            self.session, raw_entities
        )

        # Find-or-create kg_node for each entity
        name_to_node: Dict[str, KGNode] = {}
        nodes_created = 0
        nodes_reused = 0

        for entity in aligned_entities:
            node, created = await self._find_or_create_node(
                entity, user_id
            )
            if node:
                name_to_node[entity["name"]] = node
                if created:
                    nodes_created += 1
                else:
                    nodes_reused += 1

                # Link node to document
                await self._link_node_document(node.id, document_id)

        await self.session.flush()

        # --- Phase 2: Edges ---
        # Build entity name → schema_type_uri map for relationship alignment
        entity_type_map = {
            name: node.schema_type_uri
            for name, node in name_to_node.items()
        }

        aligned_rels = await self.alignment_service.align_relationships_batch(
            self.session, raw_relationships, entity_type_map
        )

        # Collect edges that need creation (dedup check), then batch-embed
        pending_edges: list[dict] = []
        seen_edge_keys: set[tuple] = set()
        for rel in aligned_rels:
            from_node = name_to_node.get(rel["from_entity"])
            to_node = name_to_node.get(rel["to_entity"])
            if not from_node or not to_node or from_node.id == to_node.id:
                continue

            alignment = rel.get("alignment")
            raw_type = rel["relationship_type"]
            property_uri = alignment.uri if (alignment and alignment.matched) else None
            property_label = alignment.label if (alignment and alignment.matched) else raw_type.replace("_", " ")

            # In-batch dedup: skip if we already have this edge queued
            edge_key = (from_node.id, to_node.id, property_uri, document_id)
            if edge_key in seen_edge_keys:
                continue
            seen_edge_keys.add(edge_key)

            # DB dedup check
            existing = await self.session.execute(
                select(KGEdge).where(
                    and_(
                        KGEdge.from_node_id == from_node.id,
                        KGEdge.to_node_id == to_node.id,
                        KGEdge.property_uri == property_uri
                        if property_uri
                        else KGEdge.property_uri.is_(None),
                        KGEdge.source_document_id == document_id,
                    )
                )
            )
            if existing.scalars().first():
                continue

            edge_text = f"{from_node.label} {property_label} {to_node.label}"
            pending_edges.append({
                "from_node": from_node,
                "to_node": to_node,
                "alignment": alignment,
                "raw_type": raw_type,
                "property_uri": property_uri,
                "property_label": property_label,
                "edge_text": edge_text,
            })

        # Batch-embed all edge texts concurrently
        edge_texts = [e["edge_text"] for e in pending_edges]
        edge_vectors = await self._embed_texts_batch(edge_texts) if edge_texts else []

        # Insert edges with their embeddings
        edges_created = 0
        for edge_data, vector in zip(pending_edges, edge_vectors):
            alignment = edge_data["alignment"]
            edge = KGEdge(
                from_node_id=edge_data["from_node"].id,
                to_node_id=edge_data["to_node"].id,
                canonical_property_id=alignment.canonical_id if (alignment and alignment.matched) else None,
                property_uri=edge_data["property_uri"],
                property_label=edge_data["property_label"],
                raw_relationship_type=edge_data["raw_type"],
                source_document_id=document_id,
                vector=vector,
                user_id=user_id,
            )
            self.session.add(edge)
            edges_created += 1

        await self.session.flush()

        result = {
            "nodes_created": nodes_created,
            "nodes_reused": nodes_reused,
            "edges_created": edges_created,
        }
        logger.info(
            f"KG processing for doc {document_id}: "
            f"{nodes_created} new nodes, {nodes_reused} reused, {edges_created} edges"
        )
        return result

    # ------------------------------------------------------------------
    # Node operations
    # ------------------------------------------------------------------

    # Minimum cosine similarity to consider a semantic match for dedup
    SEMANTIC_DEDUP_THRESHOLD = 0.88

    async def _find_or_create_node(
        self,
        entity: Dict[str, Any],
        user_id: str,
    ) -> tuple[Optional[KGNode], bool]:
        """
        Find existing kg_node or create a new one.

        Dedup strategy (in order):
        1. Exact match on (label_normalized, schema_type_uri, user_id)
        2. Semantic match via vector similarity on "name - description"
        3. Wikidata lookup → match existing node by wikidata_id
        4. Create new node with embedding + Wikidata enrichment

        Returns:
            (node, created) — created is True if a new node was inserted.
        """
        name = entity["name"]
        raw_type = entity["type"]
        description = entity.get("description", "")
        alignment = entity.get("alignment")

        label_normalized = name.strip().lower()
        schema_type_uri = alignment.uri if (alignment and alignment.matched) else None

        # 1. Exact match on normalized label + type + user
        query = select(KGNode).where(
            and_(
                KGNode.label_normalized == label_normalized,
                KGNode.user_id == user_id,
                KGNode.schema_type_uri == schema_type_uri
                if schema_type_uri
                else KGNode.schema_type_uri.is_(None),
            )
        )
        result = await self.session.execute(query)
        existing = result.scalars().first()

        if existing:
            # Backfill embedding if missing
            if existing.vector is None:
                await self._generate_node_embedding(existing)
            if not existing.wikidata_id:
                await self._enrich_node_with_wikidata(existing, name)
            return existing, False

        # 2. Semantic match via vector similarity
        node_text = f"{name} - {description}"
        node_vector = await self._embed_text(node_text)

        if node_vector:
            semantic_match = await self._find_semantic_match(
                node_vector, user_id, schema_type_uri
            )
            if semantic_match:
                logger.info(
                    f"Semantic dedup: '{name}' matched existing node "
                    f"'{semantic_match.label}' (id={semantic_match.id})"
                )
                return semantic_match, False

        # 3. Wikidata lookup for dedup + enrichment
        wikidata_entity = await self._lookup_wikidata(name)

        if wikidata_entity and wikidata_entity.wikidata_id:
            wd_query = select(KGNode).where(
                and_(
                    KGNode.wikidata_id == wikidata_entity.wikidata_id,
                    KGNode.user_id == user_id,
                )
            )
            wd_result = await self.session.execute(wd_query)
            wd_existing = wd_result.scalars().first()

            if wd_existing:
                logger.info(
                    f"Wikidata dedup: '{name}' matched existing node "
                    f"'{wd_existing.label}' via {wikidata_entity.wikidata_id}"
                )
                return wd_existing, False

        # 4. Create new node with embedding + Wikidata enrichment.
        # Race-safe insert: if a concurrent worker created the same
        # (label_normalized, schema_type_uri, user_id) row between our step-1
        # lookup and now, ON CONFLICT DO NOTHING suppresses the duplicate and
        # we re-query to return the winner.
        canonical_label = name
        if wikidata_entity and wikidata_entity.label:
            canonical_label = wikidata_entity.label

        canonical_normalized = canonical_label.strip().lower()
        node_values = {
            "label": canonical_label,
            "label_normalized": canonical_normalized,
            "canonical_class_id": alignment.canonical_id if (alignment and alignment.matched) else None,
            "schema_type_uri": schema_type_uri,
            "raw_type": raw_type,
            "raw_description": description,
            "description": wikidata_entity.description if wikidata_entity and wikidata_entity.description else description,
            "wikidata_id": wikidata_entity.wikidata_id if wikidata_entity else None,
            "vector": node_vector,
            "user_id": user_id,
        }

        stmt = (
            pg_insert(KGNode)
            .values(**node_values)
            .on_conflict_do_nothing(
                index_elements=["label_normalized", "schema_type_uri", "user_id"]
            )
            .returning(KGNode.id)
        )
        result = await self.session.execute(stmt)
        inserted_id = result.scalar_one_or_none()

        if inserted_id is not None:
            fetched = await self.session.execute(
                select(KGNode).where(KGNode.id == inserted_id)
            )
            node = fetched.scalar_one()
            logger.debug(
                f"Created kg_node: '{canonical_label}' type={schema_type_uri or raw_type} "
                f"wikidata={wikidata_entity.wikidata_id if wikidata_entity else 'none'} "
                f"(match={'yes' if alignment and alignment.matched else 'no'})"
            )
            return node, True

        # Concurrent insert won — fetch the node that now exists.
        conflict_query = select(KGNode).where(
            and_(
                KGNode.label_normalized == canonical_normalized,
                KGNode.user_id == user_id,
                KGNode.schema_type_uri == schema_type_uri
                if schema_type_uri
                else KGNode.schema_type_uri.is_(None),
            )
        )
        conflict_result = await self.session.execute(conflict_query)
        existing_node = conflict_result.scalars().first()
        if existing_node:
            logger.info(
                f"Race dedup: '{canonical_label}' matched concurrently-created "
                f"node (id={existing_node.id})"
            )
            return existing_node, False

        logger.warning(
            f"ON CONFLICT suppressed insert of '{canonical_label}' but no "
            f"matching row found — skipping"
        )
        return None, False

    async def _embed_text(self, text: str) -> Optional[List[float]]:
        """Generate an embedding vector for the given text."""
        try:
            result = await self.embedding_service.generate_embedding(
                text=text,
                task_type="RETRIEVAL_DOCUMENT",
            )
            if result.success:
                return result.embedding
        except Exception as e:
            logger.warning(f"Failed to generate embedding: {e}")
        return None

    async def _embed_texts_batch(self, texts: List[str]) -> List[Optional[List[float]]]:
        """Generate embeddings for multiple texts concurrently."""
        tasks = [self._embed_text(t) for t in texts]
        return await asyncio.gather(*tasks)

    async def _generate_node_embedding(self, node: KGNode) -> None:
        """Backfill embedding on an existing node that's missing one."""
        node_text = f"{node.label} - {node.description or ''}"
        vector = await self._embed_text(node_text)
        if vector:
            node.vector = vector
            await self.session.flush()

    async def _find_semantic_match(
        self,
        query_vector: List[float],
        user_id: str,
        schema_type_uri: Optional[str],
    ) -> Optional[KGNode]:
        """
        Find an existing node by cosine similarity against stored vectors.
        Only matches nodes for the same user and schema type.
        """
        vector_str = "[" + ",".join(str(v) for v in query_vector) + "]"

        type_filter = (
            "AND schema_type_uri = :schema_type_uri"
            if schema_type_uri
            else "AND schema_type_uri IS NULL"
        )

        sql = text(f"""
            SELECT id, label, 1 - (vector <=> CAST(:query_vector AS vector)) AS similarity
            FROM kg_node
            WHERE user_id = :user_id
              AND vector IS NOT NULL
              {type_filter}
            ORDER BY vector <=> CAST(:query_vector AS vector)
            LIMIT 1
        """)

        params: Dict[str, Any] = {
            "query_vector": vector_str,
            "user_id": user_id,
        }
        if schema_type_uri:
            params["schema_type_uri"] = schema_type_uri

        result = await self.session.execute(sql, params)
        row = result.first()

        if row and row.similarity >= self.SEMANTIC_DEDUP_THRESHOLD:
            # Fetch the full KGNode object
            node_result = await self.session.execute(
                select(KGNode).where(KGNode.id == row.id)
            )
            return node_result.scalars().first()

        return None

    async def _lookup_wikidata(self, name: str) -> Optional[WikidataEntity]:
        """Search Wikidata for an entity by name. Returns best match or None."""
        try:
            results = await self.wikidata_service.search_entities(name, limit=3)
            if results:
                # Pick the first result — Wikidata returns best match first
                return results[0]
        except Exception as e:
            logger.warning(f"Wikidata lookup failed for '{name}': {e}")
        return None

    async def _enrich_node_with_wikidata(self, node: KGNode, name: str) -> None:
        """Try to enrich an existing node with Wikidata ID if it's missing."""
        try:
            wd = await self._lookup_wikidata(name)
            if wd and wd.wikidata_id:
                node.wikidata_id = wd.wikidata_id
                # Only update label if it won't conflict with an existing node
                if wd.label and wd.label.strip().lower() != node.label_normalized:
                    new_normalized = wd.label.strip().lower()
                    conflict = await self.session.execute(
                        select(KGNode.id).where(
                            and_(
                                KGNode.label_normalized == new_normalized,
                                KGNode.schema_type_uri == node.schema_type_uri,
                                KGNode.user_id == node.user_id,
                                KGNode.id != node.id,
                            )
                        )
                    )
                    if not conflict.scalars().first():
                        node.label = wd.label
                        node.label_normalized = new_normalized
                if wd.description and not node.description:
                    node.description = wd.description
                await self.session.flush()
                logger.debug(f"Enriched kg_node '{node.label}' with Wikidata {wd.wikidata_id}")
        except Exception as e:
            logger.warning(f"Wikidata enrichment failed for node {node.id}: {e}")

    async def _link_node_document(self, node_id: int, document_id: int) -> None:
        """Create kg_node_document link if not exists."""
        existing = await self.session.execute(
            select(KGNodeDocument).where(
                and_(
                    KGNodeDocument.node_id == node_id,
                    KGNodeDocument.document_id == document_id,
                )
            )
        )
        if not existing.scalars().first():
            self.session.add(KGNodeDocument(node_id=node_id, document_id=document_id))

