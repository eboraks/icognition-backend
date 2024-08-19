import pytest
import app.study_project_handler as handler
import app.getters as getter
from app.gemini_client import GeminiClient
from app.app_logic import update_document 

genimi_client = GeminiClient()

@pytest.mark.asyncio
async def test_create_study_project():

    existing_projects = handler.get_study_projects("test_project")

    for project in existing_projects:
        handler.delete_study_project(project.id)

    project = await handler.create_study_project(name="test_project", objective="test_objective", user_id = "test_user", tasks_descriptions=["task1", "task2"])

    project = await handler.get_study_project(project.id)
    assert project.name == "test_project"
    assert project.objective == "test_objective"
    assert project.user_id == "test_user"
    assert project.objective_tasks_vector is not None
    assert len(project.tasks) > 0

@pytest.mark.asyncio
async def test_create_frech_revolution_project(): 

    name = "French Revolution Highschool paper"
    
    objective = """I am writing comprehensive report on the French Revolution.
                This report should provide a clear and detailed overview of this pivotal historical event. 
                I need help conducting thorough research to support my analysis and arguments."""

    tasks = [
        "What were the primary causes of the French Revolution?",
        "List key events in the Revolution and what they signified",
        "List the major figures in the Revolution and their roles",
        "How did the Estates-General contribute to the outbreak of the Revolution?",
        "What role did Enlightenment ideas play in shaping the Revolution?",
        "How did the storming of the Bastille mark a turning point in the Revolution?",
        "What were the major goals and achievements of the National Assembly?",
        "How did the Reign of Terror impact the course of the Revolution?",
        "What were the social and economic consequences of the Revolution?",
        "How did the French Revolution influence the development of nationalism?",
        "What were the lasting legacies of the French Revolution?",
        "How do historians interpret and debate the significance of the French Revolution today?"
    ]

    project = await handler.create_study_project(name=name, objective=objective, user_id = "HqAXhad3jrUWmPibnMf1xZczNIq2", tasks_descriptions=tasks)

    project = await handler.get_study_project(project.id)

    assert project.name == name
    assert project.objective == objective
    assert project.user_id == "HqAXhad3jrUWmPibnMf1xZczNIq2"
    assert project.objective_tasks_vector is not None
    assert len(project.tasks) == len(tasks)


@pytest.mark.asyncio
async def test_generate_docs_vector():
    docs = getter.get_documents()

    for doc in docs:
        if doc.summary_vector is None:
            doc.summary_vector = await doc.generate_vector(geminiClient=genimi_client)
            update_document(doc)


    docs = getter.get_documents()
    for doc in docs:
        if doc.is_about and doc.summary_bullet_points:
            assert doc.summary_vector is not None

@pytest.mark.asyncio
async def test_find_related_docs():
    
    name = "French Revolution Highschool paper"
    project = handler.get_study_project(name)
    documents = handler.find_related_docs(project.id)
    assert len(documents) > 3

    for doc in documents:
        assert doc.title is not None

@pytest.mark.asyncio
async def test_generate_task_response():
    
    name = "French Revolution Highschool paper"
    project = handler.get_study_project(name)
    
    documents = handler.find_related_docs(project.id)
    
    for task in project.tasks:
        response = await handler.generate_task_response(task, documents)
        assert response is not None