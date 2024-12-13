from scipy.spatial import distance
from app.log import get_logger
from datetime import datetime
from app.models import DocumentPublic, Entity, RagAnswerPublic, SearchResults, Study_Collection, Study_Collection_Document_Link, Study_Task, Document, Study_Task_Citation, StudyCollectionPublic, StudyTaskPublic, StudyTaskCitationPublic, TreeNode
from app.db_connector import get_engine
from app.gemini_client import GeminiClient
from app.gemini_prompts_models import AskQuestionPrompt
from app.search_handler import SearchHandler
import app.getters as  getter

from sqlalchemy.orm import Session, joinedload
from sqlalchemy import (
    delete,
    select,
    text,
)

logging = get_logger()


engine = get_engine()
genimi_client = GeminiClient()

async def create_study_collection(name: str, objective: str, user_id: str, tasks: list[str] = []) -> StudyCollectionPublic:
    with Session(engine) as session:
        collection = Study_Collection(objective=objective, name=name, user_id=user_id)
        
        for task in tasks:
            task = Study_Task(description=task.description)
            session.add(task)
            collection.tasks.append(task)

        await collection.generate_vector(genimi_client)
        session.add(collection)
        session.commit()
        session.refresh(collection)
    
        return collection.to_public()

def get_study_collection_by_id(collection_id: str) -> StudyCollectionPublic:
    with Session(engine) as session:
        collection = session.scalar(select(Study_Collection).options(joinedload(Study_Collection.tasks)).where(Study_Collection.id == collection_id))
        related_docs = find_related_docs_public(collection_id)
        public = collection.to_public()
        public.related_docs = related_docs

        for task in public.tasks:
            for citation in task.citations:
                doc = getter.get_document_by_id(citation.document_id)
                citation.document_title = doc.title
                

        return public


def get_study_collection_by_name(collection_name: str) -> StudyCollectionPublic:

    with Session(engine) as session:
        collection = session.scalar(select(Study_Collection).options(joinedload(Study_Collection.tasks)).where(Study_Collection.name == collection_name))
        return collection.to_public()

async def update_study_collection(collection: StudyCollectionPublic) -> StudyCollectionPublic:
    with Session(engine) as session:
        proj_exist = session.scalar(select(Study_Collection).where(Study_Collection.id == collection.id))
        if proj_exist:
            if proj_exist.name != collection.name:
                proj_exist.name = collection.name
            if proj_exist.objective != collection.objective:
                proj_exist.objective = collection.objective
            
            await proj_exist.generate_vector(genimi_client)
        session.commit()
        session.refresh(proj_exist)
        return proj_exist.to_public()



    
def get_study_collections_public(user_id: str) -> list[StudyCollectionPublic]:

    with Session(engine) as session:
        collections = session.scalars(select(Study_Collection).where(Study_Collection.user_id == user_id)).all()
        return [collection.to_public() for collection in collections]

def delete_study_collection(collection_id: int) -> bool:
    
    with Session(engine) as session:
        collection = session.scalar(select(Study_Collection).where(Study_Collection.id == collection_id))

        if collection is None:
            return False
        
        tasks = session.scalars(select(Study_Task).where(Study_Task.collection_id == collection_id)).all()
        if collection:
            session.delete(collection)
    
            for task in tasks:
                session.execute(delete(Study_Task_Citation).where(Study_Task_Citation.task_id == task.id))
                session.delete(task)

        session.commit()
        return True

def create_study_task(collection_id: int, description: str) -> StudyTaskPublic:
    with Session(engine) as session:
        collection = session.scalar(select(Study_Collection).where(Study_Collection.id == collection_id))
        if collection:
            task = Study_Task(description=description, collection_id=collection_id)
            session.add(task)
            session.commit()
        return task.to_public()
    
def get_study_task(task_id: int) -> StudyTaskPublic:
    with Session(engine) as session:
        task = session.scalar(select(Study_Task).options(joinedload(Study_Task.citations)).where(Study_Task.id == task_id))
        return task.to_public()

def get_study_tasks(collection_id: str) -> list[StudyTaskPublic]:
    with Session(engine) as session:
        tasks = session.scalars(select(Study_Task).options(joinedload(Study_Task.citations)).where(Study_Task.collection_id == collection_id)).unique().all()
        return [task.to_public() for task in tasks]

async def update_study_task(task: StudyTaskPublic) -> StudyTaskPublic:
    
    try:
        with Session(engine) as session:
            _task = session.scalar(select(Study_Task).where(Study_Task.id == task.id))
            if _task:
                _task.description = task.description
                session.commit()
                session.refresh(_task)
            else:
                logging.warning(f"Task with id: {task.id} not found")
                return None
    except Exception as e:
        logging.error(f"Error while updating task. Error: {e}")
        return None
    
    try:
        docs = find_related_docs(_task.collection_id)
        if len(docs) == 0:
            logging.warning(f"No related documents found for collection_id: {_task.collection_id}")
            with Session(engine) as session:
                session.add(_task)
                return _task.to_public()
        
        return await generate_task_response(task=_task, documents=docs)
    except Exception as e:
        logging.error(f"Error while updating task. Error: {e}")
        return None



