import time
from app.db_connector import get_engine
from app.models import (
    Chat_Message,
    Document,
    Document_Entity_Link,
    Entity,
    Embedding,
    TreeNode,
    Content_Type,
    Entity_Type,
    Bookmark,
)
from app.deleters import delete_document_and_associate_records
from sqlalchemy.orm import Session, joinedload
from Levenshtein import distance
from app.gemini_client import GeminiClient
from sqlalchemy import (
    and_,
    func,
    or_,
    select,
    text,
)
from app.log import get_logger

logger = get_logger(__name__)

import app.html_parser as html_parser

engine = get_engine()


genimi_client = GeminiClient()


def get_documents_count() -> int:
    with Session(engine) as session:
        count = session.execute(select(func.count(Document.id))).scalar()
    return count


def get_document_public_by_id(document_id: str) -> dict:
    with Session(engine) as session:
        doc = session.scalar(select(Document).where(Document.id == document_id))
        if doc is None:
            raise ValueError(f"Document with id {document_id} not found")
        session.add_all(doc.entities)

        return doc.to_dict()




def get_document_by_id(document_id: str) -> Document:
    with Session(engine) as session:
        doc = session.scalar(select(Document).where(Document.id == document_id))
        if doc is None:
            raise ValueError(f"Document with id {document_id} not found")

        return doc


def get_documents_by_ids(document_ids: set[int]) -> list[Document]:
    """Method that retrieves documents from the database by ID.

    Args:
        document_ids (list[int]): The list of document IDs.

    Returns:
        list[Document]: The list of documents.
    """
    with Session(engine) as session:
        documents = session.scalars(
            select(Document).where(Document.id.in_(document_ids))
        ).all()

    return documents


def get_documents() -> list[Document]:
    session = Session(engine)
    docs = session.scalars(select(Document)).all()
    session.close()
    return docs


def get_document_by_url(user_id: str, url: str) -> Document:
    """Get document by URL and user ID"""
    session = Session(engine)
    doc = session.scalar(
        select(Document)
        .where(Document.url == url, Document.user_id == user_id)
    )
    if doc:
        session.add_all(doc.entities)
    session.close()
    return doc


def get_documents_by_user_id(user_id: str, document_status="Done") -> list[Document]:

    with Session(engine) as session:
        docs = (
            session.scalars(
                select(Document)
                .options(joinedload(Document.entities))
                .join(Source, Source.document_id == Document.id)
                .where(
                    and_(Source.user_id == user_id, Document.status == document_status)
                )
                .order_by(Source.update_at.desc())
            )
            .unique()
            .all()
        )

    return docs


def get_documents_public_by_user_id(
    user_id: str, document_status="Done"
) -> list[dict]:
    results = []
    with Session(engine) as session:

        docs = (
            session.scalars(
                select(Document)
                .join(Source, Source.document_id == Document.id)
                .where(
                    and_(Source.user_id == user_id, Document.status == document_status)
                )
                .order_by(Source.update_at.desc())
            )
            .unique()
            .all()
        )

    for doc in docs:
        try:
            results.append(doc.to_display())
        except Exception as e:
            logger.error(f"Error getting document {doc.id} public by user id: {e}")

    return results


def get_document_by_url(url) -> Document:
    session = Session(engine)
    doc = session.scalar(select(Document).where(Document.url == url))
    session.close()
    return doc


def get_all_documents() -> list[Document]:
    with Session(engine) as session:
        docs = session.scalars(select(Document)).all()
    return docs


def get_documents_ids() -> list[int]:
    session = Session(engine)
    docs_ids = session.scalars(select(Document.id))
    session.close()
    return docs_ids


def get_entities_by_document_id(document_id) -> list[Entity]:
    session = Session(engine)
    entities = session.scalars(
        select(Entity)
        .join(Document_Entity_Link, Document_Entity_Link.entity_id == Entity.id)
        .where(Document_Entity_Link.document_id == document_id)
    ).all()
    session.close()
    return entities


def get_entities_ids_by_document_id(document_id) -> list[int]:
    session = Session(engine)
    entities_ids = session.scalars(
        select(Document_Entity_Link.entity_id).where(
            Document_Entity_Link.document_id == document_id
        )
    ).all()
    session.close()
    return entities_ids


