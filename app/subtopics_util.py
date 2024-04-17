import os
from app.db_connector import get_engine
from app.models import Bookmark, Document, Entity, SubTopic, SubTopic_Entity_Link
from app.prompt_models import SubTopicPrompt
from app.transformers_util import get_util, get_model
from sqlalchemy.orm import Session
from sqlalchemy import (
    and_,
    select,
    func,
    text,
)
from app.together_api_client import ApiCallException, TogetherMixtralClient
import logging, sys

logging.basicConfig(
    stream=sys.stdout,
    format="%(asctime)s - %(message)s",
    level=logging.INFO,
    datefmt="%Y-%m-%d %H:%M:%S", 
)


client = TogetherMixtralClient()

engine = get_engine()
st_util = get_util()
st_model = get_model()



_entity_similarity_freshold = float(os.environ["ENTITY_SIMILARITY_FRESHOLD"])
_clusters_similarity_freshold = float(os.environ["CLUSTERS_SIMILARITY_THRESHOLD"])
_clusters_min_size = int(os.environ["CLUSTERS_MIN_SIZE"])

def get_entities(user_id: str) -> list[Entity]:
    with Session(engine) as session:
        filter_stmt = select(Entity.id).join(Document, Document.id == Entity.document_id)\
            .join(Bookmark, Document.id == Bookmark.document_id)\
            .where(and_(
                Bookmark.user_id == user_id,
                Entity.embedding != None
            ))
        
        
        stmt = select(Entity).outerjoin(SubTopic_Entity_Link, Entity.id == SubTopic_Entity_Link.entity_id)\
            .where(and_(
                SubTopic_Entity_Link.subtopic_id == None,
                Entity.id.in_(session.execute(filter_stmt).scalars().unique().all())
                ))
        
        entities = session.scalars(stmt).unique().all() 
        
    return entities

def get_subtopics(user_id: str) -> list[SubTopic]:
    """Method that retrieves subtopics from the database.

    Args:
        user_id (str): The user ID.

    Returns:
        list[SubTopic]: A list of subtopics.
    """
    subtopics = []
    with Session(engine) as session:
        stmt = select(SubTopic).where(SubTopic.user_id == user_id)
        subtopics = session.scalars(stmt).unique().all()
    return subtopics

def add_entities_to_subtopic(subtopics: list[SubTopic], 
                             entities: list[Entity], 
                             cosine_similarity_threshold: float = _entity_similarity_freshold) -> list[Entity]:
    """Method that adds entities to subtopics based on cosine similarity.

    Args:
        subtopics (list[SubTopic]): _description_
        entities (list[Entity]): _description_
        cosine_similarity_threshold (float, optional): _description_. Defaults to 0.58.

    Returns:
        list[Entity]: return entities that didn't matched with any subtopic
    """

    session = Session(engine)
    tracker =[]
    for entity in entities:
        for subtopic in subtopics:
            distance = st_util.cos_sim(subtopic.embedding, entity.embedding)
            if (distance >= cosine_similarity_threshold):
                logging.info(f"Adding entity {entity.id} - {entity.name} to {subtopic.name}. Cosine similarity: {distance}")
                session.add(entity)
                session.add(subtopic)
                subtopic.entities.append(entity)
                tracker.append(entity)
                session.flush()
                break
        
    session.commit()
    session.close()

    ## Return entities that didn't matched with any subtopic
    for entity in tracker:
        entities.remove(entity)
    return entities



def get_entities_in_sentences(entities: list[Entity]) -> list[str]:
    """Method that generates sentences from the entities.
    Args:
        entities (list[Entity]): List of Entity objects.

    Returns:
        list[str]: List of sentences generated from the entities.
    """
    sentences = []
    for entity in entities:
        text = f"{entity.name} ({entity.type}): {entity.description}"
        sentences.append(text)
    return sentences


