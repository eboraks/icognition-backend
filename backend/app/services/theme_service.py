"""
Theme clustering service.

Clusters user documents into themes using HDBSCAN on document embeddings,
generates human-readable labels via Gemini, and supports on-ingestion
assignment and user reassignment.
"""

import json
from typing import Optional, List, Dict, Any

import numpy as np
from sklearn.cluster import HDBSCAN
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Embedding
from app.models_kg import Theme, ThemeDocument
from app.services.gemini_service import get_gemini_service, GeminiConfig, GeminiModel
from app.utils.logging import get_logger

logger = get_logger(__name__)

# Minimum documents needed before clustering is attempted
MIN_DOCS_FOR_CLUSTERING = 5

# Cosine similarity threshold for on-ingestion assignment
THEME_ASSIGNMENT_THRESHOLD = 0.75

# When merging with existing themes during re-cluster, threshold for "same theme"
THEME_MERGE_THRESHOLD = 0.90

# HDBSCAN parameters
HDBSCAN_MIN_CLUSTER_SIZE = 3

# Color palette for auto-assigning theme colors
THEME_COLORS = [
    "#4F46E5",  # indigo
    "#059669",  # emerald
    "#DC2626",  # red
    "#0891B2",  # cyan
    "#EA580C",  # orange
    "#7C3AED",  # violet
    "#E11D48",  # rose
    "#0284C7",  # sky
    "#CA8A04",  # yellow
    "#C026D3",  # fuchsia
    "#16A34A",  # green
    "#6366F1",  # indigo-light
]


