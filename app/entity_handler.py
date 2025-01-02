import os
import pickle
import re
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models import Entity, Document, Document_Entity_Link, Entity_User_Link, Source
from app.gemini_client import GeminiClient
import app.getters as getter
from app.wikidata_client import WikidataClient
from app.gemini_prompts_models import EntitiesPrompt, TopicPrompt
from app.log import get_logger
from app.db_connector import get_engine

engine = get_engine()

logging = get_logger(__name__)
genimi_client = GeminiClient()

wikidata = WikidataClient()


async def generate_document_entities(source: Source):
    document = getter.get_document_by_id(source.document_id)

    try:
        if len(getter.get_entities_ids_by_document_id(document.id)) == 0:
            ent_success = await generate_entities(user_id=source.user_id, doc=document)
            topic_success = await generate_topics(user_id=source.user_id, doc=document)
            logging.info(
                f"Background task for generating entities and topics for: {document.id} completed. Result, number of entities: {len(ent_success)} number of topics: {len(topic_success)}"
            )
            await generate_embeddings_for_entities(
                entities=ent_success, user_id=source.user_id
            )
            await generate_embeddings_for_entities(
                entities=topic_success, user_id=source.user_id
            )
    except Exception as e:
        logging.error("Generate document entities ", e)


async def generate_entities(
    user_id: str, doc: Document, testing: bool = False
) -> list[Entity]:
    """
    Generate entities for a document

    args:
        user_id: str
        doc: Document
        testing: bool
    """
    try:
        logging.info(f"Generating entities for document {doc.id}")

        ## If file exists, load it and return payload
        filename = f"response_two_{doc.id}.json"
        if os.path.exists(filename):
            with open(filename, "rb") as f:
                response = pickle.load(f)
                logging.info(f"Response loaded from file for document {doc.id}")
        else:
            response = await genimi_client.generate_response(
                EntitiesPrompt.build_prompt(doc.original_text), EntitiesPrompt
            )
            # logging.info(f"Response from LLM {response}")

            if testing:
                with open(filename, "wb") as f:
                    pickle.dump(response, f)

        # Using the entities builder to get the entities from the response
        entities = response.entities_builder()

        if len(entities) == 0:
            logging.info(f"No entities were found for document {doc.id}")
            return []

        ## Iterate over entities check if verbatim_text is in the original_text, if not, remove it
        entities = [
            entity
            for entity in entities
            if doc.original_text.find(entity.verbatim_text) != -1
        ]

        return await insert_entities(user_id, entities, doc)

    except Exception as e:
        logging.error(f"generate_entities: Error generating entities from LLM API {e}")
        return None


async def generate_topics(
    user_id: str, doc: Document, testing: bool = False
) -> list[Entity]:
    """
    # Generate topics for a document
    """
    try:
        logging.info(f"Generating entities for document {doc.id}")

        ## If file exists, load it and return payload
        filename = f"response_two_{doc.id}.json"
        if os.path.exists(filename):
            with open(filename, "rb") as f:
                response = pickle.load(f)
                logging.info(f"Response loaded from file for document {doc.id}")
        else:
            response = await genimi_client.generate_response(
                TopicPrompt.build_prompt(doc.original_text), TopicPrompt
            )
            # logging.info(f"Response from LLM {response}")

            if testing:
                with open(filename, "wb") as f:
                    pickle.dump(response, f)

        # Using the entities builder to get the topics (also entities) from the response
        entities = response.entities_builder()

        if len(entities) == 0:
            logging.info(f"No topic were found for document {doc.id}")
            return []

        ## Iterate over entities check if verbatim_text is in the original_text, if not, remove it
        entities = [
            entity
            for entity in entities
            if doc.original_text.find(entity.verbatim_text) != -1
        ]

        return await insert_entities(user_id, entities, doc)

    except Exception as e:
        logging.error(f"generate_topics: Error generating entities from LLM API {e}")
        return None


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
    user_id, entities: list[Entity], doc: Document
) -> list[Entity]:

    ## Make sure all previous created entities have vectors
    ## This allow search for similar entities before creating a new one
    await generate_entities_vectors()

    try:
        session_entities = []
        for entity in entities:
            ## Use regex to make sure the entity is words only
            if not re.match(r"^[A-Za-z\s]+$", entity.name):
                logging.warning(
                    f"Entity name '{entity.name}' contains non-word characters and will be skipped"
                )
                continue

            if entity.type == "Other":
                ## Skip entities that are of type 'Other' to save space and computation
                logging.warning(
                    f"Entity name '{entity.name}' is of type 'Other' and will be skipped"
                )
                continue

            ## Safe insert, return existing entity if it already exists or the new one
            session_entities.append(
                await insert_entity_safe(
                    user_id=user_id, new_entity=entity, _document_id=doc.id
                )
            )

        logging.info(
            f"{len(session_entities)} Entities for Document {doc.id} were associated"
        )

        return session_entities
    except Exception as e:
        logging.error(f"Error inserting entities {e}")
        return None


async def insert_entity_safe(
    user_id: str, new_entity: Entity, _document_id: str
) -> Entity:

    matched_entity = await getter.get_similar_entity_by_name_vector(
        user_id=user_id, new_entity=new_entity
    )

    with Session(engine) as session:

        if matched_entity:

            logging.info(
                f"Matched Entity. New: {new_entity.name} Existing: {matched_entity.name}"
            )

            session.merge(
                Document_Entity_Link(
                    document_id=_document_id,
                    entity_id=matched_entity.id,
                    verbatim_text=new_entity.verbatim_text,
                    description=new_entity.description,
                )
            )
            session.commit()
            return new_entity
        else:
            new_entity.name_vector = await genimi_client.generate_embedding(
                new_entity.name
            )
            new_entity.description_vector = await genimi_client.generate_embedding(
                new_entity.name + ": " + new_entity.description
            )
            session.add(new_entity)
            session.commit()
            session.refresh(new_entity)

            session.merge(Entity_User_Link(user_id=user_id, entity_id=new_entity.id))
            session.merge(
                Document_Entity_Link(
                    document_id=_document_id,
                    entity_id=new_entity.id,
                    verbatim_text=new_entity.verbatim_text,
                    description=new_entity.description,
                )
            )

            session.commit()
            return new_entity


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