def get_entities_by_ids(entity_ids: set[int]) -> list[Entity]:
    """Method that retrieves entities from the database by ID.

    Args:
        entity_ids (list[int
    """
    with Session(engine) as session:
        entities = (
            session.scalars(select(Entity).where(Entity.id.in_(entity_ids)))
            .unique()
            .all()
        )

    return entities


def find_entity_by_name(entity_name: str) -> Entity:
    with Session(engine) as session:
        entity = session.scalar(
            select(Entity).where(
                or_(
                    Entity.name.ilike(f"{entity_name}"),
                    Entity.normalized_label.ilike(f"{entity_name}"),
                )
            )
        )
    return entity


def find_similar_entities(entity_name: str) -> Entity:

    ## If the entity name is <=5 characters, reduce the levenshtein distance to 1
    if len(entity_name) <= 5:
        distance = 0
    elif len(entity_name) <= 8:
        distance = 1
    elif len(entity_name) <= 15:
        distance = 2
    else:
        distance = 3

    query = text(
        """
        SELECT e.id, e.name, levenshtein(LOWER(e.name), LOWER(:needle)) AS distance
        FROM entity e 
        WHERE (levenshtein_less_equal(LOWER(e.name), LOWER(:needle), :dist) <= :dist)
        OR (levenshtein_less_equal(LOWER(e.normalized_label), LOWER(:needle), :dist) <= :dist)
        ORDER BY levenshtein_less_equal(LOWER(e.name), LOWER(:needle), :dist) ASC
        LIMIT 1
        """
    ).bindparams(needle=entity_name, dist=distance)

    with Session(engine) as session:
        result = session.execute(query).first()

        if result:
            logger.info(
                f"Found similar entity to '{entity_name}' with name {result[1]} and distance {result[2]}"
            )
            entity_id = result[0] if result else None
            entity = session.scalar(select(Entity).where(Entity.id == entity_id))
            return entity
        return None


async def get_similar_entity_by_name_vector(
    user_id: str, new_entity, name_threshold: float = 0.90, desc_threshold=0.70
) -> Entity:

    try:
        with Session(engine) as session:
            entity = session.scalar(
                select(Entity).where(Entity.name.ilike(f"{new_entity.name}"))
            )
            if entity:
                return entity

            entity = session.scalar(
                select(Entity).where(
                    Entity.normalized_label.ilike(f"{new_entity.name}")
                )
            )
            if entity:
                return entity
    except Exception as e:
        logger.error(f"Error getting similar entity by name vector: {e}")

    exit = find_similar_entities(new_entity.name)
    if exit:
        return exit

    name_vector = await genimi_client.generate_embedding(new_entity.name)
    description_vector = await genimi_client.generate_embedding(
        new_entity.name + ": " + new_entity.description
    )

    ## Get similar entity by name and description vector
    with Session(engine) as session:
        query = text(
            """SELECT DISTINCT a.entity_id, a.name, a.name_cosine_similarity, a.desc_cosine_similarity   
                FROM (SELECT e.id AS entity_id, e.name, 
                    MAX(1 - (e.name_vector <=> :name_vector)) AS name_cosine_similarity,
                    MAX(1 - (e.description_vector <=> :description_vector)) AS desc_cosine_similarity 
                        FROM entity AS e
                        JOIN document_entity_link del ON del.entity_id = e.id
                        JOIN source b ON b.document_id = del.document_id
                        WHERE b.user_id = :user_id
                        GROUP BY 1, 2) a
            WHERE a.name_cosine_similarity >= :name_threshold 
            AND a.desc_cosine_similarity >= :desc_threshold
            ORDER BY a.name_cosine_similarity, a.desc_cosine_similarity DESC
            LIMIT 1"""
        )
        result = session.execute(
            query,
            {
                "name_vector": str(name_vector),
                "description_vector": str(description_vector),
                "user_id": user_id,
                "name_threshold": name_threshold,
                "desc_threshold": desc_threshold,
            },
        ).first()

        if result:
            entity_id = result[0]
            entity_name = result[1]
            name_cosine_similarity = result[2]
            desc_cosine_similarity = result[3]

            leven_distance = distance(entity_name.lower(), new_entity.name.lower())

            logger.info(
                f"Potential Found similar entity '{entity_name}' with name similarity {name_cosine_similarity} and description similarity {desc_cosine_similarity}. New entity name is '{new_entity.name}'. Levenstein distance is {leven_distance}"
            )
            if (
                entity_name.lower().find(new_entity.name.lower()) != -1
                or new_entity.name.lower().find(entity_name.lower()) != -1
            ):
                ## Get the entity
                logger.info(
                    f"Found same entity '{entity_name}' with name similarity {name_cosine_similarity} and description similarity {desc_cosine_similarity}. New entity name is '{new_entity.name}'"
                )
                entity = session.scalar(select(Entity).where(Entity.id == entity_id))
                return entity

        return None