def find_related_docs(collection_id: str, cosine_distance_freshhold: float = 0.30) -> list[Document]:
    with Session(engine) as session:
        stmt = select(Study_Collection.objective_tasks_vector).where(Study_Collection.id == collection_id).scalar_subquery()
        docs = session.scalars(select(Document).filter(Document.ai_summary_vector.cosine_distance(stmt) <= cosine_distance_freshhold)).all()
        linked_docs = session.scalars(select(Document).join(Study_Collection_Document_Link).where(Study_Collection_Document_Link.collection_id == collection_id)).all()
        
        ## Add the linked docs to the list of docs if they are not already in the list
        docs_ids = [doc.id for doc in docs]
        for linked in linked_docs:
            if linked.id not in docs_ids:
                docs.append(linked)

        return docs

def find_related_docs_public(collection_id: str, cosine_distance_freshhold: float = 0.30) -> list[DocumentPublic]:
    """This is a wrapper function that returns the list of related documents for a collection in a public format

    Args:
        collection_id (str): _description_
        cosine_distance_freshhold (float, optional): _description_. Defaults to 0.30.

    Returns:
        list[DocumentPublic]: _description_
    """
    docs = find_related_docs(collection_id, cosine_distance_freshhold)
    docs_public = calculate_cosine_dist_collection_docs(collection_id, docs)
    return docs_public


def get_list_of_candidates_docs(collection_id: str, max_docs = 10) -> list[DocumentPublic]:

    related_docs = find_related_docs(collection_id)
    related_docs_ids = [doc.id for doc in related_docs]

    ## Get the list of all documents that are not linked to the collection
    with Session(engine) as session:
        
        stmt = select(Document).filter(Document.id.notin_(related_docs_ids)).limit(max_docs)
        docs = session.scalars(stmt).all()
        docs_public = [doc.to_public() for doc in docs]

    return docs_public


def calculate_cosine_dist_collection_docs(collection_id: str, documents: list[Document]) -> list[DocumentPublic]:
    

    with Session(engine) as session:
        collection_vector = session.scalar(select(Study_Collection.objective_tasks_vector).where(Study_Collection.id == collection_id))

        docs_public = []
        for doc in documents:
            session.add(doc)
            doc_vector = doc.ai_summary_vector
            try:
                dis = 1 - distance.cosine(collection_vector, doc_vector)
            except Exception as e:
                logging.error(f"Error while calculating cosine distance. Error: {e}")
                dis = 0.0
            pub = doc.to_public(cosine_similarity=dis) 
            docs_public.append(pub)

    return docs_public



async def ask_question(collection_id: str, question: str) -> RagAnswerPublic:

    searcher = SearchHandler()
    docs = find_related_docs(collection_id)

    answer = await searcher.rag_workflow(docs=docs, search_term=question)
    return answer


def get_collection(collection_id: str) -> Study_Collection:
    with Session(engine) as session:
        collection = session.scalar(select(Study_Collection).options(joinedload(Study_Collection.tasks)).where(Study_Collection.id == collection_id))
        return collection


async def generate_collection_response(collection_id: str, listener: any = None) -> None:
    
    collection = get_collection(collection_id)
    
    documents = find_related_docs(collection_id)
    if len(documents) > 0:

        logging.info(f"Generate collection's tasks responses. Found {len(documents)} related documents for collection_id: {collection_id}")
        for task in collection.tasks:
            await generate_task_response(task, documents)
            logging.info(f"Generated response for collection_id: {collection_id} task_id: {task.id}")


        if listener:
            listener(f"Generated responses completed for collection_id: {collection_id}") 
        logging.info(f"Generated responses completed for collection_id: {collection_id}")
    else:
        logging.info(f"No related documents found for collection_id: {collection_id}")

        ## Update the collection status to NO_DOCS_FOUND
        with Session(engine) as session:
            collection = session.scalar(select(Study_Collection).where(Study_Collection.id == collection_id))
            collection.status = "NO_DOCS_FOUND"
            session.commit()

        if listener:
            listener(f"No related documents found for collection_id: {collection_id}")