class ThemeService:
    def __init__(self, session: AsyncSession):
        self.session = session

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    async def get_themes(self, user_id: str) -> List[Dict[str, Any]]:
        """Return all active themes for a user."""
        sql = text("""
            SELECT id, label, description, doc_count, color
            FROM theme
            WHERE user_id = :user_id AND is_active = true
            ORDER BY doc_count DESC
        """)
        result = await self.session.execute(sql, {"user_id": user_id})
        return [dict(r) for r in result.mappings().all()]

    async def get_theme_documents(
        self, theme_id: int, user_id: str, limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Return documents belonging to a theme."""
        sql = text("""
            SELECT d.id, d.title
            FROM document d
            JOIN theme_document td ON td.document_id = d.id
            WHERE td.theme_id = :theme_id AND d.user_id = :user_id
            ORDER BY d.created_at DESC
            LIMIT :limit
        """)
        result = await self.session.execute(
            sql, {"theme_id": theme_id, "user_id": user_id, "limit": limit}
        )
        return [dict(r) for r in result.mappings().all()]

    # ------------------------------------------------------------------
    # Batch re-clustering
    # ------------------------------------------------------------------

    async def recluster_themes(self, user_id: str) -> Dict[str, Any]:
        """
        Full re-clustering for a user. Hybrid approach:

        1. Fetch averaged content-chunk embeddings per document
        2. Run HDBSCAN to identify candidate clusters
        3. Fetch ai_markdown_content summaries for each cluster
        4. LLM judge: evaluate, merge/discard, and name real themes
        5. Persist refined themes and assignments
        """
        # Step 1: Fetch document content embeddings (averaged across chunks)
        doc_embeddings = await self._fetch_document_content_embeddings(user_id)
        if len(doc_embeddings) < MIN_DOCS_FOR_CLUSTERING:
            logger.info(
                f"User {user_id} has {len(doc_embeddings)} docs, "
                f"need {MIN_DOCS_FOR_CLUSTERING} for clustering"
            )
            return {"themes_created": 0, "themes_updated": 0, "documents_assigned": 0}

        # Wipe all existing themes and assignments for a fresh start
        # (preserve manual assignments in memory, re-apply after)
        await self.session.execute(
            text("""
                DELETE FROM theme_document td
                USING theme t
                WHERE td.theme_id = t.id AND t.user_id = :user_id
            """),
            {"user_id": user_id},
        )
        await self.session.execute(
            text("DELETE FROM theme WHERE user_id = :user_id"),
            {"user_id": user_id},
        )

        doc_ids = [d["doc_id"] for d in doc_embeddings]
        vectors = np.array([d["vector"] for d in doc_embeddings])

        # Step 2: Run HDBSCAN on content embeddings
        clusterer = HDBSCAN(
            min_cluster_size=HDBSCAN_MIN_CLUSTER_SIZE,
            metric="cosine",
        )
        labels = clusterer.fit_predict(vectors)
        unique_labels = set(labels)
        unique_labels.discard(-1)

        logger.info(
            f"HDBSCAN found {len(unique_labels)} candidate clusters for user {user_id} "
            f"({sum(labels == -1)} noise documents)"
        )

        # Step 3: Build candidate clusters with document summaries
        candidates = []
        for cluster_id in sorted(unique_labels):
            mask = labels == cluster_id
            cluster_doc_ids = [doc_ids[i] for i in range(len(doc_ids)) if mask[i]]
            cluster_vectors = vectors[mask]
            centroid = np.mean(cluster_vectors, axis=0).tolist()

            # Fetch ai_markdown_content summaries for LLM judge
            summaries = await self._fetch_document_summaries(cluster_doc_ids)
            candidates.append({
                "cluster_id": cluster_id,
                "doc_ids": cluster_doc_ids,
                "centroid": centroid,
                "summaries": summaries,
            })

        # Step 4: LLM judge — evaluate, merge, name
        refined_themes = await self._judge_and_name_clusters(candidates)

        logger.info(
            f"LLM judge refined {len(candidates)} candidates into "
            f"{len(refined_themes)} themes for user {user_id}"
        )

        # Step 5: Persist fresh themes
        manual_assignments = await self._get_manual_assignments(user_id)

        themes_created = 0
        documents_assigned = 0
        color_idx = 0

        for theme_data in refined_themes:
            label = theme_data["label"]
            description = theme_data.get("description", "")
            member_doc_ids = theme_data["doc_ids"]

            # Compute centroid from member document vectors
            member_indices = [
                i for i, did in enumerate(doc_ids) if did in set(member_doc_ids)
            ]
            if not member_indices:
                continue
            centroid = np.mean(vectors[member_indices], axis=0).tolist()

            color = THEME_COLORS[color_idx % len(THEME_COLORS)]
            color_idx += 1
            theme_id = await self._create_theme(
                user_id, label, description, centroid, len(member_doc_ids), color
            )
            themes_created += 1

            for doc_id in member_doc_ids:
                if doc_id in manual_assignments:
                    continue
                await self._upsert_theme_document(theme_id, doc_id, is_manual=False)
                documents_assigned += 1

        # Handle noise documents → "Uncategorized"
        assigned_doc_ids = set()
        for theme_data in refined_themes:
            assigned_doc_ids.update(theme_data["doc_ids"])

        noise_doc_ids = [d for d in doc_ids if d not in assigned_doc_ids]
        noise_doc_ids = [d for d in noise_doc_ids if d not in manual_assignments]
        if noise_doc_ids:
            uncat_id = await self._get_or_create_uncategorized_theme(user_id)
            for doc_id in noise_doc_ids:
                await self._upsert_theme_document(uncat_id, doc_id, is_manual=False)
                documents_assigned += 1
            await self._update_theme_doc_count(uncat_id)

        await self._deactivate_empty_themes(user_id)
        await self.session.commit()

        return {
            "themes_created": themes_created,
            "themes_updated": 0,
            "documents_assigned": documents_assigned,
        }

    # ------------------------------------------------------------------
    # On-ingestion assignment
    # ------------------------------------------------------------------

    async def assign_document_to_theme(
        self, document_id: int, user_id: str
    ) -> Optional[int]:
        """
        Assign a newly ingested document to the most similar theme.
        Returns the theme_id assigned, or None if no themes exist yet.
        """
        # Get the document's content embedding (averaged across chunks)
        doc_vector = await self._get_document_content_vector(document_id, user_id)
        if doc_vector is None:
            logger.warning(f"No title embedding found for document {document_id}")
            return None

        # Find best matching theme by centroid similarity
        best_theme_id, best_similarity = await self._find_closest_theme(
            doc_vector, user_id
        )

        if best_theme_id is None:
            return None

        if best_similarity >= THEME_ASSIGNMENT_THRESHOLD:
            theme_id = best_theme_id
        else:
            # Below threshold → uncategorized
            theme_id = await self._get_or_create_uncategorized_theme(user_id)

        await self._upsert_theme_document(theme_id, document_id, is_manual=False)
        await self._update_centroid_incremental(theme_id, doc_vector)
        await self._update_theme_doc_count(theme_id)
        await self.session.commit()

        logger.info(
            f"Assigned document {document_id} to theme {theme_id} "
            f"(similarity={best_similarity:.3f})"
        )
        return theme_id

    # ------------------------------------------------------------------
    # User reassignment
    # ------------------------------------------------------------------

    async def reassign_document(
        self,
        document_id: int,
        from_theme_id: int,
        to_theme_id: int,
        user_id: str,
    ) -> bool:
        """Move a document between themes. Sets is_manual=True."""
        # Verify both themes belong to user
        verify_sql = text("""
            SELECT id FROM theme
            WHERE id IN (:from_id, :to_id) AND user_id = :user_id
        """)
        result = await self.session.execute(
            verify_sql,
            {"from_id": from_theme_id, "to_id": to_theme_id, "user_id": user_id},
        )
        if len(result.all()) < 2:
            return False

        # Remove from old theme
        delete_sql = text("""
            DELETE FROM theme_document
            WHERE theme_id = :theme_id AND document_id = :doc_id
        """)
        await self.session.execute(
            delete_sql, {"theme_id": from_theme_id, "doc_id": document_id}
        )

        # Add to new theme with manual flag
        await self._upsert_theme_document(to_theme_id, document_id, is_manual=True)

        # Update counts for both themes
        await self._update_theme_doc_count(from_theme_id)
        await self._update_theme_doc_count(to_theme_id)

        # Recompute centroids
        await self._recompute_centroid(from_theme_id)
        await self._recompute_centroid(to_theme_id)

        await self.session.commit()
        return True

    # ------------------------------------------------------------------
    # Theme CRUD
    # ------------------------------------------------------------------

    async def update_theme(
        self, theme_id: int, user_id: str, label: Optional[str] = None, color: Optional[str] = None
    ) -> bool:
        """Rename or recolor a theme."""
        updates = []
        params: Dict[str, Any] = {"theme_id": theme_id, "user_id": user_id}
        if label is not None:
            updates.append("label = :label")
            params["label"] = label
        if color is not None:
            updates.append("color = :color")
            params["color"] = color
        if not updates:
            return False

        sql = text(f"""
            UPDATE theme SET {', '.join(updates)}, updated_at = now()
            WHERE id = :theme_id AND user_id = :user_id
        """)
        result = await self.session.execute(sql, params)
        await self.session.commit()
        return result.rowcount > 0

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _fetch_document_content_embeddings(
        self, user_id: str
    ) -> List[Dict[str, Any]]:
        """
        Fetch averaged content-chunk embeddings per document.
        Averages all content_chunk_* vectors into a single document vector.
        Falls back to title embedding if no content chunks exist.
        """
        sql = text("""
            SELECT e.source_id AS doc_id,
                   AVG(e.vector)::text AS avg_vector_text
            FROM embedding e
            JOIN document d ON d.id = e.source_id
            WHERE e.source_type = 'document'
              AND e.user_id = :user_id
              AND d.user_id = :user_id
              AND (e.field LIKE 'content_chunk%%' OR e.field = 'title')
            GROUP BY e.source_id
        """)
        result = await self.session.execute(sql, {"user_id": user_id})
        rows = []
        for r in result.mappings().all():
            vector = self._parse_pg_vector(r["avg_vector_text"])
            if vector is not None:
                rows.append({"doc_id": r["doc_id"], "vector": vector})
        return rows

    async def _fetch_document_summaries(
        self, doc_ids: List[int]
    ) -> List[Dict[str, Any]]:
        """Fetch ai_markdown_content summaries for a list of documents."""
        sql = text("""
            SELECT id, title, LEFT(ai_markdown_content, 250) AS summary
            FROM document
            WHERE id = ANY(:ids)
        """)
        result = await self.session.execute(sql, {"ids": doc_ids})
        return [dict(r) for r in result.mappings().all()]

    async def _judge_and_name_clusters(
        self, candidates: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        LLM judge: evaluate candidate clusters from HDBSCAN and produce
        refined themes with proper names.

        Input: list of {cluster_id, doc_ids, centroid, summaries}
        Output: list of {label, description, doc_ids}
        """
        if not candidates:
            return []

        gemini = get_gemini_service()

        # Build the prompt with all candidate clusters
        cluster_descriptions = []
        for i, c in enumerate(candidates):
            docs_text = "\n".join(
                f"    - [{s['id']}] {s['title']}: {s.get('summary', 'N/A')[:150]}"
                for s in c["summaries"][:8]  # max 8 docs per cluster for context
            )
            cluster_descriptions.append(
                f"Cluster {i} ({len(c['doc_ids'])} documents):\n{docs_text}"
            )

        clusters_text = "\n\n".join(cluster_descriptions)

        prompt = f"""You are analyzing document clusters from a user's knowledge base to identify meaningful themes.

Below are {len(candidates)} candidate clusters produced by an algorithm. Each cluster contains document titles and content summaries.

Your job:
1. EVALUATE each cluster: Is this a meaningful topical theme (e.g., "Iran Conflict", "AI Development", "US Economy")? Or is it just noise grouped by surface similarity (same website, same author, similar formatting)?
2. DISCARD clusters that are not real themes (e.g., clusters of "Home / X" pages, or clusters formed by URL patterns rather than content).
3. MERGE clusters that cover the same underlying topic.
4. NAME each surviving theme with a concise 2-4 word topical label. The label should describe the TOPIC, not the source or author.
5. Write a one-sentence description for each theme.

Candidate clusters:
{clusters_text}

Return a JSON array of refined themes. Each theme should have:
- "label": 2-4 word topical theme name
- "description": one-sentence description
- "source_clusters": list of cluster indices (from above) that belong to this theme

Return ONLY valid JSON array. Example:
[
  {{"label": "Iran Conflict", "description": "Coverage of the US-Iran military conflict and regional geopolitics.", "source_clusters": [0, 3]}},
  {{"label": "AI Industry", "description": "Developments in artificial intelligence companies and technology.", "source_clusters": [1]}}
]

If NO clusters represent real themes, return an empty array: []"""

        config = GeminiConfig(
            temperature=0.3,
            max_output_tokens=2048,
            response_mime_type="application/json",
        )

        try:
            result = await gemini.generate_content(
                prompt=prompt,
                model=GeminiModel.FLASH,
                config=config,
            )
            content = result["content"].strip()
            refined = self._parse_json_response(content)

            # If it's a dict with a key, extract the array
            if isinstance(refined, dict):
                refined = refined.get("themes", refined.get("results", []))

            if not isinstance(refined, list):
                logger.warning(f"LLM judge returned non-list: {type(refined)}")
                return self._fallback_naming(candidates)

            # Map source_clusters back to doc_ids
            themes = []
            for theme_data in refined:
                source_indices = theme_data.get("source_clusters", [])
                merged_doc_ids = []
                for idx in source_indices:
                    if 0 <= idx < len(candidates):
                        merged_doc_ids.extend(candidates[idx]["doc_ids"])
                if merged_doc_ids:
                    themes.append({
                        "label": str(theme_data.get("label", "Unknown"))[:255],
                        "description": str(theme_data.get("description", "")),
                        "doc_ids": merged_doc_ids,
                    })

            return themes

        except Exception as e:
            logger.error(f"LLM judge failed: {e}. Falling back to basic naming.")
            return self._fallback_naming(candidates)

    def _fallback_naming(
        self, candidates: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Fallback if LLM judge fails: use titles from summaries."""
        themes = []
        for c in candidates:
            titles = [s["title"] for s in c["summaries"][:5]]
            # Use shortest meaningful title as a rough label
            label = min(titles, key=len) if titles else "Theme"
            label = label[:255]
            themes.append({
                "label": label,
                "description": "",
                "doc_ids": c["doc_ids"],
            })
        return themes

    async def _get_document_content_vector(
        self, document_id: int, user_id: str
    ) -> Optional[List[float]]:
        """Get averaged content embedding vector for a specific document."""
        sql = text("""
            SELECT AVG(e.vector)::text AS avg_vector_text
            FROM embedding e
            WHERE e.source_type = 'document'
              AND e.source_id = :doc_id
              AND e.user_id = :user_id
              AND (e.field LIKE 'content_chunk%%' OR e.field = 'title')
        """)
        result = await self.session.execute(
            sql, {"doc_id": document_id, "user_id": user_id}
        )
        row = result.mappings().first()
        if row is None or row["avg_vector_text"] is None:
            return None
        return self._parse_pg_vector(row["avg_vector_text"])

    async def _find_closest_theme(
        self, vector: List[float], user_id: str
    ) -> tuple[Optional[int], float]:
        """Find the theme whose centroid is most similar to the given vector."""
        sql = text("""
            SELECT id, 1 - (centroid <=> CAST(:vec AS vector)) AS similarity
            FROM theme
            WHERE user_id = :user_id AND is_active = true AND centroid IS NOT NULL
            ORDER BY centroid <=> CAST(:vec AS vector)
            LIMIT 1
        """)
        result = await self.session.execute(
            sql, {"vec": str(vector), "user_id": user_id}
        )
        row = result.mappings().first()
        if row is None:
            return None, 0.0
        return row["id"], float(row["similarity"])

    async def _get_themes_with_centroids(self, user_id: str) -> List[Dict[str, Any]]:
        """Fetch active themes with their centroid vectors."""
        sql = text("""
            SELECT id, label, centroid::text AS centroid_text
            FROM theme
            WHERE user_id = :user_id AND is_active = true AND centroid IS NOT NULL
        """)
        result = await self.session.execute(sql, {"user_id": user_id})
        themes = []
        for r in result.mappings().all():
            centroid = self._parse_pg_vector(r["centroid_text"])
            if centroid is not None:
                themes.append({"id": r["id"], "label": r["label"], "centroid": centroid})
        return themes

    def _find_matching_theme(
        self, centroid: List[float], existing_themes: List[Dict[str, Any]]
    ) -> Optional[int]:
        """Check if a centroid matches an existing theme above the merge threshold."""
        if not existing_themes:
            return None
        centroid_arr = np.array(centroid)
        best_id = None
        best_sim = 0.0
        for theme in existing_themes:
            theme_arr = np.array(theme["centroid"])
            # Cosine similarity
            dot = np.dot(centroid_arr, theme_arr)
            norm = np.linalg.norm(centroid_arr) * np.linalg.norm(theme_arr)
            sim = dot / norm if norm > 0 else 0.0
            if sim > best_sim:
                best_sim = sim
                best_id = theme["id"]
        if best_sim >= THEME_MERGE_THRESHOLD:
            return best_id
        return None

    async def _get_manual_assignments(self, user_id: str) -> set:
        """Get document IDs that have been manually assigned by the user."""
        sql = text("""
            SELECT td.document_id
            FROM theme_document td
            JOIN theme t ON t.id = td.theme_id
            WHERE t.user_id = :user_id AND td.is_manual = true
        """)
        result = await self.session.execute(sql, {"user_id": user_id})
        return {r["document_id"] for r in result.mappings().all()}

    async def _create_theme(
        self,
        user_id: str,
        label: str,
        description: Optional[str],
        centroid: List[float],
        doc_count: int,
        color: str,
    ) -> int:
        """Create a new theme and return its id."""
        sql = text("""
            INSERT INTO theme (user_id, label, description, centroid, doc_count, color, is_active)
            VALUES (:user_id, :label, :description, CAST(:centroid AS vector), :doc_count, :color, true)
            ON CONFLICT (user_id, label) DO UPDATE
              SET description = EXCLUDED.description,
                  centroid = EXCLUDED.centroid,
                  doc_count = EXCLUDED.doc_count,
                  color = EXCLUDED.color,
                  is_active = true,
                  updated_at = now()
            RETURNING id
        """)
        result = await self.session.execute(sql, {
            "user_id": user_id,
            "label": label,
            "description": description,
            "centroid": str(centroid),
            "doc_count": doc_count,
            "color": color,
        })
        return result.scalar_one()

    async def _upsert_theme_document(
        self, theme_id: int, document_id: int, is_manual: bool
    ) -> None:
        """Insert or update a theme-document link."""
        sql = text("""
            INSERT INTO theme_document (theme_id, document_id, is_manual)
            VALUES (:theme_id, :doc_id, :is_manual)
            ON CONFLICT (theme_id, document_id) DO UPDATE
              SET is_manual = EXCLUDED.is_manual
        """)
        await self.session.execute(
            sql, {"theme_id": theme_id, "doc_id": document_id, "is_manual": is_manual}
        )

    async def _update_theme_doc_count(self, theme_id: int) -> None:
        """Recount documents for a theme."""
        sql = text("""
            UPDATE theme SET doc_count = (
                SELECT COUNT(*) FROM theme_document WHERE theme_id = :theme_id
            ), updated_at = now()
            WHERE id = :theme_id
        """)
        await self.session.execute(sql, {"theme_id": theme_id})

    async def _update_theme_centroid_and_count(
        self, theme_id: int, centroid: List[float], doc_count: int
    ) -> None:
        """Update centroid and doc_count for an existing theme."""
        sql = text("""
            UPDATE theme
            SET centroid = CAST(:centroid AS vector),
                doc_count = :doc_count,
                updated_at = now()
            WHERE id = :theme_id
        """)
        await self.session.execute(sql, {
            "theme_id": theme_id,
            "centroid": str(centroid),
            "doc_count": doc_count,
        })

    async def _update_centroid_incremental(
        self, theme_id: int, new_vector: List[float]
    ) -> None:
        """Incrementally update a theme centroid with a new document vector."""
        # Fetch current centroid and count
        sql = text("""
            SELECT centroid::text AS centroid_text, doc_count
            FROM theme WHERE id = :theme_id
        """)
        result = await self.session.execute(sql, {"theme_id": theme_id})
        row = result.mappings().first()
        if row is None:
            return

        old_centroid = self._parse_pg_vector(row["centroid_text"])
        n = row["doc_count"]

        if old_centroid is None or n == 0:
            new_centroid = new_vector
        else:
            old_arr = np.array(old_centroid)
            new_arr = np.array(new_vector)
            new_centroid = ((old_arr * n + new_arr) / (n + 1)).tolist()

        update_sql = text("""
            UPDATE theme SET centroid = CAST(:centroid AS vector), updated_at = now()
            WHERE id = :theme_id
        """)
        await self.session.execute(update_sql, {
            "centroid": str(new_centroid),
            "theme_id": theme_id,
        })

    async def _recompute_centroid(self, theme_id: int) -> None:
        """Recompute centroid from scratch using all member document embeddings."""
        sql = text("""
            SELECT e.vector::text AS vector_text
            FROM embedding e
            JOIN theme_document td ON td.document_id = e.source_id
            WHERE td.theme_id = :theme_id
              AND e.source_type = 'document'
              AND e.field = 'title'
        """)
        result = await self.session.execute(sql, {"theme_id": theme_id})
        vectors = []
        for r in result.mappings().all():
            v = self._parse_pg_vector(r["vector_text"])
            if v is not None:
                vectors.append(v)

        if vectors:
            centroid = np.mean(np.array(vectors), axis=0).tolist()
            update_sql = text("""
                UPDATE theme SET centroid = CAST(:centroid AS vector), updated_at = now()
                WHERE id = :theme_id
            """)
            await self.session.execute(update_sql, {
                "centroid": str(centroid),
                "theme_id": theme_id,
            })

    async def _get_or_create_uncategorized_theme(self, user_id: str) -> int:
        """Get or create the 'Uncategorized' theme for a user."""
        sql = text("""
            SELECT id FROM theme
            WHERE user_id = :user_id AND label = 'Uncategorized'
        """)
        result = await self.session.execute(sql, {"user_id": user_id})
        row = result.scalars().first()
        if row is not None:
            # Reactivate if needed
            await self.session.execute(
                text("UPDATE theme SET is_active = true WHERE id = :id"),
                {"id": row},
            )
            return row

        insert_sql = text("""
            INSERT INTO theme (user_id, label, description, doc_count, color, is_active)
            VALUES (:user_id, 'Uncategorized', 'Documents that do not fit a specific theme', 0, '#6B7280', true)
            RETURNING id
        """)
        result = await self.session.execute(insert_sql, {"user_id": user_id})
        return result.scalar_one()

    async def _deactivate_empty_themes(self, user_id: str) -> None:
        """Deactivate themes with zero documents (except Uncategorized)."""
        sql = text("""
            UPDATE theme SET is_active = false, updated_at = now()
            WHERE user_id = :user_id
              AND label != 'Uncategorized'
              AND id NOT IN (SELECT DISTINCT theme_id FROM theme_document)
        """)
        await self.session.execute(sql, {"user_id": user_id})

    async def _generate_theme_label(
        self, document_titles: List[str]
    ) -> tuple[str, str]:
        """Generate a theme label and description from document titles using Gemini."""
        gemini = get_gemini_service()
        sample_titles = document_titles[:10]
        titles_text = "\n".join(f"- {t}" for t in sample_titles)

        prompt = f"""Given these document titles from a user's knowledge base, generate a concise theme label and description.

Document titles:
{titles_text}

Return a JSON object with exactly these fields:
- "label": A concise 2-4 word theme label (e.g., "AI Development", "US Economy", "Climate Policy")
- "description": A one-sentence description of what this theme covers

Return only valid JSON, no other text."""

        config = GeminiConfig(
            temperature=0.3,
            max_output_tokens=256,
            response_mime_type="application/json",
        )

        try:
            result = await gemini.generate_content(
                prompt=prompt,
                model=GeminiModel.FLASH,
                config=config,
            )
            content = result["content"].strip()
            data = self._parse_json_response(content)
            label = str(data.get("label", "Unknown Theme"))[:255]
            description = str(data.get("description", ""))
            return label, description
        except Exception as e:
            logger.error(f"Failed to generate theme label: {e}")
            # Fallback: use first title words
            fallback = " ".join(sample_titles[0].split()[:3]) if sample_titles else "Theme"
            return fallback, ""

    @staticmethod
    def _parse_json_response(content: str) -> dict:
        """Parse JSON from Gemini response, handling markdown code fences."""
        # Try direct parse first
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass

        # Strip markdown code fences (```json ... ``` or ``` ... ```)
        import re
        match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", content, re.DOTALL)
        if match:
            return json.loads(match.group(1).strip())

        # Try to find first { ... } block
        start = content.find("{")
        end = content.rfind("}")
        if start != -1 and end != -1 and end > start:
            return json.loads(content[start : end + 1])

        raise json.JSONDecodeError("No valid JSON found in response", content, 0)

    @staticmethod
    def _parse_pg_vector(vector_text: Optional[str]) -> Optional[List[float]]:
        """Parse a PostgreSQL vector string like '[0.1,0.2,...]' into a list of floats."""
        if vector_text is None:
            return None
        try:
            cleaned = vector_text.strip("[]")
            return [float(x) for x in cleaned.split(",")]
        except (ValueError, AttributeError):
            return None


# ------------------------------------------------------------------
# Singleton accessor
# ------------------------------------------------------------------

_theme_service: Optional[ThemeService] = None


def get_theme_service(session: AsyncSession) -> ThemeService:
    """Get a ThemeService instance for the given session."""
    return ThemeService(session)
