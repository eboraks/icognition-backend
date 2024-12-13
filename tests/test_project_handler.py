import pytest
import study_collection_handler as handler
import app.getters as getter
from app.gemini_client import GeminiClient
from app.app_logic import update_document 

genimi_client = GeminiClient()

@pytest.mark.asyncio
async def test_create_study_collection():

    existing_collections = handler.get_study_collections_public("test_collection")

    for collection in existing_collections:
        handler.delete_study_collection(collection.id)

    collection = await handler.create_study_collection(name="test_collection", objective="test_objective", user_id = "test_user", tasks_descriptions=["task1", "task2"])

    collection = handler.get_study_collection_by_id(collection.id)
    assert collection.name == "test_collection"
    assert collection.objective == "test_objective"
    assert collection.user_id == "test_user"
    assert len(collection.tasks) > 0

@pytest.mark.asyncio
async def test_create_frech_revolution_collection(): 

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

    collection = await handler.create_study_collection(name=name, objective=objective, user_id = "HqAXhad3jrUWmPibnMf1xZczNIq2", tasks_descriptions=tasks)

    collection = handler.get_study_collection_by_id(collection.id)

    assert collection.name == name
    assert collection.objective == objective
    assert collection.user_id == "HqAXhad3jrUWmPibnMf1xZczNIq2"
    assert len(collection.tasks) == len(tasks)


@pytest.mark.asyncio
async def test_generate_docs_vector():
    docs = getter.get_documents()

    for doc in docs:
        if doc.ai_summary_vector is None:
            doc.ai_summary_vector = await doc.generate_vector(geminiClient=genimi_client)
            update_document(doc)


    docs = getter.get_documents()
    for doc in docs:
        if doc.ai_is_about and doc.ai_bullet_points:
            assert doc.ai_summary_vector is not None

@pytest.mark.asyncio
async def test_find_related_docs():
    
    name = "French Revolution Highschool paper"
    collection = handler.get_study_collection_by_name(name)
    documents = handler.find_related_docs(collection.id)
    assert len(documents) > 3

    for doc in documents:
        assert doc.title is not None

@pytest.mark.asyncio
async def test_generate_task_response():
    
    name = "French Revolution Highschool paper"
    collection = handler.get_study_collection_by_name(name)
    
    documents = handler.find_related_docs(collection.id)
    
    for task in collection.tasks:
        response = await handler.generate_task_response(task, documents)
        assert response is not None