def generate_clusters(entities: list[Entity], 
                      minimum_community_size: int = _clusters_min_size, 
                      cosine_similarity_threshold: float = _clusters_similarity_freshold):
    """Method that generates clusters of sentences using sentence transformer.

    Args:
        sentences (list[str]): _description_
        minimum_community_size (int, optional): _description_. Defaults to 3.
        cosine_similarity_threshold (float, optional): _description_. Defaults to 0.6.

    Returns:
        _type_: _description_
    """
    sentences = get_entities_in_sentences(entities)
    logging.info(f"Generating clusters for {len(sentences)} entities")
    ## Generate embeddings for the sentences
    sentences_embedding = st_model.encode(sentences)
    
    ## Perform community detection
    clusters = st_util.community_detection(sentences_embedding, min_community_size=minimum_community_size, threshold=cosine_similarity_threshold)
    logging.info(f"Generated {len(clusters)} clusters from the {len(sentences)} entities.")
    return clusters


async def create_subtopic(user_id: str, entities: list[Entity], cluster: list[int]) -> SubTopic:
    """Method that create subtopic from the given cluster of entities.

    Args:
        user_id (str): user id
        cluster (list[int]): sentence transformer cluster
        entities (list[Entity]): list of Entity objects

    Returns:
        SubTopic: Subtopic object
    """
    
    ## Add entities to the subtopic
    subtopic = SubTopic(name="Temporarily")
    
    subtopic_entities = []
    for i in cluster:
        subtopic_entities.append(entities[i])

    subtopic.entities = subtopic_entities
        
    ## Use LLM to generate a description for the subtopic
    try:
        answer = await client.generate(body_text=SubTopicPrompt.get_messages(subtopic.entities_agg_string()), model=SubTopicPrompt)
    except ApiCallException as e:
        logging.error(f"Error in generating subtopic for {subtopic.name}: {e}")
            
    try: 
        key_words = ", ".join(answer.key_words)
        subtopic_str = f"{answer.name} - {answer.description} - {key_words}"
        subtopic_emb = st_model.encode(subtopic_str, convert_to_tensor=True)

        subtopic.name = answer.name
        subtopic.description = answer.description
        subtopic.key_words = key_words
        subtopic.embedding = subtopic_emb
        subtopic.user_id = user_id
    except Exception as e:
        logging.error(f"Error in processing subtopic {subtopic.name}: {e}")

    with Session(engine) as session:
        session.add_all(subtopic.entities)
        session.add(subtopic)
        session.commit()
        session.refresh(subtopic)
    
    return subtopic    




async def subtopics_factory(user_id: str, 
                            entities: list[Entity] = None,
                            clusters: list[list[int]] = None, 
                            minimum_community_size: int = _clusters_min_size, 
                            cosine_similarity_threshold: float = _clusters_similarity_freshold) -> list[SubTopic]:
    """Method that generates subtopics from the given entities.
    
    Args:
        user_id (str): The ID of the user.
        clusters (Optional): The clusters to use for generating subtopics. If not provided, clusters will be generated.
        entities (Optional): The list of entities to use for generating subtopics. If not provided, entities will be fetched based on the user ID.
        minimum_community_size (int): The minimum size of a community to be considered as a cluster. Default is 3.
        cosine_similarity_threshold (float): The threshold value for cosine similarity. Default is 0.6.
    
    Returns:
        list[SubTopic]: The list of generated subtopics.
    """

    if entities is None:
        logging.info(f"Entities or Clusters are None, generating entities for user_id {user_id}")
        entities = get_entities(user_id=user_id)
    
    ## Search if entities already match an existing subtopic
    subtopics = get_subtopics(user_id=user_id)    
    if(len(subtopics) > 0):
        entities = add_entities_to_subtopic(subtopics, entities)
        
    if clusters is None:
        clusters = generate_clusters(entities = entities, 
                                     minimum_community_size = minimum_community_size, 
                                     cosine_similarity_threshold = cosine_similarity_threshold)

    subtopics = []
    for cluster in clusters:
        ## Create subtopic for each cluster and save it to the database
        subtopic = await create_subtopic(user_id = user_id, entities = entities, cluster = cluster)
        subtopics.append(subtopic)
    
    return subtopics

def delete_user_id_subtopics(user_id: str):
    with Session(engine) as session:
        subtopics = session.scalars(select(SubTopic).where(SubTopic.user_id == user_id)).unique().all()
        subtopics_ids = [subtopic.id for subtopic in subtopics]
        delete_links = session.scalars(select(SubTopic_Entity_Link).filter(SubTopic_Entity_Link.subtopic_id.in_(subtopics_ids))).all()
        
        for link in delete_links:
            session.delete(link)
        
        for subtopic in subtopics:
            session.delete(subtopic)
        
        session.commit()