def get_bookmarks_by_user_id(user_id: int) -> list[Bookmark]:
    """Get bookmarks by user ID"""
    session = Session(engine)
    bookmarks = session.scalars(
        select(Bookmark)
        .where(Bookmark.user_id == user_id)
        .order_by(Bookmark.created_at.desc())
    ).all()
    session.close()
    return bookmarks


def get_entities_by_document_id(document_id) -> list[Entity]:
    session = Session(engine)
    entities = session.scalars(
        select(Entity)
        .join(Document_Entity_Link, Document_Entity_Link.entity_id == Entity.id)
        .where(Document_Entity_Link.document_id == document_id)
    ).all()
    session.close()
    return entities


def get_entities_names_by_user_id(user_id: str) -> list[str]:
    session = Session(engine)
    entities = session.scalars(
        select(Entity.name)
        .join(Document_Entity_Link, Document_Entity_Link.entity_id == Entity.id)
        .join(Source, Source.document_id == Document_Entity_Link.document_id)
        .where(Source.user_id == user_id)
        .order_by(Entity.name)
        .distinct()
    ).all()
    session.close()
    return entities


def get_entities_by_user_id_and_type(user_id: str, type: str) -> list[Entity]:
    session = Session(engine)
    entities = session.scalars(
        select(Entity)
        .join(Document, Document.id == Entity.document_id)
        .join(Source, Source.document_id == Document.id)
        .where(Source.user_id == user_id, Entity.type == type)
    ).all()
    session.close()
    return entities


def get_documenets_by_entity_id(entity_id: int) -> list[Document]:
    session = Session(engine)
    documents = session.scalars(
        select(Document)
        .join(Document_Entity_Link, Document_Entity_Link.document_id == Document.id)
        .where(Document_Entity_Link.entity_id == entity_id)
    ).all()
    session.close()
    return documents






def get_document_embeddings(document_id: int) -> list[Embedding]:
    with Session(engine) as session:
        embeddings = session.scalars(
            select(Embedding).where(Embedding.source_id == document_id)
        ).all()
    return embeddings


def get_entity_embeddings(entity_id: int) -> list[Embedding]:
    with Session(engine) as session:
        embeddings = session.scalars(
            select(Embedding).where(Embedding.source_id == entity_id)
        ).all()
    return embeddings


def get_documents_by_entity_id(entity_id: int) -> list[Document]:
    with Session(engine) as session:
        documents = (
            session.scalars(
                select(Document)
                .join(
                    Document_Entity_Link,
                    Document_Entity_Link.document_id == Document.id,
                )
                .where(Document_Entity_Link.entity_id == entity_id)
            )
            .unique()
            .all()
        )

    return documents


def get_embedding_by_id(embedding_id: int) -> Embedding:
    with Session(engine) as session:
        embedding = session.scalar(
            select(Embedding).where(Embedding.id == embedding_id)
        )
    return embedding


def calculate_number_of_docs_thredhold(user_id: str) -> int:
    with Session(engine) as session:
        stmt = text(
            """
            SELECT count(distinct document_id) as docs_count
            FROM public.source
            WHERE user_id = :user_id
            """
        )
        docs_count = session.scalar(stmt, {"user_id": user_id})

        return round(docs_count / 50)


