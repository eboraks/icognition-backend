from pg8000 import IntegrityError
from app.log import get_logger
logging = get_logger(__name__)


import os
import pickle
import re
import json
from sqlalchemy import select, func, update
from sqlalchemy.orm import Session
from pydantic import BaseModel
from app.models import Entity, Document, Document_Entity_Link, Entity_User_Link, Source, User
from app.response_models import ExtractedEntity, Status, MatchResult
from app.gemini_client import GeminiClient
from app.wikidata_client import WikidataClient, WikidataSearchResult
from app.gemini_prompts_models import EntitiesPrompt, TopicPrompt
from app.db_connector import get_engine
from typing import List, Optional

engine = get_engine()

genimi_client = GeminiClient()

wikidata = WikidataClient()





async def generate_entities_vectors():
    with Session(engine) as session:
        entities = session.scalars(
            select(Entity).where(Entity.description_vector == None)
        ).all()
        logging.info(f"Entities without description vector {len(entities)}")

        for entity in entities:
            # If entity has description, generate the vector
            if entity.description:
                # Use a different model for the larger 3072-dimension vector if needed
                # You might need to specify a different model in generate_embedding for larger vectors
                # Check if a specific model is needed for larger dimension vectors
                rich_text = f"{entity.name}: {entity.description}"
                if entity.wikidata_description:
                    rich_text += f" Wikidata description: {entity.wikidata_description}"
                if entity.wikidata_instance_of:
                    rich_text += f" Instance of: {', '.join(entity.wikidata_instance_of)}"
                
                entity.description_vector = await genimi_client.generate_embedding(
                    content=rich_text,
                    model_name=os.getenv("GEMINI_EMBEDDING_MODEL_LARGE", os.getenv("GEMINI_EMBEDDING_MODEL"))
                )
            session.add(entity)
            session.commit()
        logging.info(f"Vector descriptions for {len(entities)} entities were generated")


async def insert_entities(
    user_id, entities: list[ExtractedEntity], doc_id: str
):
    try:
        for entity in entities:
            ## Use regex to make sure the entity is words only and contains at least one letter
            if not re.match(r"^[A-Za-z0-9\s\-+()'.#]*[A-Za-z]+[A-Za-z0-9\s\-+()'.#]*$", entity.name):
                logging.warning(
                    f"Entity name '{entity.name}' contains non-word characters or no letters and will be skipped"
                )
                continue

            try:
                # Check if the entity already exists
                existing_entity = await find_existing_entity(entity.name)
                
                if existing_entity:
                    # Just update the links
                    with Session(engine) as session:
                        try:
                            # Create and merge the links
                            session.merge(Entity_User_Link(user_id=user_id, entity_id=existing_entity.id))
                            session.merge(Document_Entity_Link(
                                document_id=doc_id,
                                entity_id=existing_entity.id
                            ))
                            session.commit()
                        except Exception as e:
                            session.rollback()
                            logging.error(f"Error updating links for entity {entity.name}: {e}")
                            continue
                else:
                    # Enrich and insert new entity
                    enriched_entity = await find_wikidata_entity(entity)
                    
                    # Generate embedding vector if not already available
                    if len(enriched_entity.description_vector) == 0 and enriched_entity.description:
                        rich_text = f"{enriched_entity.name}: {enriched_entity.description}"
                        if enriched_entity.wikidata_description:
                            rich_text += f" Wikidata description: {enriched_entity.wikidata_description}"
                        if enriched_entity.wikidata_instance_of:
                            rich_text += f" Instance of: {', '.join(enriched_entity.wikidata_instance_of)}"
                        
                        enriched_entity.description_vector = await genimi_client.generate_embedding(
                            content=rich_text,
                            task_type="SEMANTIC_SIMILARITY"
                        )
                    
                    with Session(engine) as session:
                        try:
                            # First merge the entity
                            merged_entity = session.merge(enriched_entity)
                            session.flush()
                            
                            # Then create and merge the links
                            session.merge(Entity_User_Link(user_id=user_id, entity_id=merged_entity.id))
                            session.merge(Document_Entity_Link(
                                document_id=doc_id,
                                entity_id=merged_entity.id
                            ))
                            session.commit()
                            logging.info(f"Processed entity: {entity.name}")
                        except IntegrityError as e:
                            session.rollback()
                            logging.warning(f"Entity {entity.name} already exists, skipping: {e}")
                            continue
                        except Exception as e:
                            session.rollback()
                            logging.error(f"Error inserting entity {entity.name}: {e}")
                            continue
                                
            except Exception as enrichment_error:
                logging.error(f"Error processing entity {entity.name}: {enrichment_error}")
                continue

    except Exception as e:
        logging.error(f"Error inserting entities: {e}")
        return None


