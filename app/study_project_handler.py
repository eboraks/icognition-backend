import logging, sys
from app.models import Study_Project, Study_Task, Document, Study_Task_Citation
from app.db_connector import get_engine
from app.gemini_client import GeminiClient
from app.gemini_prompts_models import AskQuestionPrompt

from sqlalchemy.orm import Session, joinedload
from sqlalchemy import (
    delete,
    select,
)

logging.basicConfig(
    stream=sys.stdout,
    format="%(asctime)s - %(message)s",
    level=logging.INFO,
    datefmt="%Y-%m-%d %H:%M:%S",
)


engine = get_engine()
genimi_client = GeminiClient()

async def create_study_project(name: str, objective: str, user_id: str, tasks_descriptions: list[str] = []) -> Study_Project:
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
    
        return project

def get_study_project(project_id: int) -> Study_Project:
    with Session(engine) as session:
        project = session.scalar(select(Study_Project).options(joinedload(Study_Project.tasks)).where(Study_Project.id == project_id))
        return project


def get_study_project(project_name: str) -> Study_Project:

    with Session(engine) as session:
        project = session.scalar(select(Study_Project).options(joinedload(Study_Project.tasks)).where(Study_Project.name == project_name))
        return project

async def update_study_project(project_id: int, name: str, objective: str) -> Study_Project:
    with Session(engine) as session:
        project = session.scalar(Study_Project).where(Study_Project.id == project_id)
        if project:
            project.name = name
            project.objective = objective
            project.generate_vector(genimi_client)
        session.commit()
        session.refresh(project)
    return project


    
def get_study_projects(user_id: str) -> list[Study_Project]:

    with Session(engine) as session:
        projects = session.scalars(select(Study_Project).where(Study_Project.user_id == user_id)).all()
        return projects

def delete_study_project(project_id: int) -> None:
    with Session(engine) as session:
        project = session.scalar(select(Study_Project).where(Study_Project.id == project_id))
        tasks = session.scalars(select(Study_Task).where(Study_Task.project_id == project_id)).all()
        if project:
            session.delete(project)
    
            for task in tasks:
                session.delete(task)

        session.commit()

def create_study_task(project_id: int, description: str) -> Study_Task:
    with Session(engine) as session:
        project = session.scalar(Study_Project).where(Study_Project.id == project_id)
        if project:
            task = Study_Task(description=description, project_id=project_id)
            session.add(task)
            session.commit()
        return task
    
def get_study_task(task_id: int) -> Study_Task:
    with Session(engine) as session:
        task = session.scalar(select(Study_Task).options(joinedload(Study_Task.citations)).where(Study_Task.id == task_id))
        return task

def get_study_tasks(project_id: int) -> list[Study_Task]:
    with Session(engine) as session:
        tasks = session.scalars(select(Study_Task).options(joinedload(Study_Task.citations)).where(Study_Task.project_id == project_id)).all()
        return tasks


def find_related_docs(project_id: int) -> list[Document]:
    with Session(engine) as session:
        stmt = select(Study_Project.objective_tasks_vector).where(Study_Project.id == project_id).scalar_subquery()
        docs = session.scalars(select(Document).filter(Document.summary_vector.cosine_distance(stmt) <= 0.30)).all()
        return docs


async def generate_task_response(task: Study_Task, documents: list[Document]) -> Study_Task:


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
                
    
def insert_task_citations(task: Study_Task, response: AskQuestionPrompt) -> Study_Task:
    
    with Session(engine) as session:
        
        session.add(task)
        task.status = response.meta_answer
        task.explanation = response.answer

        if response.meta_answer == "SUCCESS":
            logging.info(f"Inserting citations for task_id: {task.id}. Number of citations: {len(response.documents_citations)}")
            ## Before inserting the citations, delete the existing citations for the task
            num_deleted_rows = delete_task_citations(task.id)
            logging.info(f"Deleted {num_deleted_rows} citations for task_id: {task.id}")

            for doc_citation in response.documents_citations:
                study_task_citation = Study_Task_Citation(task_id=task.id, 
                                                        document_id=doc_citation.document_id, 
                                                        citations= doc_citation.get_citations())
                session.add(study_task_citation)
                task.citations.append(study_task_citation)
        
        session.commit()
        session.refresh(task)
        return task


def delete_task_citations(task_id: int) -> int:
    with Session(engine) as session:
        results = session.execute(delete(Study_Task_Citation).where(Study_Task_Citation.task_id == task_id))
        session.commit()
        return results.rowcount