def  get_entities_tree_nodes_by_user_id(user_id: str) -> list[TreeNode]:

    min_num_docs = calculate_number_of_docs_thredhold(user_id)
    results = []
    stmt = text(
        """SELECT ta.type, 
            json_agg(distinct ta.name) as ents_names, 
            json_agg(distinct ta.entity_id) as ents_ids, 
            count(distinct ta.document_id) as docs_count,
            json_agg(distinct ta.document_id) as docs_ids
        FROM (SELECT LOWER(e.type) as type, e.name as name, e.description,  e.id as entity_id, l.document_id as document_id
            FROM public.entity e
            JOIN public.document_entity_link l ON l.entity_id = e.id
            JOIN public.entity_user_link ul ON ul.entity_id = e.id
            WHERE ul.user_id = :user_id
            GROUP BY 1, 2, 3, 4, 5
            HAVING count(distinct l.document_id) >= :min_num_docs) AS ta
        GROUP BY 1""")

    try:
        with Session(engine) as session:
            start_time = time.time()
            query = stmt.bindparams(user_id=user_id, min_num_docs=min_num_docs)
            logger.debug(f"Executing query: {query}")
            types = session.execute(query).fetchall()
            logger.info(
                f"Time to get entities tree nodes by user id: {(time.time() - start_time):.2f} seconds"
            )

            start_time = time.time()
            for k, t in enumerate(types):
                top_node = TreeNode(
                    label=t.type.title(),
                    key=(t.type.title().replace(" ", "").lower()),
                    doc_count=t.docs_count,
                    doc_ids=t.docs_ids,
                    children=[],
                )

                entities = (
                    session.scalars(
                        select(Entity)
                        .options(joinedload(Entity.documents))
                        .where(Entity.id.in_(t.ents_ids))
                        .order_by(Entity.name)
                    )
                    .unique()
                    .all()
                )

                for ent in entities:
                    ent_node = ent.to_node()

                    if ent_node.doc_count >= min_num_docs:
                        top_node.children.append(ent_node)

                """ for e_name in t.ents_names:
                    ent_node = session.scalar(select(Entity).where(Entity.name == e_name)).to_node()
                    if ent_node.doc_count > min_num_docs:
                        top_node.children.append(ent_node) """

                # Only add the top node if it has children
                if len(top_node.children) > 1:
                    results.append(top_node)
            logger.info(
                f"Time to create entities tree nodes by user id: {(time.time() - start_time):.2f} seconds"
            )
    except Exception as e:
        logger.error(f"Error getting entities tree nodes by user id: {e}")

    return sorted(results, key=lambda x: x.label, reverse=True)





def get_content_types() -> list[Content_Type]:
    """Get all content types from the database.
    
    Returns:
        list[Content_Type]: List of all content types
    """
    with Session(engine) as session:
        content_types = session.scalars(select(Content_Type)).all()
    return content_types

def get_entity_types() -> list[Entity_Type]:
    """Get all entity types from the database.
    
    Returns:
        list[Entity_Type]: List of all entity types
    """
    with Session(engine) as session:
        entity_types = session.scalars(select(Entity_Type)).all()
    return entity_types


def get_chat_history(chat_id: str) -> list[Chat_Message]:
    with Session(engine) as session:
        chat_history = session.scalars(select(Chat_Message).where(Chat_Message.chat_id == chat_id)).all()
    return chat_history


def get_chat_messages(user_id: str, document_id: str, event_name: str = None) -> list[Chat_Message]:
    """
    Get chat messages for a specific user and document, optionally filtered by event_name
    
    Args:
        user_id: The user ID
        document_id: The document ID
        event_name: Optional event name to filter messages (e.g., EventName.SUMMARY.value)
        
    Returns:
        A list of Chat_Message objects matching the criteria, ordered by created_at in descending order
    """
    with Session(engine) as session:
        # Start with base query for user and document
        query = select(Chat_Message).where(
            and_(
                Chat_Message.user_id == user_id,
                Chat_Message.chat_id == document_id
            )
        )
        
        # Add event_name filter if provided
        if event_name:
            query = query.where(Chat_Message.event_name == event_name)
            
        # Order by creation date (newest first)
        query = query.order_by(Chat_Message.created_at.desc())
            
        # Execute the query and get the results
        chat_messages = session.scalars(query).all()
        
    return chat_messages