async def populate_entities():

    ## Get document.types_and_concepts from the database
    with Session(engine) as session:
        
        ## get all users
        users = session.scalars(select(User)).all()
        
        for user in users:
            # Join Document and Source tables to find documents belonging to the user
            documents = session.scalars(
                select(Document)
                .join(Source, Document.id == Source.document_id)
                .where(Source.user_id == user.id)
            ).all()
            for document in documents:
                types_and_concepts = document.types_and_concepts
                
                ## For each type and concept, create ExtractedEntity and insert it into the database
                entities = []
                for type_and_concept in types_and_concepts:
                    entity = ExtractedEntity(
                        name=type_and_concept["name"],
                        type=type_and_concept["type"],
                        description=type_and_concept["description"],
                        status=Status.SUCCESS
                    )
                    entities.append(entity)
        
                if len(entities) > 0:
                    await insert_entities(user.id, entities, document.id)

        


async def generate_embeddings_for_entities(entities: list[Entity], user_id: str):

    logging.info(f"Generating embeddings for {len(entities)} entities")

    with Session(engine) as session:

        embeddings = []
        for entity in entities:
            session.add(entity)
            for emb in entity.to_embeddings():
                if emb.text:
                    emb.vector = await genimi_client.generate_embedding(emb.text)
                    emb.user_id = user_id
                    embeddings.append(emb)

        session.add_all(embeddings)
        session.commit()


async def search_wikidata_and_update_entity(entity: Entity) -> bool:
    """
    Search wikidata for entity and return the description
    """ 

    if entity.normalized_label:
        term = entity.normalized_label
    else:
        term = entity.name

    wiki_entities = await wikidata.search_by_label(term)

    for wiki_entity in wiki_entities:
        id = wiki_entity["id"]
        label = wiki_entity["label"]
        description = wiki_entity["description"]
        instance_of = wiki_entity["instance_of"]
        aliases = wiki_entity["alias"]

        logging.info(f"Entity found in Wikidata: {label}, search term: {term}")
        if label.lower() == term.lower():
            entity.normalized_label = label
            entity.description = description
            entity.instance_of = instance_of
            entity.aliases = aliases
            entity.wikidata_id = id

            with Session(engine) as session:
                session.add(entity)
                session.merge(entity)
                session.commit()
                return True

    return False


async def find_entities_without_wikidata_id():
    with Session(engine) as session:
        entities = session.scalars(
            select(Entity).where(Entity.wikidata_id == None)
        ).all()

        logging.info(f"Entities without wikidata_id {len(entities)}")

        for entity in entities:
            await search_wikidata_and_update_entity(entity)


async def find_duplicate_entities() -> list[tuple[str, list[Entity]]]:
    """
    Find entities with duplicate names and return them grouped.
    Returns list of tuples containing (name, list of duplicate entities)
    """
    try:
        with Session(engine) as session:
            # First get all entity names that have duplicates
            stmt = (
                select(Entity.name, func.count(Entity.id).label("count"))
                .group_by(Entity.name)
                .having(func.count(Entity.id) > 1)
            )

            duplicate_names = session.execute(stmt).all()

            # For each duplicate name, get all entities
            duplicates = []
            for name, _ in duplicate_names:
                entities = session.scalars(
                    select(Entity).where(Entity.name == name)
                ).all()
                duplicates.append((name, entities))

            logging.info(f"Found {len(duplicates)} entities with duplicates")
            return duplicates
    except Exception as e:
        logging.error(f"Error finding duplicate entities: {e}")
        return []


async def merge_duplicate_entities():
    """
    Merge all duplicate entities by keeping one and updating references
    """
    try:
        duplicates = await find_duplicate_entities()

        with Session(engine) as session:
            for name, entities in duplicates:
                # Use the first entity as primary
                primary_entity = entities[0]
                duplicate_entities = entities[1:]

                logging.info(
                    f"Merging {len(duplicate_entities)} duplicates of '{name}'"
                )

                for dup_entity in duplicate_entities:
                    # Update all document_entity_links to point to primary entity
                    stmt = (
                        update(Document_Entity_Link)
                        .where(Document_Entity_Link.entity_id == dup_entity.id)
                        .values(entity_id=primary_entity.id)
                    )
                    session.execute(stmt)

                    # Update all entity_user_links to point to primary entity
                    stmt = (
                        update(Entity_User_Link)
                        .where(Entity_User_Link.entity_id == dup_entity.id)
                        .values(entity_id=primary_entity.id)
                    )
                    session.execute(stmt)

                    # Delete the duplicate entity
                    session.delete(dup_entity)

                session.commit()

        logging.info("Completed merging duplicate entities")
        return True
    except Exception as e:
        logging.error(f"Error merging duplicate entities: {e}")
        return False


