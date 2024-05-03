import os
from app.db_connector import get_engine
from app.models import Bookmark, Document, Entity, SubTopic, SubTopic_Document_Link, SubTopic_Embedding_Link, Embedding, SubTopic_Entity_Link
from app.prompt_models import SubTopicPrompt
from app.transformers_util import get_util, get_model, generate_embeddings
import app.getters as getter
import app.icog_util as util
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



_entity_similarity_freshold = float(os.getenv("ENTITY_SIMILARITY_FRESHOLD"))
_clusters_similarity_freshold = float(os.getenv("CLUSTERS_SIMILARITY_THRESHOLD"))
_clusters_min_size = int(os.getenv("CLUSTERS_MIN_SIZE"))

_min_docs_for_subtopic = int(os.getenv("MIN_DOCS_FOR_SUBTOPIC", 2))
_min_ents_for_subtopic = int(os.getenv("MIN_ENTS_FOR_SUBTOPIC", 4)) 



 
def add_embedding_to_subtopic(embedding: Embedding, 
                             threshold: float = _entity_similarity_freshold) -> SubTopic | None:
    """Method that adds an embedding to a subtopic if it matches the cosine similarity threshold."""
    result = None
    with Session(engine) as session:
        ## Query to find the subtopic that matches the embedding
        stmt = text("""SELECT a.emb_id, a.subtopic_id, a.cosine_similarity
                    FROM (SELECT e.id AS emb_id, l.subtopic_id AS subtopic_id, MAX(1 - (e.vector <=> :vector)) AS cosine_similarity 
                            FROM embedding AS e
                            LEFT OUTER JOIN subtopic_embedding_link l ON l.embedding_id = e.id
                            WHERE e.user_id = :user_id
                            AND l.subtopic_id IS NULL
                            AND e.id != :needle_id
                            GROUP BY 1, 2) a
                    JOIN subtopic_embedding_link b ON a.subtopic_id = b.subtopic_id
                    WHERE a.cosine_similarity >= :threshold
                    ORDER BY a.cosine_similarity DESC
                    LIMIT :limit""")
        
        matches_subtopic = session.execute(stmt, {"vector": str(embedding.vector.tolist()), 
                                                 "user_id": embedding.user_id, 
                                                 "needle_id": embedding.id, 
                                                 "threshold": threshold, "limit": 1}).first()
        
        if (matches_subtopic is not None):
            subtopic = session.scalar(select(SubTopic).where(SubTopic.id == matches_subtopic.subtopic_id))
            session.add(embedding)
            session.refresh(embedding)
            subtopic.embeddings.append(embedding)
            session.commit()
            result = subtopic
        else:
            result = None
    
    return result

def generate_clusters(embeddings: list[Embedding], 
                      minimum_community_size: int = _clusters_min_size, 
                      cosine_similarity_threshold: float = _clusters_similarity_freshold):
    """Method that generates clusters of sentences using sentence transformer.

    Args:
        embeddings (list[Embedding]): List of embeddings to cluster.
        minimum_community_size (int, optional): _description_. Defaults to 3.
        cosine_similarity_threshold (float, optional): _description_. Defaults to 0.6.

    Returns:
        _type_: _description_
    """
    embs = [emb.vector for emb in embeddings]
    
    ## Perform community detection
    clusters = st_util.community_detection(embs, min_community_size=minimum_community_size, threshold=cosine_similarity_threshold)
    logging.info(f"Generated {len(clusters)} clusters from the {len(embs)} embedding.")
    return clusters


