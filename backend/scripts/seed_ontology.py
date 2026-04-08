"""
Seed kg_canonical_class and kg_canonical_property tables from schema.ttl.

Parses schema.org classes and properties using rdflib, generates embeddings
via EmbeddingService, and upserts into the canonical tables.

Usage:
    cd backend
    python -m scripts.seed_ontology
    python -m scripts.seed_ontology --dry-run       # parse only, no DB writes
    python -m scripts.seed_ontology --skip-embeddings  # seed without vectors
"""

import asyncio
import argparse
import os
import sys
import time
from pathlib import Path
from typing import Optional

from rdflib import Graph, Namespace, RDF, RDFS, OWL
from dotenv import load_dotenv

# Ensure backend package is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

load_dotenv()

from app.utils.logging import get_logger
from app.db.database import async_session, engine
from app.models_kg import KGCanonicalClass, KGCanonicalProperty

logger = get_logger(__name__)

SCHEMA = Namespace("https://schema.org/")
SCHEMA_TTL_PATH = Path(__file__).resolve().parent.parent.parent / "instructions" / "schema.ttl"

# Batch size for concurrent embedding calls
EMBED_BATCH_SIZE = 20


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def parse_schema_classes(g: Graph) -> list[dict]:
    """Extract schema.org classes from the RDF graph."""
    classes = []
    for subj in g.subjects(RDF.type, RDFS.Class):
        uri = str(subj)
        if not uri.startswith(str(SCHEMA)):
            continue

        label = None
        for obj in g.objects(subj, RDFS.label):
            label = str(obj)
            break

        description = None
        for obj in g.objects(subj, RDFS.comment):
            description = str(obj)
            break

        parent_uri = None
        for obj in g.objects(subj, RDFS.subClassOf):
            parent = str(obj)
            if parent.startswith(str(SCHEMA)):
                parent_uri = parent
                break

        if label:
            classes.append({
                "uri": uri,
                "label": label,
                "description": description,
                "parent_uri": parent_uri,
            })

    logger.info(f"Parsed {len(classes)} schema.org classes")
    return classes


def parse_schema_properties(g: Graph) -> list[dict]:
    """Extract schema.org properties from the RDF graph."""
    props = []
    for subj in g.subjects(RDF.type, RDF.Property):
        uri = str(subj)
        if not uri.startswith(str(SCHEMA)):
            continue

        label = None
        for obj in g.objects(subj, RDFS.label):
            label = str(obj)
            break

        description = None
        for obj in g.objects(subj, RDFS.comment):
            description = str(obj)
            break

        parent_uri = None
        for obj in g.objects(subj, RDFS.subPropertyOf):
            parent = str(obj)
            if parent.startswith(str(SCHEMA)):
                parent_uri = parent
                break

        # domainIncludes / rangeIncludes — take first schema.org value
        domain_class_uri = None
        for obj in g.objects(subj, SCHEMA.domainIncludes):
            candidate = str(obj)
            if candidate.startswith(str(SCHEMA)):
                domain_class_uri = candidate
                break

        range_class_uri = None
        for obj in g.objects(subj, SCHEMA.rangeIncludes):
            candidate = str(obj)
            if candidate.startswith(str(SCHEMA)):
                range_class_uri = candidate
                break

        if label:
            props.append({
                "uri": uri,
                "label": label,
                "description": description,
                "parent_uri": parent_uri,
                "domain_class_uri": domain_class_uri,
                "range_class_uri": range_class_uri,
            })

    logger.info(f"Parsed {len(props)} schema.org properties")
    return props


# ---------------------------------------------------------------------------
# Embedding generation
# ---------------------------------------------------------------------------

def _embed_text(label: str, description: Optional[str]) -> str:
    """Build the text string that will be embedded."""
    if description:
        # Truncate very long descriptions to keep embedding focused
        desc = description[:500]
        return f"{label}: {desc}"
    return label


async def generate_embeddings_batch(items: list[dict], embedding_service) -> list[dict]:
    """Generate embeddings for a list of items (each must have 'label' and 'description')."""
    from app.services.embedding_service import EmbeddingResult

    async def embed_one(item: dict) -> dict:
        text = _embed_text(item["label"], item.get("description"))
        result: EmbeddingResult = await embedding_service.generate_embedding(
            text=text,
            task_type="RETRIEVAL_DOCUMENT",
        )
        if result.success:
            item["vector"] = result.embedding
        else:
            logger.warning(f"Embedding failed for {item['uri']}: {result.error}")
            item["vector"] = None
        return item

    # Process in batches to avoid rate limits
    for i in range(0, len(items), EMBED_BATCH_SIZE):
        batch = items[i : i + EMBED_BATCH_SIZE]
        await asyncio.gather(*(embed_one(item) for item in batch))
        if i + EMBED_BATCH_SIZE < len(items):
            # Small delay between batches to be kind to the API
            await asyncio.sleep(0.5)

    embedded_count = sum(1 for item in items if item.get("vector") is not None)
    logger.info(f"Generated {embedded_count}/{len(items)} embeddings")
    return items


