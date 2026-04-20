"""
Diagnose why a document's content field is empty even though raw_html was saved.

Loads the stored raw_html for a given document id, re-runs HtmlContentService
on it, and prints what the extractor produces (title, content length, author,
metadata keys). Does NOT write anything.

Usage:
  cd backend && .venv/bin/python scripts/diag_doc_extraction.py <doc_id>
"""

import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select

from app.db.database import async_session
from app.models import Document
from app.services.html_content_service import HtmlContentService


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("doc_id", type=int)
    args = parser.parse_args()

    async with async_session() as sess:
        doc = (await sess.execute(
            select(Document).where(Document.id == args.doc_id)
        )).scalar_one_or_none()

        if doc is None:
            print(f"doc {args.doc_id} not found")
            return

        print(f"doc {doc.id}")
        print(f"  url:            {doc.url}")
        print(f"  title:          {doc.title}")
        print(f"  raw_html_len:   {len(doc.raw_html or '')}")
        print(f"  content_len:    {len(doc.content or '')}")
        print()

        if not doc.raw_html:
            print("raw_html is empty — nothing to re-extract")
            return

        svc = HtmlContentService()
        result = await svc.extract_content(doc.raw_html, doc.url or "")

        content_str = result.content or ""
        print("re-extraction result:")
        print(f"  title:          {result.title}")
        print(f"  author:         {result.author}")
        print(f"  content_len:    {len(content_str)}")
        print(f"  publish_date:   {result.publication_date}")
        print(f"  image_url:      {result.image_url}")
        print(f"  tags:           {result.tags}")
        print(f"  metadata keys:  {list((result.metadata or {}).keys())}")
        meta_desc = (result.metadata or {}).get("description")
        if meta_desc:
            print(f"  metadata.description ({len(meta_desc)} chars): {meta_desc[:200]}")
        print()

        if content_str:
            preview = content_str.strip()[:400]
            print(f"content preview:\n{preview}")
        else:
            print("content is EMPTY after re-extraction — extractor is not finding body")
            html_preview = doc.raw_html[:1500].replace("\n", " ")
            print("\nraw_html first 1500 chars:")
            print(html_preview)


if __name__ == "__main__":
    asyncio.run(main())
