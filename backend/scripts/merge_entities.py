"""
Migration script to merge duplicate entities and anchor them to Wikidata.
Ensures entities are global and deduplicated.
"""

import asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, text
from sqlmodel import select as sqlmodel_select

from app.db.database import get_session
from app.models import Entity, EntityDocument, User
# We'll use a local link table if it exists, or just ensure EntityDocument is updated
from app.services.wikidata_service import get_wikidata_service
from app.services.embedding_service import get_embedding_service
from app.utils.logging import get_logger

logger = get_logger(__name__)

async def merge_entities():
    """
    Identify duplicate entities, anchor them to Wikidata, and merge them.
    """
    logger.info("Starting entity merge and Wikidata anchoring migration...")
    
    wikidata_service = get_wikidata_service()
    embedding_service = get_embedding_service()
    
    async for session in get_session():
        # 1. Get all unique name/type combinations
        query = select(Entity.name, Entity.type, func.count(Entity.id)).group_by(Entity.name, Entity.type).having(func.count(Entity.id) >= 1)
        result = await session.execute(query)
        entity_groups = result.fetchall()
        
        logger.info(f"Found {len(entity_groups)} unique entity groups to process")
        
        for name, etype, count in entity_groups:
            try:
                # Fetch all entities in this group
                ent_query = select(Entity).where(and_(Entity.name == name, Entity.type == etype)).order_by(Entity.created_at.asc())
                ent_result = await session.execute(ent_query)
                entities = ent_result.scalars().all()
                
                if not entities:
                    continue
                
                # Primary entity will be the first one (oldest)
                primary = entities[0]
                duplicates = entities[1:]
                
                # OPTIMIZATION: If primary is already global and has wikidata, and we have no duplicates, skip
                if primary.user_id is None and primary.wikidata_id and not duplicates:
                    continue

                logger.info(f"Processing group: {name} ({etype}) - {count} records")
                
                # Try to anchor primary to Wikidata if not already anchored
                if not primary.wikidata_id:
                    wd_results = await wikidata_service.search_entities(name, limit=1)
                    if wd_results:
                        match = wd_results[0]
                        primary.wikidata_id = match.wikidata_id
                        primary.wikidata_label = match.label
                        primary.wikidata_description = match.description
                        primary.wikidata_url = match.url
                        primary.aliases = match.aliases
                        logger.info(f"Anchored '{name}' to Wikidata ID: {match.wikidata_id}")
                
                # If we have duplicates, merge them into primary
                for duplicate in duplicates:
                    logger.info(f"Merging entity {duplicate.id} into {primary.id}")
                    
                    # Robust merge for entity_documents:
                    # 1. Delete links from duplicate that would conflict with primary
                    conflict_stmt = text(
                        "DELETE FROM entity_documents "
                        "WHERE entity_id = :duplicate_id AND document_id IN ("
                        "  SELECT document_id FROM entity_documents WHERE entity_id = :primary_id"
                        ")"
                    )
                    await session.execute(conflict_stmt, {"primary_id": primary.id, "duplicate_id": duplicate.id})
                    
                    # 2. Update the remaining links
                    update_docs_stmt = text(
                        "UPDATE entity_documents SET entity_id = :primary_id WHERE entity_id = :duplicate_id"
                    )
                    await session.execute(update_docs_stmt, {"primary_id": primary.id, "duplicate_id": duplicate.id})
                    
                    # Delete the duplicate entity record
                    await session.delete(duplicate)
                
                # Set primary as global
                primary.user_id = None 
                
                # Ensure primary has embeddings
                await embedding_service.generate_and_store_entity_embeddings(
                    session=session,
                    entity=primary,
                    user_id="global",
                    force_regenerate=False
                )
                
                await session.commit()
                
            except Exception as e:
                logger.error(f"Error processing entity group '{name}': {e}")
                await session.rollback()
                continue

    logger.info("Entity migration completed successfully")

if __name__ == "__main__":
    asyncio.run(merge_entities())