async def create_subtopic(user_id: str, embeddings: list[Embedding], cluster: list[int], 
                          min_num_of_doc: int = _min_docs_for_subtopic, 
                          min_num_of_entities: int = _min_ents_for_subtopic) -> SubTopic | None:
    """
    Create a subtopic based on the given parameters.

    Args:
        user_id (str): The ID of the user creating the subtopic.
        embeddings (list[Embedding]): The list of embeddings.
        cluster (list[int]): The list of indices representing the cluster.
        min_num_of_doc (int, optional): The minimum number of documents required for the subtopic. Defaults to _min_docs_for_subtopic.
        min_num_of_entities (int, optional): The minimum number of entities required for the subtopic. Defaults to _min_ents_for_subtopic.

    Returns:
        SubTopic | None: The created subtopic object, or None if the subtopic creation is skipped.

    """
    
    subtopic_embs = []
    for i in cluster:
        subtopic_embs.append(embeddings[i])

    doc_ids = set()
    ent_ids = set()
    for emb in subtopic_embs:
        if (emb.source_type == "entity"):
            ent_ids.add(emb.source_id)

        if (emb.source_type == "document"):
            doc_ids.add(emb.source_id)
    
    if (len(doc_ids) < min_num_of_doc and len(ent_ids) < min_num_of_entities):
        logging.info("Skipping subtopic creation. Not enough documents.")
        return None

    docs = getter.get_documents_by_ids(doc_ids)
    ents = getter.get_entities_by_ids(ent_ids)
    ## It possible to have entities that contribute to the subtopic but not their document. 
    ## In this case, we need to fetch the documents for the entities, this is done for usuability.
    ## When a user filter for a subtopic, we want to show the documents that are related to the entities.
    for ent in ents:
        ent_docs = getter.get_documents_by_entity_id(ent.id)
        docs.extend(ent_docs)

    ## Deduplicate the list of documents
    docs = util.deduplicate_objects_list(docs)

    ## Add entities to the subtopic
    subtopic = SubTopic(name="Temporarily")
    subtopic.entities = ents
    subtopic.documents = docs
    subtopic.embeddings = subtopic_embs

    ## Use LLM to generate a description for the subtopic
    try:
        if (subtopic.entities_agg_string() is None):
            logging.info("Skipping subtopic creation. No text to used to generate name.")
            return None
        
        answer = await client.generate(messages=SubTopicPrompt.get_messages(subtopic.entities_agg_string()), model=SubTopicPrompt)
    except ApiCallException as e:
        logging.error(f"Error in generating subtopic for {subtopic.name}: {e}")
            
    try:
        subtopic.name = answer.name
        subtopic.description = answer.description
        subtopic.key_words = ", ".join(answer.key_words)
        subtopic.vector =  generate_embeddings(f"{subtopic.name} {subtopic.description} {subtopic.key_words}")
        subtopic.user_id = user_id
    except Exception as e:
        logging.error(f"Error in processing subtopic {subtopic.name}: {e}")

    with Session(engine) as session:
        session.add_all(subtopic.entities)
        session.add_all(subtopic.documents)
        session.add_all(subtopic.embeddings)
        session.add(subtopic)
        session.commit()
        session.refresh(subtopic)
    
    return subtopic



def get_orphaned_embeddings(user_id: str) -> list[Embedding]:
    
    with Session(engine) as session:
        filter_stmt = select(Embedding)\
            .outerjoin(SubTopic_Embedding_Link, Embedding.id == SubTopic_Embedding_Link.embedding_id)\
            .where(
                and_(
                    Embedding.user_id == user_id, 
                    SubTopic_Embedding_Link.subtopic_id == None))
            
        embeddings = session.scalars(filter_stmt).unique().all()
    
    return embeddings


async def subtopics_factory(_user_id: str, 
                            _embeddings: list[Embedding] = None,
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

    if _embeddings is None:
        logging.info(f"Getting embedding for user_id {_user_id} without subtopic")
        _embeddings = get_orphaned_embeddings(user_id= _user_id)
    
    ## Search if embedding already match an existing subtopic
    ## If yes, add the embedding to the subtopic and refetch orphaned embeddings
    subtopics_match = []    
    for emb in _embeddings:
        subtopic = add_embedding_to_subtopic(embedding = emb)
        if subtopic:
            subtopics_match.append(emb)
    logging.info(f"Matched {len(subtopics_match)} embeddings to existing subtopics for user_id {_user_id}")


    ## Refetch orphaned embeddings
    _embeddings = None
    _embeddings = get_orphaned_embeddings(user_id= _user_id)

    ## Generate clusters for embeddings
    clusters = generate_clusters(embeddings = _embeddings, 
                                    minimum_community_size = minimum_community_size, 
                                    cosine_similarity_threshold = cosine_similarity_threshold)

    subtopics = []
    for cluster in clusters:
        ## Create subtopic for each cluster and save it to the database
        subtopic = await create_subtopic(user_id = _user_id, embeddings = _embeddings, cluster = cluster)
        if subtopic is not None:
            subtopics.append(subtopic)
    
    logging.info(f"Generated {len(subtopics)} subtopics for user_id {_user_id}")

    return subtopics

def delete_user_id_subtopics(user_id: str):
    with Session(engine) as session:
        subtopics = session.scalars(select(SubTopic).where(SubTopic.user_id == user_id)).unique().all()
        subtopics_ids = [subtopic.id for subtopic in subtopics]
        delete_ent_links = session.scalars(select(SubTopic_Entity_Link).filter(SubTopic_Entity_Link.subtopic_id.in_(subtopics_ids))).all()
        delete_docs_links = session.scalars(select(SubTopic_Document_Link).filter(SubTopic_Document_Link.subtopic_id.in_(subtopics_ids))).all()
        delete_emb_links = session.scalars(select(SubTopic_Embedding_Link).filter(SubTopic_Embedding_Link.subtopic_id.in_(subtopics_ids))).all()
        
        for link in delete_ent_links:
            session.delete(link)

        for link in delete_docs_links:
            session.delete(link)
        
        for link in delete_emb_links:
            session.delete(link)
        
        for subtopic in subtopics:
            session.delete(subtopic)
        
        session.commit()