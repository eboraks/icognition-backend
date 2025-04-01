from pg8000 import IntegrityError
from app.log import get_logger
from app.response_models import ExtractedEntity, Status 
logging = get_logger(__name__)


import os
import pickle
import re
from sqlalchemy import select, func, update
from sqlalchemy.orm import Session
from app.models import Entity, Document, Document_Entity_Link, Entity_User_Link, Source, User
from app.gemini_client import GeminiClient
import app.getters as getter
from app.wikidata_client import WikidataClient
from app.gemini_prompts_models import EntitiesPrompt, TopicPrompt
from app.db_connector import get_engine

engine = get_engine()

genimi_client = GeminiClient()

wikidata = WikidataClient()





async def generate_entities_vectors():
    with Session(engine) as session:
        entities = session.scalars(
            select(Entity).where(Entity.name_vector == None)
        ).all()

        for entity in entities:

            entity.name_vector = await genimi_client.generate_embedding(entity.name)
            session.add(entity)

        session.commit()
        logging.info(f"Vector names for {len(entities)} entities were generated")

    with Session(engine) as session:
        entities = session.scalars(
            select(Entity).where(Entity.description_vector == None)
        ).all()
        logging.info(f"Entities without description vector {len(entities)}")

        for entity in entities:
            entity.description_vector = await genimi_client.generate_embedding(
                entity.name + ": " + entity.description
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

            
            ## Safe insert, return existing entity if it already exists or the new one
            with Session(engine) as session:
                try:
                    entity_obj = Entity(
                        id=(entity.name + entity.type).replace(" ", "").lower(),
                        name=entity.name,
                        description=entity.description,
                        type=entity.type,
                    )
                    # First merge the entity
                    session.merge(entity_obj)
                    session.flush()  # Flush to get the entity ID
                    
                    # Then create and merge the links
                    session.merge(Entity_User_Link(user_id=user_id, entity_id=entity_obj.id))
                    session.merge(Document_Entity_Link(
                        document_id=doc_id,
                        entity_id=entity_obj.id
                    ))
                    session.commit()
                except IntegrityError as e:
                    session.rollback()
                    logging.warning(f"Entity {entity.name} already exists, skipping: {e}")
                    continue
                except Exception as e:
                    session.rollback()
                    logging.error(f"Error inserting entity {entity.name}: {e}")
                    continue

    except Exception as e:
        logging.error(f"Error inserting entities {e}")
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
