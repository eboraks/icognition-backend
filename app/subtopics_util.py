from app.db_connector import get_engine
from app.models import Entity, SubTopic, SubTopic_Entity_Link
from app.prompt_models import SubTopicPrompt
from app.transformers_util import get_util, get_model
from sqlalchemy.orm import Session
from sqlalchemy import (
    select,
    func,
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


def get_entities() -> list[Entity]:
    with Session(engine) as session:
        entities = session.execute(
            select(Entity)
            .outerjoin(SubTopic_Entity_Link, SubTopic_Entity_Link.entity_id == Entity.id)
            .group_by(Entity.id)
            .having(func.count(SubTopic_Entity_Link.subtopic_name) == 0)
        ).scalars().unique().all()
    
    return entities

def get_entities_in_sentences(entities: list[Entity]) -> list[str]:
    sentences = []
    for entity in entities:
        text = f"{entity.name} ({entity.type}): {entity.description}"
        sentences.append(text)
    return sentences


def generate_clusters(sentences: list[str], minimum_community_size: int = 3, cosine_similarity_threshold: float = 0.6):
    ## Generate embeddings for the sentences
    sentences_embedding = st_model.encode(sentences, convert_to_tensor=True)
    
    ## Perform community detection
    clusters = st_util.community_detection(sentences_embedding, min_community_size=minimum_community_size, threshold=cosine_similarity_threshold)

    return clusters

def search_subtopics(subtopic: SubTopic, cosine_similarity_threshold: float = 0.6):
    """ Search for subtopics similar to the given subtopic."""
    with Session(engine) as session:
        subtopics = session.execute(
            select(SubTopic)
            .filter(SubTopic.embedding.cosine_distance(subtopic.embedding) > cosine_similarity_threshold)
        ).scalars().unique().all()
    
    return subtopics


async def create_subtopic(cluster: list[int], entities: list[Entity]) -> SubTopic:
    """Method that create subtopic from the given cluster of entities.

    Args:
        cluster (list[int]): sentence transformer cluster
        entities (list[Entity]): list of Entity objects

    Returns:
        SubTopic: Subtopic object
    """
    
    ## Add entities to the subtopic
    subtopic = SubTopic(name="Temporarily")
    for i in cluster:
        subtopic.entities.append(entities[i])
    
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
    except Exception as e:
        logging.error(f"Error in processing subtopic {subtopic.name}: {e}")

    return subtopic




async def generate_subtopics(minimum_community_size: int = 3, cosine_similarity_threshold: float = 0.6):

    entities = get_entities()
    sentences = get_entities_in_sentences(entities)

    clusters = generate_clusters(sentences, minimum_community_size=minimum_community_size, cosine_similarity_threshold=cosine_similarity_threshold)

    subtopics = []
    for ci, cluster in enumerate(clusters):
        subtopic = await create_subtopic(cluster, entities)
        
        existing_subtopics = search_subtopics(subtopic, cosine_similarity_threshold=cosine_similarity_threshold)
        if(len(existing_subtopics) > 0):
            for existing_subtopic in existing_subtopics:
                logging.info(f"Found similar subtopics for {existing_subtopic.name} with id {existing_subtopic.id}")
        else:
            subtopics.append(subtopic)
    
    try:
        with Session(engine) as session:
            logging.info(f"Saving subtopics in database. Count: {len(subtopics)}")
            session.add_all(subtopics)
            session.commit()
    except Exception as e:
        logging.error(f"Error in saving subtopics: {e}")
        raise e