async def find_wikidata_entity(entity: ExtractedEntity) -> Entity:
    """
    Search Wikidata for an entity based on the extracted entity information.
    Uses WikidataClient to find potential matches and then GeminiClient to identify best match.
    """
    try:
        # Search Wikidata for potential matches
        search_results = await wikidata.text_search(entity.name)
        
        if not search_results or len(search_results) == 0:
            return Entity(
                id=(entity.name + entity.type).replace(" ", "").lower(),
                name=entity.name,
                description=entity.description,
                type=entity.type
            )
        
        # Create a prompt for Gemini
        prompt = f"""
        I need to identify the most likely match between an extracted entity and potential Wikidata entities.
        
        Extracted Entity:
        - Name: {entity.name}
        - Type: {entity.type}
        - Description: {entity.description}
        
        Potential Wikidata Matches:
        {json.dumps([{"id": r.id, "label": r.label, "description": r.description, "aliases": r.aliases, "instance_of": r.instance_of} for r in search_results[:5]], indent=2)}
        
        Analyze the name, description, and entity type to determine the most likely match.
        Return a JSON object in this format:
        {{
            "best_match_index": <index of the best match (0-based)>,
            "match_confidence": <confidence level between 0-1>,
            "reasoning": <brief explanation of why this is the best match>
        }}
        
        If none of the Wikidata entities are a good match, set the best_match_index to -1.
        """
        
        try:
            gemini_response = await genimi_client.generate_response(prompt, MatchResult)
            
            if gemini_response.best_match_index >= 0 and gemini_response.best_match_index < len(search_results):
                # We have a match
                result = search_results[gemini_response.best_match_index]
                
                # Use the wikidata client to get the detailed information using the id
                detailed_info = await wikidata.search_by_id(result.id)
                
                # verify that the detailed info label is the same as the result label
                if detailed_info.label != result.label:
                    return Entity(
                        id=(entity.name + entity.type).replace(" ", "").lower(),
                        name=entity.name,
                        description=entity.description,
                        type=entity.type
                    )
                
                # Create the Entity with additional Wikidata fields
                entity_obj = Entity(
                    id=(entity.name + entity.type).replace(" ", "").lower(),
                    name=entity.name,
                    normalized_label=result.label,
                    description=entity.description,  # Keep the original description
                    type=entity.type,
                    wikidata_id=result.id,
                    wikidata_label=result.label,
                    wikidata_description=result.description,
                    wikidata_instance_of=result.instance_of,
                    aliases=[{"alias": alias} for alias in result.aliases] if result.aliases else []
                )
                
                # Try to get detailed entity information including pageviews
                try:
                    # Get more detailed information if available
                    detailed_info = await wikidata.search_by_id(result.id)
                    if detailed_info:
                        # Update with more detailed information
                        entity_obj.wikidata_instance_of = detailed_info.instance_of if detailed_info.instance_of else entity_obj.wikidata_instance_of
                except Exception as detail_error:
                    pass
                
                return entity_obj
            else:
                return Entity(
                    id=(entity.name + entity.type).replace(" ", "").lower(),
                    name=entity.name,
                    description=entity.description,
                    type=entity.type
                )
                
        except Exception as e:
            # If Gemini analysis fails, just use the top result
            logging.error(f"Error in Gemini analysis for {entity.name}: {str(e)}")
            result = search_results[0]
            return Entity(
                id=(entity.name + entity.type).replace(" ", "").lower(),
                name=entity.name,
                normalized_label=result.label,
                description=entity.description,
                type=entity.type,
                wikidata_id=result.id,
                wikidata_label=result.label,
                wikidata_description=result.description,
                wikidata_instance_of=result.instance_of,
                aliases=[{"alias": alias} for alias in result.aliases] if result.aliases else []
            )
            
    except Exception as e:
        logging.error(f"Error finding Wikidata entity for {entity.name}: {str(e)}")
        return Entity(
            id=(entity.name + entity.type).replace(" ", "").lower(),
            name=entity.name,
            description=entity.description,
            type=entity.type
        )


async def find_existing_entity(name: str) -> Optional[Entity]:
    """
    Search for an existing entity with the same name or normalized label.
    """
    try:
        with Session(engine) as session:
            # First try exact name match
            entity = session.scalar(
                select(Entity).where(Entity.name.ilike(f"{name}"))
            )
            if entity:
                return entity
            
            # Then try normalized label match
            entity = session.scalar(
                select(Entity).where(Entity.normalized_label.ilike(f"{name}"))
            )
            return entity
    except Exception as e:
        logging.error(f"Error finding existing entity: {e}")
        return None