def get_collection_entities(collection_id: int) -> list[TreeNode]:
    
    document = find_related_docs(collection_id)
    
    if len(document) == 0:
        return []
    
    docs_ids_str = ', '.join([f"'{doc.id}'" for doc in document])
    
    results = []
    stmt = text(f"""
        SELECT a.type, a.ents_count, a.docs_count, a.ents_names, a.docs_ids 
        FROM (SELECT e.type, 
            count(distinct e.name) as ents_count, 
            json_agg(distinct e.name) as ents_names,
            count(distinct l.document_id) as docs_count,
            json_agg(distinct l.document_id) as docs_ids
        FROM public.entity e
        JOIN public.document_entity_link l ON l.entity_id = e.id
        JOIN public.source s ON s.document_id = l.document_id
            WHERE l.document_id IN ({docs_ids_str})
        GROUP BY 1) a
        """)
    try:

        with Session(engine) as session:

            types = session.execute(stmt).fetchall()

            for k, t in enumerate(types):
                top_node = TreeNode(label=t.type.title(), key=str(k), doc_count=t.docs_count, doc_ids=t.docs_ids, children=[])
                for e_name in t.ents_names:
                    ent_node = session.scalar(select(Entity).where(Entity.name == e_name)).to_node()
                    if ent_node.doc_count > 0:
                        top_node.children.append(ent_node)
                # Only add the top node if it has children
                
                if len(top_node.children) > 0:
                    results.append(top_node)
    except Exception as e:
        logging.error(f"Error while getting collection entities. Error: {e}")
    finally:                
        return results



async def generate_task_response(task: Study_Task, documents: list[Document]) -> StudyTaskPublic:


    #client = GeminiClient(_model_name = GeminiClient.pro_model_name())
    client = GeminiClient()
    try:
        response = await client.generate_response(AskQuestionPrompt.build_prompt(question= task.description, docs = documents),AskQuestionPrompt)
        
        if response:
            logging.info(f"Generated response for task_id: {task.id}")
            return insert_task_citations(task, response)
        else:
            raise Exception(f"Failed to generate response for task_id: {task.id}")

    except Exception as e:
        # Handle the exception here
        raise Exception(f"Error while generate response for task_id: {task.id}. Error: {e}")
                
    
def insert_task_citations(task_public: StudyTaskPublic, response: AskQuestionPrompt) -> StudyTaskPublic:
    
    with Session(engine) as session:
        
        task = session.scalar(select(Study_Task).where(Study_Task.id == task_public.id))
        task.status = response.meta_answer
        task.ai_explanation = response.answer
        task.updated_at = datetime.now()

        if response.meta_answer == "SUCCESS":
            logging.info(f"Inserting citations for task_id: {task.id}. Number of citations: {len(response.documents_citations)}")
            ## Before inserting the citations, delete the existing citations for the task
            num_deleted_rows = delete_task_citations(task.id)
            logging.info(f"Deleted {num_deleted_rows} citations for task_id: {task.id}")

            for doc_citation in response.documents_citations:
                study_task_citation = Study_Task_Citation(task_id=task.id, 
                                                        document_id=doc_citation.document_id, 
                                                        text_reference = doc_citation.get_verbatims())
                session.add(study_task_citation)
                task.citations.append(study_task_citation)
        
        session.commit()
        session.refresh(task)
        return task.to_public()


def delete_task_citations(task_id: int) -> int:
    with Session(engine) as session:
        results = session.execute(delete(Study_Task_Citation).where(Study_Task_Citation.task_id == task_id))
        session.commit()
        return results.rowcount
    
def link_collection_document(collection_id: str, document_id: str) -> Study_Collection_Document_Link:

    with Session(engine) as session:
        session.merge(Study_Collection_Document_Link(collection_id=collection_id, document_id=document_id))
        session.commit()
        link = session.scalar(select(Study_Collection_Document_Link)\
                              .where(Study_Collection_Document_Link.collection_id == collection_id and Study_Collection_Document_Link.document_id == document_id))

    return link

def unlink_collection_document(collection_id: str, document_id: str) -> bool:

    with Session(engine) as session:
        session.execute(delete(Study_Collection_Document_Link)\
                        .where(Study_Collection_Document_Link.collection_id == collection_id and Study_Collection_Document_Link.document_id == document_id))
        session.commit()

    return True


def get_collection_status(collection_id: str) -> str:
    
    with Session(engine) as session:
        collection = session.scalar(select(Study_Collection).options(joinedload(Study_Collection.tasks)).where(Study_Collection.id == collection_id))

    number_of_tasks = len(collection.tasks)
    number_of_tasks_with_response = len([task for task in collection.tasks if task.status == "SUCCESS"])
    number_of_tasks_with_ai_response = len([task for task in collection.tasks if task.ai_explanation is not None])

    return {"total_tasks": number_of_tasks, 
            "tasks_with_response": number_of_tasks_with_response, 
            "tasks_with_ai_response": number_of_tasks_with_ai_response, 
            "percentage_tasks_with_response": (number_of_tasks_with_response/number_of_tasks)*100,}