import logging, sys
from datetime import datetime
from app.models import DocumentPublic, Entity, EntityPublic, Study_Project, Study_Project_Document_Link, Study_Task, Document, Study_Task_Citation, StudyProjectPublic, StudyTaskPublic, StudyTaskCitationPublic, TreeNode
from app.db_connector import get_engine
from app.gemini_client import GeminiClient
from app.gemini_prompts_models import AskQuestionPrompt

from sqlalchemy.orm import Session, joinedload
from sqlalchemy import (
    delete,
    select,
    text,
)

logging.basicConfig(
    stream=sys.stdout,
    format="%(asctime)s - %(message)s",
    level=logging.INFO,
    datefmt="%Y-%m-%d %H:%M:%S",
)


engine = get_engine()
genimi_client = GeminiClient()

async def create_study_project(name: str, objective: str, user_id: str, tasks_descriptions: list[str] = []) -> StudyProjectPublic:
    with Session(engine) as session:
        project = Study_Project(objective=objective, name=name, user_id=user_id)
        
        for task_description in tasks_descriptions:
            task = Study_Task(description=task_description)
            session.add(task)
            project.tasks.append(task)

        await project.generate_vector(genimi_client)
        session.add(project)
        session.commit()
        session.refresh(project)
    
        return project.to_public()

def get_study_project_by_id(project_id: str) -> StudyProjectPublic:
    with Session(engine) as session:
        project = session.scalar(select(Study_Project).options(joinedload(Study_Project.tasks)).where(Study_Project.id == project_id))
        return project.to_public()


def get_study_project_by_name(project_name: str) -> StudyProjectPublic:

    with Session(engine) as session:
        project = session.scalar(select(Study_Project).options(joinedload(Study_Project.tasks)).where(Study_Project.name == project_name))
        return project.to_public()

async def update_study_project(project: StudyProjectPublic) -> StudyProjectPublic:
    with Session(engine) as session:
        proj_exist = session.scalar(select(Study_Project).where(Study_Project.id == project.id))
        if proj_exist:
            if proj_exist.name != project.name:
                proj_exist.name = project.name
            if proj_exist.objective != project.objective:
                proj_exist.objective = project.objective
            
            await proj_exist.generate_vector(genimi_client)
        session.commit()
        session.refresh(proj_exist)
        return proj_exist.to_public()



    
def get_study_projects_public(user_id: str) -> list[StudyProjectPublic]:

    with Session(engine) as session:
        projects = session.scalars(select(Study_Project).where(Study_Project.user_id == user_id)).all()
        return [project.to_public() for project in projects]

def delete_study_project(project_id: int) -> bool:
    
    with Session(engine) as session:
        project = session.scalar(select(Study_Project).where(Study_Project.id == project_id))

        if project is None:
            return False
        
        tasks = session.scalars(select(Study_Task).where(Study_Task.project_id == project_id)).all()
        if project:
            session.delete(project)
    
            for task in tasks:
                session.execute(delete(Study_Task_Citation).where(Study_Task_Citation.task_id == task.id))
                session.delete(task)

        session.commit()
        return True

def create_study_task(project_id: int, description: str) -> StudyTaskPublic:
    with Session(engine) as session:
        project = session.scalar(select(Study_Project).where(Study_Project.id == project_id))
        if project:
            task = Study_Task(description=description, project_id=project_id)
            session.add(task)
            session.commit()
        return task.to_public()
    
def get_study_task(task_id: int) -> StudyTaskPublic:
    with Session(engine) as session:
        task = session.scalar(select(Study_Task).options(joinedload(Study_Task.citations)).where(Study_Task.id == task_id))
        return task.to_public()

def get_study_tasks(project_id: str) -> list[StudyTaskPublic]:
    with Session(engine) as session:
        tasks = session.scalars(select(Study_Task).options(joinedload(Study_Task.citations)).where(Study_Task.project_id == project_id)).unique().all()
        return [task.to_public() for task in tasks]

async def update_study_task(task_id: int, description: str) -> StudyTaskPublic:
    
    try:
        with Session(engine) as session:
            task = session.scalar(select(Study_Task).where(Study_Task.id == task_id))
            if task:
                task.description = description
                session.commit()
    except Exception as e:
        logging.error(f"Error while updating task. Error: {e}")
        return None
    
    try:
        docs = find_related_docs(task.project_id)
        await generate_task_response(task=task, documents=docs)
    except Exception as e:
        logging.error(f"Error while updating task. Error: {e}")
        return None
    
    return task.to_public()


def find_related_docs(project_id: str, cosine_distance_freshhold: float = 0.30) -> list[Document]:
    with Session(engine) as session:
        stmt = select(Study_Project.objective_tasks_vector).where(Study_Project.id == project_id).scalar_subquery()
        docs = session.scalars(select(Document).filter(Document.ai_summary_vector.cosine_distance(stmt) <= cosine_distance_freshhold)).all()
        linked_docs = session.scalars(select(Document).join(Study_Project_Document_Link).where(Study_Project_Document_Link.project_id == project_id)).all()
        
        ## Add the linked docs to the list of docs if they are not already in the list
        docs_ids = [doc.id for doc in docs]
        for linked in linked_docs:
            if linked.id not in docs_ids:
                docs.append(linked)


        return docs


async def generate_project_response(project_id: str, listener: any = None) -> None:
    
    with Session(engine) as session:
        project = session.scalar(select(Study_Project).options(joinedload(Study_Project.tasks)).where(Study_Project.id == project_id))
    
    documents = find_related_docs(project_id)
    if len(documents) > 0:

        logging.info(f"Generate project's tasks responses. Found {len(documents)} related documents for project_id: {project_id}")
        for task in project.tasks:
            await generate_task_response(task, documents)
            logging.info(f"Generated response for project_id: {project_id} task_id: {task.id}")

        if listener:
            listener(f"Generated responses completed for project_id: {project_id}") 
        logging.info(f"Generated responses completed for project_id: {project_id}")
    else:
        logging.info(f"No related documents found for project_id: {project_id}")

        ## Update the project status to NO_DOCS_FOUND
        with Session(engine) as session:
            project = session.scalar(select(Study_Project).where(Study_Project.id == project_id))
            project.status = "NO_DOCS_FOUND"
            session.commit()

        if listener:
            listener(f"No related documents found for project_id: {project_id}")


def get_project_entities(project_id: int) -> list[TreeNode]:
    
    document = find_related_docs(project_id)
    
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
        logging.error(f"Error while getting project entities. Error: {e}")
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
                                                        text_referance = doc_citation.get_verbatims())
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
    
def link_project_document(project_id: str, document_id: str) -> Study_Project_Document_Link:

    with Session(engine) as session:
        session.merge(Study_Project_Document_Link(project_id=project_id, document_id=document_id))
        session.commit()
        link = session.scalar(select(Study_Project_Document_Link)\
                              .where(Study_Project_Document_Link.project_id == project_id and Study_Project_Document_Link.document_id == document_id))

    return link

def unlink_project_document(project_id: str, document_id: str) -> bool:

    with Session(engine) as session:
        session.execute(delete(Study_Project_Document_Link)\
                        .where(Study_Project_Document_Link.project_id == project_id and Study_Project_Document_Link.document_id == document_id))
        session.commit()

    return True