# ---------------------------------------------------------------------------
# Database upsert
# ---------------------------------------------------------------------------

async def upsert_classes(classes: list[dict]) -> int:
    """Insert or update canonical classes."""
    from sqlalchemy import select

    count = 0
    async with async_session() as session:
        for cls in classes:
            stmt = select(KGCanonicalClass).where(KGCanonicalClass.uri == cls["uri"])
            result = await session.execute(stmt)
            existing = result.scalars().first()

            if existing:
                existing.label = cls["label"]
                existing.description = cls.get("description")
                existing.parent_uri = cls.get("parent_uri")
                if cls.get("vector") is not None:
                    existing.vector = cls["vector"]
            else:
                session.add(KGCanonicalClass(
                    uri=cls["uri"],
                    label=cls["label"],
                    description=cls.get("description"),
                    parent_uri=cls.get("parent_uri"),
                    vector=cls.get("vector"),
                ))
                count += 1

        await session.commit()
    logger.info(f"Upserted {len(classes)} classes ({count} new)")
    return count


async def upsert_properties(props: list[dict]) -> int:
    """Insert or update canonical properties."""
    from sqlalchemy import select

    count = 0
    async with async_session() as session:
        for prop in props:
            stmt = select(KGCanonicalProperty).where(KGCanonicalProperty.uri == prop["uri"])
            result = await session.execute(stmt)
            existing = result.scalars().first()

            if existing:
                existing.label = prop["label"]
                existing.description = prop.get("description")
                existing.parent_uri = prop.get("parent_uri")
                existing.domain_class_uri = prop.get("domain_class_uri")
                existing.range_class_uri = prop.get("range_class_uri")
                if prop.get("vector") is not None:
                    existing.vector = prop["vector"]
            else:
                session.add(KGCanonicalProperty(
                    uri=prop["uri"],
                    label=prop["label"],
                    description=prop.get("description"),
                    parent_uri=prop.get("parent_uri"),
                    domain_class_uri=prop.get("domain_class_uri"),
                    range_class_uri=prop.get("range_class_uri"),
                    vector=prop.get("vector"),
                ))
                count += 1

        await session.commit()
    logger.info(f"Upserted {len(props)} properties ({count} new)")
    return count


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main(dry_run: bool = False, skip_embeddings: bool = False):
    ttl_path = SCHEMA_TTL_PATH
    if not ttl_path.exists():
        logger.error(f"schema.ttl not found at {ttl_path}")
        sys.exit(1)

    logger.info(f"Loading schema.ttl from {ttl_path}")
    t0 = time.time()
    g = Graph()
    g.parse(str(ttl_path), format="turtle")
    logger.info(f"Parsed RDF graph in {time.time() - t0:.1f}s ({len(g)} triples)")

    classes = parse_schema_classes(g)
    properties = parse_schema_properties(g)

    if dry_run:
        logger.info("=== DRY RUN — no DB writes ===")
        logger.info(f"Would seed {len(classes)} classes and {len(properties)} properties")
        # Print a few examples
        for c in classes[:5]:
            logger.info(f"  Class: {c['uri']}  label={c['label']}  parent={c.get('parent_uri')}")
        for p in properties[:5]:
            logger.info(f"  Prop:  {p['uri']}  label={p['label']}  domain={p.get('domain_class_uri')}  range={p.get('range_class_uri')}")
        return

    if not skip_embeddings:
        from app.services.embedding_service import get_embedding_service
        embedding_service = get_embedding_service()

        logger.info("Generating embeddings for classes...")
        classes = await generate_embeddings_batch(classes, embedding_service)

        logger.info("Generating embeddings for properties...")
        properties = await generate_embeddings_batch(properties, embedding_service)

    logger.info("Upserting classes to DB...")
    await upsert_classes(classes)

    logger.info("Upserting properties to DB...")
    await upsert_properties(properties)

    logger.info("Seed complete!")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed schema.org canonical tables")
    parser.add_argument("--dry-run", action="store_true", help="Parse only, no DB writes")
    parser.add_argument("--skip-embeddings", action="store_true", help="Seed without generating vectors")
    args = parser.parse_args()

    asyncio.run(main(dry_run=args.dry_run, skip_embeddings=args.skip_embeddings))
