"""
Graph exploration service — fuzzy search, neighborhood expansion, entity/relationship detail.

Reads from KG tables: kg_node, kg_edge, kg_node_document.
"""

from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.utils.logging import get_logger

logger = get_logger(__name__)


class GraphService:
    """Service for graph exploration queries using KG tables."""

    def __init__(self, session: AsyncSession):
        self.session = session

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    async def search(
        self,
        q: str,
        user_id: str,
        result_type: Optional[str] = None,
        entity_type: Optional[str] = None,
        limit: int = 20,
        threshold: float = 0.3,
    ) -> dict:
        """Fuzzy search across nodes (by label), edges (by property_label), and documents (by title/content)."""
        parts = []
        params: dict = {"q": q, "threshold": threshold, "limit": min(limit, 100), "user_id": user_id}

        if result_type in (None, "entity"):
            entity_filter = ""
            if entity_type:
                entity_filter = "AND n.raw_type = :entity_type"
                params["entity_type"] = entity_type
            parts.append(f"""
                SELECT n.id AS id, n.label AS label, n.raw_type AS type,
                       'entity' AS result_type,
                       similarity(n.label, :q) AS sim
                FROM kg_node n
                WHERE similarity(n.label, :q) >= :threshold
                  AND n.user_id = :user_id
                  {entity_filter}
            """)

        if result_type in (None, "relationship"):
            parts.append("""
                SELECT MIN(e.id) AS id, e.property_label AS label,
                       'relationship' AS type,
                       'relationship' AS result_type,
                       MAX(similarity(e.property_label, :q)) AS sim
                FROM kg_edge e
                WHERE similarity(e.property_label, :q) >= :threshold
                  AND e.user_id = :user_id
                GROUP BY e.property_label
            """)

        if result_type in (None, "document"):
            parts.append("""
                SELECT d.id AS id, d.title AS label,
                       'document' AS type,
                       'document' AS result_type,
                       word_similarity(:q, d.title) AS sim
                FROM document d
                WHERE word_similarity(:q, d.title) >= :threshold
                  AND d.user_id = :user_id
            """)
            parts.append("""
                SELECT d.id AS id, d.title AS label,
                       'document' AS type,
                       'document' AS result_type,
                       word_similarity(:q, d.ai_markdown_content) AS sim
                FROM document d
                WHERE d.ai_markdown_content IS NOT NULL
                  AND word_similarity(:q, d.ai_markdown_content) >= :threshold
                  AND d.user_id = :user_id
                  AND d.id NOT IN (
                      SELECT d2.id FROM document d2
                      WHERE word_similarity(:q, d2.title) >= :threshold
                        AND d2.user_id = :user_id
                  )
            """)

        if not parts:
            return {"query": q, "total": 0, "results": []}

        union_sql = " UNION ALL ".join(parts)
        sql = text(f"{union_sql} ORDER BY sim DESC LIMIT :limit")

        result = await self.session.execute(sql, params)
        rows = result.mappings().all()

        return {
            "query": q,
            "total": len(rows),
            "results": [
                {
                    "id": row["id"],
                    "label": row["label"],
                    "type": row["type"],
                    "result_type": row["result_type"],
                    "similarity": round(float(row["sim"]), 3),
                }
                for row in rows
            ],
        }

    # ------------------------------------------------------------------
    # Entity (Node) detail
    # ------------------------------------------------------------------

    async def get_entity(self, entity_id: int) -> Optional[dict]:
        """Fetch full node detail including canonical class and linked documents."""
        sql = text("""
            SELECT n.id, n.label AS name, n.raw_type AS type, n.description,
                   n.schema_type_uri, n.wikidata_id,
                   cc.label AS canonical_type
            FROM kg_node n
            LEFT JOIN kg_canonical_class cc ON cc.id = n.canonical_class_id
            WHERE n.id = :entity_id
        """)
        result = await self.session.execute(sql, {"entity_id": entity_id})
        entity = result.mappings().first()
        if not entity:
            return None

        docs_sql = text("""
            SELECT d.id, d.title
            FROM document d
            JOIN kg_node_document nd ON nd.document_id = d.id
            WHERE nd.node_id = :entity_id
            ORDER BY d.title
        """)
        docs_result = await self.session.execute(docs_sql, {"entity_id": entity_id})
        docs = [dict(r) for r in docs_result.mappings().all()]

        return {
            "id": entity["id"],
            "name": entity["name"],
            "type": entity["type"],
            "canonical_type": entity["canonical_type"],
            "schema_type_uri": entity["schema_type_uri"],
            "wikidata_id": entity["wikidata_id"],
            "description": entity["description"],
            "document_count": len(docs),
            "documents": docs,
        }

    # ------------------------------------------------------------------
    # Neighborhood
    # ------------------------------------------------------------------

    async def get_neighborhood(
        self, entity_id: int, depth: int = 1, limit: int = 50
    ) -> dict:
        """Fetch 1-hop neighborhood: the node, all directly connected nodes, edges, and linked documents."""
        depth = min(depth, 2)
        limit = min(limit, 100)

        edges_sql = text("""
            SELECT e.id, e.from_node_id AS from_entity_id, e.to_node_id AS to_entity_id,
                   e.property_label AS relationship_type, e.property_uri
            FROM kg_edge e
            WHERE e.from_node_id = :entity_id OR e.to_node_id = :entity_id
            ORDER BY e.id
            LIMIT :limit
        """)
        edges_result = await self.session.execute(
            edges_sql, {"entity_id": entity_id, "limit": limit}
        )
        rels = [dict(r) for r in edges_result.mappings().all()]

        # Collect all node IDs
        node_ids = {entity_id}
        for r in rels:
            node_ids.add(r["from_entity_id"])
            node_ids.add(r["to_entity_id"])

        if not node_ids:
            return {"entities": [], "relationships": [], "documents": [], "center_entity_id": entity_id}

        node_id_list = list(node_ids)
        nodes_sql = text("""
            SELECT n.id, n.label AS name, n.raw_type AS type,
                   cc.label AS canonical_type, n.wikidata_id
            FROM kg_node n
            LEFT JOIN kg_canonical_class cc ON cc.id = n.canonical_class_id
            WHERE n.id = ANY(:ids)
        """)
        nodes_result = await self.session.execute(nodes_sql, {"ids": node_id_list})
        entities = [dict(r) for r in nodes_result.mappings().all()]

        # Fetch documents linked to neighborhood nodes
        docs_sql = text("""
            SELECT DISTINCT d.id, d.title
            FROM document d
            JOIN kg_node_document nd ON nd.document_id = d.id
            WHERE nd.node_id = ANY(:node_ids)
            ORDER BY d.title
        """)
        docs_result = await self.session.execute(docs_sql, {"node_ids": node_id_list})
        documents = [dict(r) for r in docs_result.mappings().all()]

        # Node-document links for graph edges
        links_sql = text("""
            SELECT nd.node_id AS entity_id, nd.document_id
            FROM kg_node_document nd
            WHERE nd.node_id = ANY(:node_ids)
        """)
        links_result = await self.session.execute(links_sql, {"node_ids": node_id_list})
        entity_document_links = [dict(r) for r in links_result.mappings().all()]

        return {
            "entities": entities,
            "relationships": rels,
            "documents": documents,
            "entity_document_links": entity_document_links,
            "center_entity_id": entity_id,
        }

    # ------------------------------------------------------------------
    # Relationship (Edge) detail
    # ------------------------------------------------------------------

    async def get_relationship(self, relationship_id: int) -> Optional[dict]:
        """Fetch full edge detail with endpoint nodes and source document."""
        sql = text("""
            SELECT e.id, e.property_label AS relationship_type,
                   e.property_uri, e.raw_relationship_type,
                   n1.id AS from_id, n1.label AS from_name, n1.raw_type AS from_type,
                   cc1.label AS from_canonical_type, n1.wikidata_id AS from_wikidata_id,
                   n2.id AS to_id, n2.label AS to_name, n2.raw_type AS to_type,
                   cc2.label AS to_canonical_type, n2.wikidata_id AS to_wikidata_id,
                   e.source_document_id
            FROM kg_edge e
            JOIN kg_node n1 ON n1.id = e.from_node_id
            JOIN kg_node n2 ON n2.id = e.to_node_id
            LEFT JOIN kg_canonical_class cc1 ON cc1.id = n1.canonical_class_id
            LEFT JOIN kg_canonical_class cc2 ON cc2.id = n2.canonical_class_id
            WHERE e.id = :relationship_id
        """)
        result = await self.session.execute(sql, {"relationship_id": relationship_id})
        row = result.mappings().first()
        if not row:
            return None

        # Source document (kg_edge has direct FK, not a junction table)
        source_documents = []
        if row["source_document_id"]:
            doc_sql = text("SELECT id, title FROM document WHERE id = :doc_id")
            doc_result = await self.session.execute(doc_sql, {"doc_id": row["source_document_id"]})
            doc_row = doc_result.mappings().first()
            if doc_row:
                source_documents.append(dict(doc_row))

        return {
            "id": row["id"],
            "relationship_type": row["relationship_type"],
            "property_uri": row["property_uri"],
            "raw_relationship_type": row["raw_relationship_type"],
            "from_entity": {
                "id": row["from_id"], "name": row["from_name"], "type": row["from_type"],
                "canonical_type": row["from_canonical_type"], "wikidata_id": row["from_wikidata_id"],
            },
            "to_entity": {
                "id": row["to_id"], "name": row["to_name"], "type": row["to_type"],
                "canonical_type": row["to_canonical_type"], "wikidata_id": row["to_wikidata_id"],
            },
            "source_documents": source_documents,
        }

    async def get_entity_relationships(
        self,
        entity_id: int,
        direction: str = "both",
        limit: int = 50,
    ) -> list[dict]:
        """List edges connected to a node."""
        limit = min(limit, 100)

        if direction == "from":
            where = "e.from_node_id = :entity_id"
        elif direction == "to":
            where = "e.to_node_id = :entity_id"
        else:
            where = "(e.from_node_id = :entity_id OR e.to_node_id = :entity_id)"

        sql = text(f"""
            SELECT e.id, e.from_node_id AS from_entity_id, e.to_node_id AS to_entity_id,
                   e.property_label AS relationship_type, e.property_uri
            FROM kg_edge e
            WHERE {where}
            ORDER BY e.property_label
            LIMIT :limit
        """)
        result = await self.session.execute(
            sql, {"entity_id": entity_id, "limit": limit}
        )
        return [dict(r) for r in result.mappings().all()]

    async def get_entity_documents(self, entity_id: int, limit: int = 50) -> list[dict]:
        """List documents a node appears in."""
        sql = text("""
            SELECT d.id, d.title
            FROM document d
            JOIN kg_node_document nd ON nd.document_id = d.id
            WHERE nd.node_id = :entity_id
            ORDER BY d.title
            LIMIT :limit
        """)
        result = await self.session.execute(
            sql, {"entity_id": entity_id, "limit": min(limit, 100)}
        )
        return [dict(r) for r in result.mappings().all()]

    # ------------------------------------------------------------------
    # Document detail
    # ------------------------------------------------------------------

    async def get_document(self, document_id: int) -> Optional[dict]:
        """Fetch document detail including ai_markdown_content."""
        sql = text("""
            SELECT id, title, url, ai_markdown_content
            FROM document
            WHERE id = :document_id
        """)
        result = await self.session.execute(sql, {"document_id": document_id})
        row = result.mappings().first()
        if not row:
            return None

        entities_sql = text("""
            SELECT n.id, n.label AS name, n.raw_type AS type,
                   cc.label AS canonical_type, n.wikidata_id
            FROM kg_node n
            JOIN kg_node_document nd ON nd.node_id = n.id
            LEFT JOIN kg_canonical_class cc ON cc.id = n.canonical_class_id
            WHERE nd.document_id = :document_id
        """)
        entities_result = await self.session.execute(entities_sql, {"document_id": document_id})
        entities = [dict(r) for r in entities_result.mappings().all()]

        return {
            "id": row["id"],
            "title": row["title"],
            "url": row["url"],
            "ai_markdown_content": row["ai_markdown_content"],
            "entities": entities,
        }

    # ------------------------------------------------------------------
    # Subgraph (batch)
    # ------------------------------------------------------------------

    async def get_subgraph(self, entity_ids: list[int], include_relationships: bool = True) -> dict:
        """Batch-fetch a subgraph for multiple node IDs."""
        nodes_sql = text("""
            SELECT n.id, n.label AS name, n.raw_type AS type,
                   cc.label AS canonical_type, n.wikidata_id
            FROM kg_node n
            LEFT JOIN kg_canonical_class cc ON cc.id = n.canonical_class_id
            WHERE n.id = ANY(:ids)
        """)
        nodes_result = await self.session.execute(nodes_sql, {"ids": entity_ids})
        entities = [dict(r) for r in nodes_result.mappings().all()]

        rels = []
        if include_relationships and entity_ids:
            rels_sql = text("""
                SELECT e.id, e.from_node_id AS from_entity_id, e.to_node_id AS to_entity_id,
                       e.property_label AS relationship_type, e.property_uri
                FROM kg_edge e
                WHERE e.from_node_id = ANY(:ids) AND e.to_node_id = ANY(:ids)
            """)
            rels_result = await self.session.execute(rels_sql, {"ids": entity_ids})
            rels = [dict(r) for r in rels_result.mappings().all()]

        docs_sql = text("""
            SELECT DISTINCT d.id, d.title
            FROM document d
            JOIN kg_node_document nd ON nd.document_id = d.id
            WHERE nd.node_id = ANY(:ids)
        """)
        docs_result = await self.session.execute(docs_sql, {"ids": entity_ids})
        documents = [dict(r) for r in docs_result.mappings().all()]

        doc_ids = [d["id"] for d in documents]
        entity_document_links = []
        if doc_ids:
            links_sql = text("""
                SELECT nd.node_id AS entity_id, nd.document_id
                FROM kg_node_document nd
                WHERE nd.node_id = ANY(:entity_ids) AND nd.document_id = ANY(:doc_ids)
            """)
            links_result = await self.session.execute(links_sql, {"entity_ids": entity_ids, "doc_ids": doc_ids})
            entity_document_links = [dict(r) for r in links_result.mappings().all()]

        return {"entities": entities, "relationships": rels, "documents": documents, "entity_document_links": entity_document_links, "center_entity_id": None}

    # ------------------------------------------------------------------
    # KG context (for chat enrichment)
    # ------------------------------------------------------------------

    async def get_entity_kg_context(self, entity_ids: list[int]) -> list[dict]:
        """
        For a list of node IDs, return structured KG context:
        each node with its relationships and linked document titles.
        """
        if not entity_ids:
            return []

        nodes_sql = text(
            "SELECT id, label AS name, raw_type AS type, description FROM kg_node WHERE id = ANY(:ids)"
        )
        nodes_result = await self.session.execute(nodes_sql, {"ids": entity_ids})
        nodes = {r["id"]: dict(r) for r in nodes_result.mappings().all()}

        rels_sql = text("""
            SELECT e.property_label AS relationship_type,
                   n1.label AS from_name,
                   n2.label AS to_name
            FROM kg_edge e
            JOIN kg_node n1 ON n1.id = e.from_node_id
            JOIN kg_node n2 ON n2.id = e.to_node_id
            WHERE e.from_node_id = ANY(:ids) OR e.to_node_id = ANY(:ids)
            LIMIT 50
        """)
        rels_result = await self.session.execute(rels_sql, {"ids": entity_ids})
        all_rels = rels_result.mappings().all()

        docs_sql = text("""
            SELECT nd.node_id AS entity_id, d.title
            FROM kg_node_document nd
            JOIN document d ON d.id = nd.document_id
            WHERE nd.node_id = ANY(:ids)
            ORDER BY nd.node_id, d.title
            LIMIT 50
        """)
        docs_result = await self.session.execute(docs_sql, {"ids": entity_ids})
        all_docs = docs_result.mappings().all()

        result = []
        for eid in entity_ids:
            if eid not in nodes:
                continue
            e = nodes[eid]
            rels = [
                {"from_entity": r["from_name"], "relationship_type": r["relationship_type"], "to_entity": r["to_name"]}
                for r in all_rels
                if r["from_name"] == e["name"] or r["to_name"] == e["name"]
            ]
            seen = set()
            unique_rels = []
            for r in rels:
                key = (r["from_entity"], r["relationship_type"], r["to_entity"])
                if key not in seen:
                    seen.add(key)
                    unique_rels.append(r)

            docs = [r["title"] for r in all_docs if r["entity_id"] == eid]

            result.append({
                "id": e["id"],
                "name": e["name"],
                "type": e["type"],
                "description": e["description"],
                "relationships": unique_rels,
                "documents": docs,
            })
        return result

    # ------------------------------------------------------------------
    # Discovery graph (hub landing page)
    # ------------------------------------------------------------------

    async def get_discovery_graph(
        self, user_id: str, source: Optional[str] = None,
        theme_id: Optional[int] = None,
        research_session_id: Optional[int] = None,
        limit: int = 30
    ) -> dict:
        """
        Return a discovery graph for the hub landing page:
        popular nodes (by edge + document count) and recent nodes,
        plus edges between them.
        """
        limit = min(limit, 50)
        half = limit // 2

        source_filter = ""
        theme_filter = ""
        params: dict = {"user_id": user_id, "half": half, "limit": limit}
        if source:
            source_filter = """
                AND n.id IN (
                    SELECT nd2.node_id FROM kg_node_document nd2
                    JOIN document d2 ON d2.id = nd2.document_id
                    WHERE d2.user_id = :user_id
                      AND (d2.site_name = :source
                           OR CASE WHEN d2.url IS NOT NULL
                              THEN substring(d2.url from '://([^/]+)')
                              ELSE NULL END = :source)
                )
            """
            params["source"] = source
        if theme_id:
            theme_filter = """
                AND n.id IN (
                    SELECT nd3.node_id FROM kg_node_document nd3
                    JOIN theme_document td ON td.document_id = nd3.document_id
                    WHERE td.theme_id = :theme_id
                )
            """
            params["theme_id"] = theme_id

        popular_sql = text(f"""
            SELECT n.id, n.label AS name, n.raw_type AS type,
                   cc.label AS canonical_type, n.wikidata_id
            FROM kg_node n
            LEFT JOIN kg_canonical_class cc ON cc.id = n.canonical_class_id
            LEFT JOIN kg_node_document nd ON nd.node_id = n.id
            LEFT JOIN kg_edge er ON er.from_node_id = n.id OR er.to_node_id = n.id
            WHERE n.user_id = :user_id
              {source_filter}
              {theme_filter}
            GROUP BY n.id, n.label, n.raw_type, cc.label, n.wikidata_id
            ORDER BY COUNT(DISTINCT er.id) + COUNT(DISTINCT nd.document_id) DESC
            LIMIT :half
        """)
        popular_result = await self.session.execute(popular_sql, params)
        popular = [dict(r) for r in popular_result.mappings().all()]

        popular_ids = {e["id"] for e in popular}

        recent_sql = text(f"""
            SELECT n.id, n.label AS name, n.raw_type AS type,
                   cc.label AS canonical_type, n.wikidata_id
            FROM kg_node n
            LEFT JOIN kg_canonical_class cc ON cc.id = n.canonical_class_id
            JOIN kg_node_document nd ON nd.node_id = n.id
            JOIN document d ON d.id = nd.document_id
            WHERE d.user_id = :user_id
              {source_filter}
              {theme_filter}
            GROUP BY n.id, n.label, n.raw_type, cc.label, n.wikidata_id
            ORDER BY MAX(d.created_at) DESC
            LIMIT :half
        """)
        recent_result = await self.session.execute(recent_sql, params)
        recent = [dict(r) for r in recent_result.mappings().all()]

        all_entities = list(popular)
        for e in recent:
            if e["id"] not in popular_ids:
                all_entities.append(e)

        entity_ids = [e["id"] for e in all_entities]

        # ── Research-specific path: start from documents in the research session ──
        if research_session_id:
            return await self._build_research_graph(
                user_id, research_session_id, limit
            )

        # ── Theme-specific path: start from themed documents ──
        if theme_id:
            return await self._build_theme_graph(
                user_id, theme_id, all_entities, entity_ids, limit
            )

        if not entity_ids:
            return {"entities": [], "relationships": [], "documents": [], "center_entity_id": None}

        # ── Standard (non-theme) path ──
        rels_sql = text("""
            SELECT e.id, e.from_node_id AS from_entity_id, e.to_node_id AS to_entity_id,
                   e.property_label AS relationship_type, e.property_uri
            FROM kg_edge e
            WHERE e.from_node_id = ANY(:ids) AND e.to_node_id = ANY(:ids)
        """)
        rels_result = await self.session.execute(rels_sql, {"ids": entity_ids})
        rels = [dict(r) for r in rels_result.mappings().all()]

        docs_sql = text("""
            SELECT DISTINCT d.id, d.title
            FROM document d
            JOIN kg_node_document nd ON nd.document_id = d.id
            WHERE nd.node_id = ANY(:ids) AND d.user_id = :user_id
        """)
        docs_result = await self.session.execute(docs_sql, {"ids": entity_ids, "user_id": user_id})
        documents = [dict(r) for r in docs_result.mappings().all()]

        doc_ids = [d["id"] for d in documents]
        entity_document_links = []
        if doc_ids:
            links_sql = text("""
                SELECT nd.node_id AS entity_id, nd.document_id
                FROM kg_node_document nd
                WHERE nd.node_id = ANY(:entity_ids)
                  AND nd.document_id = ANY(:doc_ids)
            """)
            links_result = await self.session.execute(links_sql, {"entity_ids": entity_ids, "doc_ids": doc_ids})
            entity_document_links = [dict(r) for r in links_result.mappings().all()]

        return {
            "entities": all_entities,
            "relationships": rels,
            "documents": documents,
            "entity_document_links": entity_document_links,
            "center_entity_id": None,
        }

    async def _build_theme_graph(
        self,
        user_id: str,
        theme_id: int,
        hint_entities: list[dict],
        hint_entity_ids: list[int],
        limit: int,
    ) -> dict:
        """
        Build a discovery graph for a theme. Starts from themed documents,
        finds all their KG entities and relationships, and includes orphan
        documents (no KG nodes) as standalone document nodes.
        """
        # 1. Get all documents in this theme
        docs_sql = text("""
            SELECT d.id, d.title
            FROM document d
            JOIN theme_document td ON td.document_id = d.id
            WHERE td.theme_id = :theme_id AND d.user_id = :user_id
        """)
        docs_result = await self.session.execute(
            docs_sql, {"theme_id": theme_id, "user_id": user_id}
        )
        documents = [dict(r) for r in docs_result.mappings().all()]
        doc_ids = [d["id"] for d in documents]

        logger.info(
            f"_build_theme_graph: theme={theme_id}, docs={len(documents)}, "
            f"doc_ids={doc_ids[:5]}..."
        )

        if not doc_ids:
            return {
                "entities": [], "relationships": [], "documents": [],
                "entity_document_links": [], "center_entity_id": None,
            }

        # 2. Find all KG entities connected to these documents
        entities_sql = text("""
            SELECT DISTINCT n.id, n.label AS name, n.raw_type AS type,
                   cc.label AS canonical_type, n.wikidata_id
            FROM kg_node n
            LEFT JOIN kg_canonical_class cc ON cc.id = n.canonical_class_id
            JOIN kg_node_document nd ON nd.node_id = n.id
            WHERE nd.document_id = ANY(:doc_ids) AND n.user_id = :user_id
            LIMIT :limit
        """)
        entities_result = await self.session.execute(
            entities_sql, {"doc_ids": doc_ids, "user_id": user_id, "limit": limit}
        )
        entities = [dict(r) for r in entities_result.mappings().all()]
        entity_ids = [e["id"] for e in entities]

        # 3. Find relationships between these entities
        rels = []
        if entity_ids:
            rels_sql = text("""
                SELECT e.id, e.from_node_id AS from_entity_id,
                       e.to_node_id AS to_entity_id,
                       e.property_label AS relationship_type, e.property_uri
                FROM kg_edge e
                WHERE e.from_node_id = ANY(:ids) AND e.to_node_id = ANY(:ids)
            """)
            rels_result = await self.session.execute(rels_sql, {"ids": entity_ids})
            rels = [dict(r) for r in rels_result.mappings().all()]

        # 4. Entity-document links
        entity_document_links = []
        if entity_ids and doc_ids:
            links_sql = text("""
                SELECT nd.node_id AS entity_id, nd.document_id
                FROM kg_node_document nd
                WHERE nd.node_id = ANY(:entity_ids)
                  AND nd.document_id = ANY(:doc_ids)
            """)
            links_result = await self.session.execute(
                links_sql, {"entity_ids": entity_ids, "doc_ids": doc_ids}
            )
            entity_document_links = [dict(r) for r in links_result.mappings().all()]

        return {
            "entities": entities,
            "relationships": rels,
            "documents": documents,
            "entity_document_links": entity_document_links,
            "center_entity_id": None,
        }

    async def _build_research_graph(
        self,
        user_id: str,
        research_session_id: int,
        limit: int,
    ) -> dict:
        """
        Build a discovery graph filtered to documents from a single research session.
        Shows all docs saved by that research run plus any entities extracted from them.
        """
        # 1. Get all documents in this research session
        docs_sql = text("""
            SELECT d.id, d.title
            FROM document d
            WHERE d.research_session_id = :rs_id AND d.user_id = :user_id
            ORDER BY d.created_at DESC
        """)
        docs_result = await self.session.execute(
            docs_sql, {"rs_id": research_session_id, "user_id": user_id}
        )
        documents = [dict(r) for r in docs_result.mappings().all()]
        doc_ids = [d["id"] for d in documents]

        if not doc_ids:
            return {
                "entities": [], "relationships": [], "documents": [],
                "entity_document_links": [], "center_entity_id": None,
            }

        # 2. Find KG entities connected to these documents (if any — research docs
        #    may not have KG extraction complete yet)
        entities_sql = text("""
            SELECT DISTINCT n.id, n.label AS name, n.raw_type AS type,
                   cc.label AS canonical_type, n.wikidata_id
            FROM kg_node n
            LEFT JOIN kg_canonical_class cc ON cc.id = n.canonical_class_id
            JOIN kg_node_document nd ON nd.node_id = n.id
            WHERE nd.document_id = ANY(:doc_ids) AND n.user_id = :user_id
            LIMIT :limit
        """)
        entities_result = await self.session.execute(
            entities_sql, {"doc_ids": doc_ids, "user_id": user_id, "limit": limit}
        )
        entities = [dict(r) for r in entities_result.mappings().all()]
        entity_ids = [e["id"] for e in entities]

        # 3. Find relationships between these entities
        rels = []
        if entity_ids:
            rels_sql = text("""
                SELECT e.id, e.from_node_id AS from_entity_id,
                       e.to_node_id AS to_entity_id,
                       e.property_label AS relationship_type, e.property_uri
                FROM kg_edge e
                WHERE e.from_node_id = ANY(:ids) AND e.to_node_id = ANY(:ids)
            """)
            rels_result = await self.session.execute(rels_sql, {"ids": entity_ids})
            rels = [dict(r) for r in rels_result.mappings().all()]

        # 4. Entity-document links
        entity_document_links = []
        if entity_ids and doc_ids:
            links_sql = text("""
                SELECT nd.node_id AS entity_id, nd.document_id
                FROM kg_node_document nd
                WHERE nd.node_id = ANY(:entity_ids)
                  AND nd.document_id = ANY(:doc_ids)
            """)
            links_result = await self.session.execute(
                links_sql, {"entity_ids": entity_ids, "doc_ids": doc_ids}
            )
            entity_document_links = [dict(r) for r in links_result.mappings().all()]

        return {
            "entities": entities,
            "relationships": rels,
            "documents": documents,
            "entity_document_links": entity_document_links,
            "center_entity_id": None,
        }

    # ------------------------------------------------------------------
    # Research sessions
    # ------------------------------------------------------------------

    async def get_research_sessions(self, user_id: str) -> list[dict]:
        """Return all research sessions for a user with document counts."""
        sql = text("""
            SELECT rs.id, rs.brief, rs.status, rs.created_at,
                   COUNT(d.id) AS doc_count
            FROM research_session rs
            LEFT JOIN document d ON d.research_session_id = rs.id
            WHERE rs.user_id = :user_id
            GROUP BY rs.id, rs.brief, rs.status, rs.created_at
            ORDER BY rs.created_at DESC
        """)
        result = await self.session.execute(sql, {"user_id": user_id})
        return [dict(r) for r in result.mappings().all()]

    # ------------------------------------------------------------------
    # Document sources
    # ------------------------------------------------------------------

    async def get_document_sources(self, user_id: str) -> list[dict]:
        """Return document sources grouped by site_name/domain, with counts."""
        sql = text("""
            SELECT
                COALESCE(
                    NULLIF(site_name, ''),
                    substring(url from '://([^/]+)'),
                    'Other'
                ) AS source_name,
                COUNT(*) AS doc_count
            FROM document
            WHERE user_id = :user_id
            GROUP BY source_name
            ORDER BY doc_count DESC
        """)
        result = await self.session.execute(sql, {"user_id": user_id})
        return [{"site_name": r["source_name"], "count": r["doc_count"]} for r in result.mappings().all()]

    # ------------------------------------------------------------------
    # Document subgraph
    # ------------------------------------------------------------------

    async def get_document_subgraph(self, document_id: int) -> dict:
        """Fetch full subgraph for a document."""
        entities_sql = text("""
            SELECT n.id, n.label AS name, n.raw_type AS type,
                   cc.label AS canonical_type, n.wikidata_id
            FROM kg_node n
            JOIN kg_node_document nd ON nd.node_id = n.id
            LEFT JOIN kg_canonical_class cc ON cc.id = n.canonical_class_id
            WHERE nd.document_id = :document_id
        """)
        entities_result = await self.session.execute(entities_sql, {"document_id": document_id})
        entities = [dict(r) for r in entities_result.mappings().all()]

        # Get edges sourced from this document
        rels_sql = text("""
            SELECT e.id, e.from_node_id AS from_entity_id, e.to_node_id AS to_entity_id,
                   e.property_label AS relationship_type, e.property_uri
            FROM kg_edge e
            WHERE e.source_document_id = :document_id
        """)
        rels_result = await self.session.execute(rels_sql, {"document_id": document_id})
        rels = [dict(r) for r in rels_result.mappings().all()]

        doc_sql = text("SELECT id, title FROM document WHERE id = :document_id")
        doc_result = await self.session.execute(doc_sql, {"document_id": document_id})
        doc_row = doc_result.mappings().first()
        documents = [dict(doc_row)] if doc_row else []

        entity_ids = [e["id"] for e in entities]
        entity_document_links = [{"entity_id": eid, "document_id": document_id} for eid in entity_ids]

        return {"entities": entities, "relationships": rels, "documents": documents, "entity_document_links": entity_document_links, "center_entity_id": None}
