"""
Graph exploration service — fuzzy search, neighborhood expansion, entity/relationship detail.
"""

from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.utils.logging import get_logger

logger = get_logger(__name__)


class GraphService:
    """Service for graph exploration queries."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def search(
        self,
        q: str,
        user_id: str,
        result_type: Optional[str] = None,
        entity_type: Optional[str] = None,
        limit: int = 20,
        threshold: float = 0.3,
    ) -> dict:
        """Fuzzy search across entities (by name), relationships (by type), and documents (by title/content)."""
        parts = []
        params: dict = {"q": q, "threshold": threshold, "limit": min(limit, 100), "user_id": user_id}

        if result_type in (None, "entity"):
            entity_filter = ""
            if entity_type:
                entity_filter = "AND e.type = :entity_type"
                params["entity_type"] = entity_type
            parts.append(f"""
                SELECT MIN(e.id) AS id, e.name AS label, e.type, 'entity' AS result_type,
                       MAX(similarity(e.name, :q)) AS sim
                FROM entities e
                WHERE similarity(e.name, :q) >= :threshold
                  AND (e.user_id = :user_id OR e.user_id IS NULL)
                  {entity_filter}
                GROUP BY e.name, e.type
            """)

        if result_type in (None, "relationship"):
            parts.append("""
                SELECT MIN(r.id) AS id, r.relationship_type AS label,
                       'relationship' AS type,
                       'relationship' AS result_type,
                       MAX(similarity(r.relationship_type, :q)) AS sim
                FROM entity_relationships r
                WHERE similarity(r.relationship_type, :q) >= :threshold
                GROUP BY r.relationship_type
            """)

        if result_type in (None, "document"):
            # Use word_similarity() for documents — it matches the best substring,
            # so short queries like "U.S." score high against long titles.
            parts.append("""
                SELECT d.id AS id, d.title AS label,
                       'document' AS type,
                       'document' AS result_type,
                       word_similarity(:q, d.title) AS sim
                FROM document d
                WHERE word_similarity(:q, d.title) >= :threshold
                  AND d.user_id = :user_id
            """)
            # Search documents by ai_markdown_content (dedup: skip docs already matched by title)
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

    async def get_entity(self, entity_id: int) -> Optional[dict]:
        """Fetch full entity detail including linked documents."""
        entity_sql = text(
            "SELECT id, name, type, description FROM entities WHERE id = :entity_id"
        )
        result = await self.session.execute(entity_sql, {"entity_id": entity_id})
        entity = result.mappings().first()
        if not entity:
            return None

        docs_sql = text("""
            SELECT d.id, d.title
            FROM document d
            JOIN entity_documents ed ON ed.document_id = d.id
            WHERE ed.entity_id = :entity_id
            ORDER BY d.title
        """)
        docs_result = await self.session.execute(docs_sql, {"entity_id": entity_id})
        docs = [dict(r) for r in docs_result.mappings().all()]

        return {
            "id": entity["id"],
            "name": entity["name"],
            "type": entity["type"],
            "description": entity["description"],
            "document_count": len(docs),
            "documents": docs,
        }

    async def get_neighborhood(
        self, entity_id: int, depth: int = 1, limit: int = 50
    ) -> dict:
        """Fetch 1-hop neighborhood: the entity, all directly related entities, relationships, and linked documents."""
        depth = min(depth, 2)
        limit = min(limit, 100)

        rels_sql = text("""
            SELECT id, from_entity_id, to_entity_id, relationship_type, source_document_id
            FROM entity_relationships
            WHERE from_entity_id = :entity_id OR to_entity_id = :entity_id
            LIMIT :limit
        """)
        rels_result = await self.session.execute(
            rels_sql, {"entity_id": entity_id, "limit": limit}
        )
        rels = [dict(r) for r in rels_result.mappings().all()]

        # Collect all entity IDs
        entity_ids = {entity_id}
        for r in rels:
            entity_ids.add(r["from_entity_id"])
            entity_ids.add(r["to_entity_id"])

        if not entity_ids:
            return {"entities": [], "relationships": [], "documents": [], "center_entity_id": entity_id}

        entities_sql = text("""
            SELECT id, name, type FROM entities WHERE id = ANY(:ids)
        """)
        entities_result = await self.session.execute(
            entities_sql, {"ids": list(entity_ids)}
        )
        entities = [dict(r) for r in entities_result.mappings().all()]

        # Only include documents that are direct sources of the displayed relationships
        source_doc_ids = list({r["source_document_id"] for r in rels if r["source_document_id"]})
        documents = []
        if source_doc_ids:
            docs_sql = text("""
                SELECT DISTINCT d.id, d.title
                FROM document d
                WHERE d.id = ANY(:ids)
                ORDER BY d.title
            """)
            docs_result = await self.session.execute(docs_sql, {"ids": source_doc_ids})
            documents = [dict(r) for r in docs_result.mappings().all()]

        return {
            "entities": entities,
            "relationships": rels,
            "documents": documents,
            "center_entity_id": entity_id,
        }

    async def get_relationship(self, relationship_id: int) -> Optional[dict]:
        """Fetch full relationship detail with endpoint entities and source document."""
        sql = text("""
            SELECT r.id, r.relationship_type, r.source_document_id,
                   e1.id AS from_id, e1.name AS from_name, e1.type AS from_type,
                   e2.id AS to_id, e2.name AS to_name, e2.type AS to_type,
                   d.id AS doc_id, d.title AS doc_title
            FROM entity_relationships r
            JOIN entities e1 ON e1.id = r.from_entity_id
            JOIN entities e2 ON e2.id = r.to_entity_id
            LEFT JOIN document d ON d.id = r.source_document_id
            WHERE r.id = :relationship_id
        """)
        result = await self.session.execute(sql, {"relationship_id": relationship_id})
        row = result.mappings().first()
        if not row:
            return None

        resp = {
            "id": row["id"],
            "relationship_type": row["relationship_type"],
            "from_entity": {"id": row["from_id"], "name": row["from_name"], "type": row["from_type"]},
            "to_entity": {"id": row["to_id"], "name": row["to_name"], "type": row["to_type"]},
            "source_document": None,
        }
        if row["doc_id"]:
            resp["source_document"] = {"id": row["doc_id"], "title": row["doc_title"]}
        return resp

    async def get_entity_relationships(
        self,
        entity_id: int,
        direction: str = "both",
        limit: int = 50,
    ) -> list[dict]:
        """List relationships connected to an entity."""
        limit = min(limit, 100)

        if direction == "from":
            where = "r.from_entity_id = :entity_id"
        elif direction == "to":
            where = "r.to_entity_id = :entity_id"
        else:
            where = "(r.from_entity_id = :entity_id OR r.to_entity_id = :entity_id)"

        sql = text(f"""
            SELECT r.id, r.from_entity_id, r.to_entity_id,
                   r.relationship_type, r.source_document_id
            FROM entity_relationships r
            WHERE {where}
            ORDER BY r.relationship_type
            LIMIT :limit
        """)
        result = await self.session.execute(
            sql, {"entity_id": entity_id, "limit": limit}
        )
        return [dict(r) for r in result.mappings().all()]

    async def get_entity_documents(self, entity_id: int, limit: int = 50) -> list[dict]:
        """List documents an entity appears in."""
        sql = text("""
            SELECT d.id, d.title
            FROM document d
            JOIN entity_documents ed ON ed.document_id = d.id
            WHERE ed.entity_id = :entity_id
            ORDER BY d.title
            LIMIT :limit
        """)
        result = await self.session.execute(
            sql, {"entity_id": entity_id, "limit": min(limit, 100)}
        )
        return [dict(r) for r in result.mappings().all()]

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

        # Get entities linked to this document
        entities_sql = text("""
            SELECT e.id, e.name, e.type
            FROM entities e
            JOIN entity_documents ed ON ed.entity_id = e.id
            WHERE ed.document_id = :document_id
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

    async def get_subgraph(self, entity_ids: list[int], include_relationships: bool = True) -> dict:
        """Batch-fetch a subgraph for multiple entity IDs."""
        entities_sql = text("SELECT id, name, type FROM entities WHERE id = ANY(:ids)")
        entities_result = await self.session.execute(entities_sql, {"ids": entity_ids})
        entities = [dict(r) for r in entities_result.mappings().all()]

        rels = []
        if include_relationships and entity_ids:
            rels_sql = text("""
                SELECT id, from_entity_id, to_entity_id, relationship_type, source_document_id
                FROM entity_relationships
                WHERE from_entity_id = ANY(:ids) AND to_entity_id = ANY(:ids)
            """)
            rels_result = await self.session.execute(rels_sql, {"ids": entity_ids})
            rels = [dict(r) for r in rels_result.mappings().all()]

        # Fetch documents linked to these entities
        docs_sql = text("""
            SELECT DISTINCT d.id, d.title
            FROM document d
            JOIN entity_documents ed ON ed.document_id = d.id
            WHERE ed.entity_id = ANY(:ids)
        """)
        docs_result = await self.session.execute(docs_sql, {"ids": entity_ids})
        documents = [dict(r) for r in docs_result.mappings().all()]

        return {"entities": entities, "relationships": rels, "documents": documents, "center_entity_id": None}

    async def get_entity_kg_context(self, entity_ids: list[int]) -> list[dict]:
        """
        For a list of entity IDs, return structured KG context:
        each entity with its relationships and linked document titles.
        """
        if not entity_ids:
            return []

        # Fetch entity details
        entities_sql = text(
            "SELECT id, name, type, description FROM entities WHERE id = ANY(:ids)"
        )
        entities_result = await self.session.execute(entities_sql, {"ids": entity_ids})
        entities = {r["id"]: dict(r) for r in entities_result.mappings().all()}

        # Fetch relationships involving these entities
        rels_sql = text("""
            SELECT r.relationship_type,
                   e1.name AS from_name,
                   e2.name AS to_name
            FROM entity_relationships r
            JOIN entities e1 ON e1.id = r.from_entity_id
            JOIN entities e2 ON e2.id = r.to_entity_id
            WHERE r.from_entity_id = ANY(:ids) OR r.to_entity_id = ANY(:ids)
            LIMIT 50
        """)
        rels_result = await self.session.execute(rels_sql, {"ids": entity_ids})
        all_rels = rels_result.mappings().all()

        # Fetch linked documents
        docs_sql = text("""
            SELECT ed.entity_id, d.title
            FROM entity_documents ed
            JOIN document d ON d.id = ed.document_id
            WHERE ed.entity_id = ANY(:ids)
            ORDER BY ed.entity_id, d.title
            LIMIT 50
        """)
        docs_result = await self.session.execute(docs_sql, {"ids": entity_ids})
        all_docs = docs_result.mappings().all()

        # Group relationships and docs by entity
        result = []
        for eid in entity_ids:
            if eid not in entities:
                continue
            e = entities[eid]
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

    async def get_document_subgraph(self, document_id: int) -> dict:
        """Fetch full subgraph for a document."""
        entities_sql = text("""
            SELECT e.id, e.name, e.type
            FROM entities e
            JOIN entity_documents ed ON ed.entity_id = e.id
            WHERE ed.document_id = :document_id
        """)
        entities_result = await self.session.execute(entities_sql, {"document_id": document_id})
        entities = [dict(r) for r in entities_result.mappings().all()]

        rels_sql = text("""
            SELECT id, from_entity_id, to_entity_id, relationship_type, source_document_id
            FROM entity_relationships
            WHERE source_document_id = :document_id
        """)
        rels_result = await self.session.execute(rels_sql, {"document_id": document_id})
        rels = [dict(r) for r in rels_result.mappings().all()]

        doc_sql = text("SELECT id, title FROM document WHERE id = :document_id")
        doc_result = await self.session.execute(doc_sql, {"document_id": document_id})
        doc_row = doc_result.mappings().first()
        documents = [dict(doc_row)] if doc_row else []

        return {"entities": entities, "relationships": rels, "documents": documents, "center_entity_id": None}
