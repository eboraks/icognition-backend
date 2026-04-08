"""
KG Pipeline — standalone background task for building the knowledge graph.

This module is decoupled from the content extraction pipeline so that:
1. The user gets their summary/bullet points without waiting for KG processing
2. In the future, this can run as a separate container/service

Entry point: process_document_kg_background()
"""

from sqlalchemy import select

from app.core.config import settings
from app.db.database import async_session
from app.models import Document
from app.services.kg_adapter import KGAdapter
from app.services.dspy_entity_service import get_dspy_entity_service
from app.utils.logging import get_logger

logger = get_logger(__name__)


async def process_document_kg_background(
    document_id: int,
    user_id: str,
) -> None:
    """
    Standalone background task that runs the full KG pipeline for a document.

    Steps:
    1. Load the document content
    2. Extract entities (DSPy)
    3. Extract relationships (DSPy)
    4. Align to schema.org + Wikidata and persist KG nodes/edges

    This task is fire-and-forget — failures are logged but don't affect
    the user-facing content pipeline.
    """
    if not settings.KG_EXTRACTION_ENABLED:
        return

    try:
        logger.info(f"KG pipeline started for document {document_id}")

        async with async_session() as session:
            # Load document
            result = await session.execute(
                select(Document).where(Document.id == document_id)
            )
            document = result.scalar_one_or_none()

            if not document:
                logger.warning(f"KG pipeline: document {document_id} not found")
                return

            # Check content availability
            if not document.content or not document.content.strip():
                logger.info(f"KG pipeline: skipping document {document_id} — no content")
                return

            if document.content_type in ["not_available", "fetch_failed"]:
                logger.info(f"KG pipeline: skipping document {document_id} — content unavailable")
                return

            # Step 1: Extract entities
            dspy_entity_service = get_dspy_entity_service()
            entities = await dspy_entity_service.extract_entities_from_content(
                content=document.content,
                document_id=document_id,
                session=session,
            )

            if not entities:
                logger.info(f"KG pipeline: no entities extracted for document {document_id}")
                return

            logger.info(f"KG pipeline: extracted {len(entities)} entities for document {document_id}")

            # Step 2: Extract relationships
            relationships = []
            if len(entities) >= 2:
                entity_names = [e["name"] for e in entities]
                relationships = await dspy_entity_service.extract_relationships_from_entities(
                    entity_names=entity_names,
                    content=document.content,
                    document_id=document_id,
                )
                logger.info(
                    f"KG pipeline: extracted {len(relationships)} relationships for document {document_id}"
                )

            # Step 3: Align and persist KG nodes/edges
            kg_adapter = KGAdapter(session)
            kg_result = await kg_adapter.process_document_kg(
                user_id=user_id,
                document_id=document_id,
                raw_entities=entities,
                raw_relationships=relationships,
            )
            await session.commit()

            logger.info(
                f"KG pipeline completed for document {document_id}: "
                f"{kg_result['nodes_created']} nodes created, "
                f"{kg_result['nodes_reused']} reused, "
                f"{kg_result['edges_created']} edges"
            )

    except Exception as e:
        logger.error(f"KG pipeline failed for document {document_id}: {e}")
        import traceback
        logger.error(f"KG pipeline traceback: {traceback.format_exc()}")
