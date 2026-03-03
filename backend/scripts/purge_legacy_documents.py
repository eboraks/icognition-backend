"""
Purge documents without ai_markdown_content.

Documents missing ai_markdown_content were analyzed by the old pre-DSPy pipeline
and are no longer useful. This script deletes them along with all dependent rows.

Deletion order (respects FK constraints):
  entity_relationships → entity_documents → document_entity_link
  → embeddings → question_answer → study_collection_document_link
  → bookmarks → document

Usage:
  # Dry-run (default) — prints counts only:
  cd backend && .venv/bin/python scripts/purge_legacy_documents.py

  # Execute deletions:
  cd backend && .venv/bin/python scripts/purge_legacy_documents.py --execute
"""

import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from app.db.database import get_database_url
from sqlalchemy.ext.asyncio import create_async_engine, AsyncConnection


FIND_LEGACY_IDS = text("""
    SELECT id FROM document
    WHERE ai_markdown_content IS NULL OR TRIM(ai_markdown_content) = ''
""")

COUNT_LEGACY = text("""
    SELECT COUNT(*) FROM document
    WHERE ai_markdown_content IS NULL OR TRIM(ai_markdown_content) = ''
""")

# Count dependent rows for reporting
COUNT_QUERIES = {
    "entity_relationships": text("""
        SELECT COUNT(*) FROM entity_relationships
        WHERE source_document_id = ANY(:ids)
    """),
    "entity_documents": text("""
        SELECT COUNT(*) FROM entity_documents
        WHERE document_id = ANY(:ids)
    """),
    "document_entity_link": text("""
        SELECT COUNT(*) FROM document_entity_link
        WHERE document_id = ANY(:ids)
    """),
    "embeddings": text("""
        SELECT COUNT(*) FROM embedding
        WHERE source_type = 'document' AND source_id = ANY(:ids)
    """),
    "question_answer": text("""
        SELECT COUNT(*) FROM question_answer
        WHERE document_id = ANY(:ids)
    """),
    "study_collection_document_link": text("""
        SELECT COUNT(*) FROM study_collection_document_link
        WHERE document_id = ANY(:ids)
    """),
    "bookmarks": text("""
        SELECT COUNT(*) FROM bookmarks
        WHERE document_id = ANY(:ids)
    """),
}

# Delete statements — order matters (child rows first)
DELETE_QUERIES = [
    ("entity_relationships", text("""
        DELETE FROM entity_relationships
        WHERE source_document_id = ANY(:ids)
    """)),
    ("entity_documents", text("""
        DELETE FROM entity_documents
        WHERE document_id = ANY(:ids)
    """)),
    ("document_entity_link", text("""
        DELETE FROM document_entity_link
        WHERE document_id = ANY(:ids)
    """)),
    ("embeddings", text("""
        DELETE FROM embedding
        WHERE source_type = 'document' AND source_id = ANY(:ids)
    """)),
    ("question_answer", text("""
        DELETE FROM question_answer
        WHERE document_id = ANY(:ids)
    """)),
    ("study_collection_document_link", text("""
        DELETE FROM study_collection_document_link
        WHERE document_id = ANY(:ids)
    """)),
    ("bookmarks", text("""
        DELETE FROM bookmarks
        WHERE document_id = ANY(:ids)
    """)),
    ("document", text("""
        DELETE FROM document
        WHERE id = ANY(:ids)
    """)),
]


async def run(execute: bool):
    engine = create_async_engine(get_database_url())

    async with engine.connect() as conn:
        # Find legacy document IDs
        result = await conn.execute(FIND_LEGACY_IDS)
        legacy_ids = [row[0] for row in result]

        if not legacy_ids:
            print("No legacy documents found (all documents have ai_markdown_content). Nothing to do.")
            await engine.dispose()
            return

        count_result = await conn.execute(COUNT_LEGACY)
        doc_count = count_result.scalar()

        print(f"\nFound {doc_count} legacy document(s) without ai_markdown_content.")
        print(f"IDs: {legacy_ids[:20]}{'...' if len(legacy_ids) > 20 else ''}\n")

        # Count dependent rows
        print("Dependent rows that will be deleted:")
        ids_param = {"ids": legacy_ids}
        for table, query in COUNT_QUERIES.items():
            try:
                r = await conn.execute(query, ids_param)
                n = r.scalar()
                print(f"  {table}: {n}")
            except Exception as e:
                print(f"  {table}: error counting — {e}")

        if not execute:
            print("\n[DRY RUN] No changes made.")
            print("Run with --execute to perform the deletions.")
            await engine.dispose()
            return

        # Execute deletions
        print("\nExecuting deletions...")
        try:
            for table, query in DELETE_QUERIES:
                r = await conn.execute(query, ids_param)
                print(f"  Deleted {r.rowcount} rows from {table}")
            await conn.commit()
        except Exception as e:
            await conn.rollback()
            print(f"  ERROR: {e}")
            raise

        print("\nDone. All legacy documents and dependent rows deleted.")

        # Verify
        verify = await conn.execute(COUNT_LEGACY)
        remaining = verify.scalar()
        print(f"Verification: {remaining} legacy document(s) remaining (expected 0).")

    await engine.dispose()


if __name__ == "__main__":
    execute = "--execute" in sys.argv
    if execute:
        print("WARNING: Running in EXECUTE mode — this will permanently delete data.")
        confirm = input("Type 'yes' to confirm: ").strip().lower()
        if confirm != "yes":
            print("Aborted.")
            sys.exit(0)
    asyncio.run(run(execute=execute))
