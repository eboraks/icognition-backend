"""
Backfill research-saved documents that never finished post-processing.

Research sub-agents save documents and fire a background task that runs:
  1. DSPy content analysis  (populates ai_markdown_content + extracted_content)
  2. Embedding generation    (populates embedding rows)
  3. KG extraction           (populates kg_node / kg_edge / kg_node_document)

Historically this task could fail mid-flight — notably because of the
kg_node unique-constraint race between parallel sub-agents. When it failed,
the document ended up "orphaned": visible in the research graph but with no
AI content in the Details panel and/or no edges in the graph.

This script finds every document with research_session_id set that is missing
any of those three outputs and re-runs the corresponding step(s).

Usage:
  cd backend && .venv/bin/python scripts/backfill_research_documents.py
  cd backend && .venv/bin/python scripts/backfill_research_documents.py --execute
  cd backend && .venv/bin/python scripts/backfill_research_documents.py --execute --user-id <uid>
  cd backend && .venv/bin/python scripts/backfill_research_documents.py --execute --doc-id 123
"""

import argparse
import asyncio
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select, text

from app.db.database import async_session
from app.models import Document
from app.services.dspy_content_service import get_dspy_content_service
from app.services.embedding_service import get_embedding_service
from app.services.kg_pipeline import process_document_kg_background
from app.utils.logging import get_logger

logger = get_logger(__name__)


FIND_CANDIDATES_SQL = text("""
    SELECT
        d.id,
        d.user_id,
        d.title,
        (d.ai_markdown_content IS NULL OR TRIM(d.ai_markdown_content) = '') AS needs_dspy,
        NOT EXISTS (
            SELECT 1 FROM embedding e
            WHERE e.source_type = 'document' AND e.source_id = d.id
        ) AS needs_embeddings,
        NOT EXISTS (
            SELECT 1 FROM kg_node_document knd WHERE knd.document_id = d.id
        ) AS needs_kg
    FROM document d
    WHERE d.research_session_id IS NOT NULL
      AND d.content IS NOT NULL
      AND TRIM(d.content) <> ''
      AND (CAST(:doc_id AS INTEGER) IS NULL OR d.id = CAST(:doc_id AS INTEGER))
      AND (CAST(:user_id AS TEXT) IS NULL OR d.user_id = CAST(:user_id AS TEXT))
    ORDER BY d.id
""")


async def find_candidates(doc_id: int | None, user_id: str | None) -> list[dict]:
    async with async_session() as sess:
        result = await sess.execute(
            FIND_CANDIDATES_SQL,
            {"doc_id": doc_id, "user_id": user_id},
        )
        rows = result.mappings().all()
    return [
        dict(r) for r in rows
        if r["needs_dspy"] or r["needs_embeddings"] or r["needs_kg"]
    ]


async def run_dspy(doc_id: int) -> bool:
    async with async_session() as sess:
        doc = (await sess.execute(
            select(Document).where(Document.id == doc_id)
        )).scalar_one_or_none()
        if doc is None or not doc.content or not doc.content.strip():
            return False
        try:
            dspy_svc = get_dspy_content_service()
            analysis = await dspy_svc.analyze_document_content(
                content=doc.content, title=doc.title, url=doc.url,
            )
            doc.ai_is_about = analysis["summary"]
            doc.ai_markdown_content = analysis.get("markdown_content", "")
            doc.extracted_content = analysis["extracted_content"]
            doc.source_type = analysis["extracted_content"]["source_type"]
            doc.updated_at = datetime.now()
            await sess.commit()
            return True
        except Exception as e:
            logger.error(f"DSPy backfill failed for doc {doc_id}: {e}")
            await sess.rollback()
            return False


async def run_embeddings(doc_id: int, user_id: str) -> bool:
    async with async_session() as sess:
        doc = (await sess.execute(
            select(Document).where(Document.id == doc_id)
        )).scalar_one_or_none()
        if doc is None:
            return False
        try:
            emb_svc = get_embedding_service()
            await emb_svc.generate_and_store_document_embeddings(
                session=sess, document=doc, user_id=user_id,
            )
            await sess.commit()
            return True
        except Exception as e:
            logger.error(f"Embedding backfill failed for doc {doc_id}: {e}")
            await sess.rollback()
            return False


async def run_kg(doc_id: int, user_id: str) -> bool:
    try:
        await process_document_kg_background(doc_id, user_id)
        return True
    except Exception as e:
        logger.error(f"KG backfill failed for doc {doc_id}: {e}")
        return False


async def backfill_one(candidate: dict, execute: bool) -> dict:
    doc_id = candidate["id"]
    user_id = candidate["user_id"]
    title = (candidate["title"] or "")[:60]
    steps_needed = [
        s for s, flag in (
            ("dspy", candidate["needs_dspy"]),
            ("embeddings", candidate["needs_embeddings"]),
            ("kg", candidate["needs_kg"]),
        ) if flag
    ]
    print(f"  doc={doc_id} user={user_id} title='{title}' → {','.join(steps_needed)}")

    if not execute:
        return {"doc_id": doc_id, "executed": False, "steps": steps_needed}

    outcomes = {}
    if candidate["needs_dspy"]:
        outcomes["dspy"] = await run_dspy(doc_id)
    if candidate["needs_embeddings"]:
        outcomes["embeddings"] = await run_embeddings(doc_id, user_id)
    if candidate["needs_kg"]:
        outcomes["kg"] = await run_kg(doc_id, user_id)
    print(f"    result: {outcomes}")
    return {"doc_id": doc_id, "executed": True, "outcomes": outcomes}


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true",
                        help="Actually run the backfill (default is dry-run).")
    parser.add_argument("--user-id", type=str, default=None,
                        help="Limit to a single user_id.")
    parser.add_argument("--doc-id", type=int, default=None,
                        help="Backfill a single document id.")
    args = parser.parse_args()

    print(f"Mode: {'EXECUTE' if args.execute else 'DRY-RUN'}")
    if args.user_id:
        print(f"Filter: user_id={args.user_id}")
    if args.doc_id:
        print(f"Filter: doc_id={args.doc_id}")

    candidates = await find_candidates(args.doc_id, args.user_id)
    print(f"Found {len(candidates)} research documents needing backfill:\n")

    if not candidates:
        return

    counts = {"dspy": 0, "embeddings": 0, "kg": 0}
    for c in candidates:
        if c["needs_dspy"]:
            counts["dspy"] += 1
        if c["needs_embeddings"]:
            counts["embeddings"] += 1
        if c["needs_kg"]:
            counts["kg"] += 1
    print(f"Pending steps across candidates: {counts}\n")

    results = []
    for c in candidates:
        results.append(await backfill_one(c, args.execute))

    if args.execute:
        ok = sum(1 for r in results if all(r.get("outcomes", {}).values()))
        print(f"\nCompleted: {ok}/{len(results)} documents fully backfilled.")
    else:
        print("\nDry-run complete. Re-run with --execute to apply.")


if __name__ == "__main__":
    asyncio.run(main())
