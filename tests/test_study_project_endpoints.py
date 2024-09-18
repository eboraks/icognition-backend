import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

@pytest.mark.asyncio
async def test_create_study_project():
    # Test create_study_project endpoint
    payload = {
        "name": "test_project",
        "objective": "test_objective",
        "user_id": "test_user",
        "tasks": [{"description": "description of the test task"}]
    }
    response = client.post("/study_project", json=payload)
    assert response.status_code == 200
    assert response.json()["name"] == "test_project"
    assert response.json()["objective"] == "test_objective"
    assert response.json()["user_id"] == "test_user"
    assert len(response.json()["tasks"]) > 0

    response = client.delete(f"/study_project/{response.json()['id']}")

def test_get_study_project():
    # Test get_study_project endpoint
    id = '920a386f-ee85-4630-bf82-518b3ef5ee38'
    response = client.get(f"/study_project/{id}")
    assert response.status_code == 200
    assert response.json()["id"] == id

def test_update_study_project():

    # Test create_study_project endpoint
    payload = {
        "name": "test_project",
        "objective": "test_objective",
        "user_id": "test_user",
        "tasks": [{"description": "description of the test task"}]
    }
    response = client.post("/study_project", json=payload)
    assert response.status_code == 200
    assert response.json()["name"] == "test_project"
    assert response.json()["objective"] == "test_objective"
    assert response.json()["user_id"] == "test_user"
    assert len(response.json()["tasks"]) > 0

    # Test update_study_project endpoint
    id = response.json()["id"]
    update_payload = {
        "name": "test_project",
        "objective": "updated_test_objective",
        "user_id": "test_user",
    }
    response = client.put(f"/study_project/{id}", json=update_payload)
    assert response.status_code == 200
    assert response.json()["objective"] == "updated_test_objective"

    response = client.delete(f"/study_project/{id}")



def test_delete_study_project():
    # Test delete_study_project endpoint
    id = '0d64caf4-dcf3-4a49-8dfe-770159480523'
    response = client.delete(f"/study_project/{id}")
    assert response.status_code == 204

def test_create_study_task():
    # Test create_study_task endpoint
    project_id = '2f2c29b9-2a58-4349-8fc6-672ef5e1df71'
    description = f"test_description for task {project_id}"
    payload = {
        "project_id": project_id,
        "description": description
    }
    response = client.post("/study_task", json=payload)
    assert response.status_code == 200
    assert response.json()["project_id"] == project_id
    assert response.json()["description"] == description

def test_get_study_tasks():
    # Test get_study_tasks endpoint
    project_id = '2f2c29b9-2a58-4349-8fc6-672ef5e1df71'
    response = client.get(f"/study_project_tasks/{project_id}")
    assert response.status_code == 200
    assert len(response.json()) > 0


def test_update_study_task():
    # Test create_study_task endpoint
    project_id = '2f2c29b9-2a58-4349-8fc6-672ef5e1df71'
    description = f"test_description for task {project_id}"
    payload = {
        "project_id": project_id,
        "description": description
    }
    response = client.post("/study_task", json=payload)
    task_id = response.json()["id"]
    assert response.status_code == 200
    assert response.json()["project_id"] == project_id
    assert response.json()["description"] == description

    # Test update_study_task endpoint
    update_payload = {
        "project_id": project_id,
        "description": "updated_description"
    }
    response = client.put(f"/study_task/{task_id}", json=update_payload)
    assert response.status_code == 200
    assert response.json()["description"] == "updated_description"

def test_study_related_entities():
    # Test get_study_related_entities endpoint
     # French Revolution project
    project_id = '60700311-8bfd-4cb0-a654-99d1ec0fdcdc'
                            
    response = client.get(f"/study_project/{project_id}/related_entities")
    assert response.status_code == 200
    assert len(response.json()) > 0
    for node in response.json():
        assert node["label"] is not None
        for entity in node["children"]:
            assert entity["label"] is not None
            assert entity["data"] is not None


def test_generate_study_project_summary():
    # Test generate_study_project_summary endpoint
    # French Revolution project
    project_id = '60700311-8bfd-4cb0-a654-99d1ec0fdcdc'
    
    response = client.get(f"/generate_study_project/{project_id}")
    assert response.status_code == 200
    

def test_create_project_document_link():
    # Test create_project_document_link endpoint
    
    # French Revolution project
    project_id = '60700311-8bfd-4cb0-a654-99d1ec0fdcdc'
    # Storming the bastille document
    document_id = '199260dd-92f7-467d-9631-669d81c0faa4'

    payload = {
        "project_id": project_id,
        "document_id": document_id
    }
    response = client.post("/project_document_link", json=payload)
    assert response.status_code == 200
    assert response.json()["project_id"] == project_id
    assert response.json()["document_id"] == document_id


def test_delete_project_document_link():
    # Test delete_project_document_link endpoint
    
    # French Revolution project
    project_id = '60700311-8bfd-4cb0-a654-99d1ec0fdcdc'
    # Storming the bastille document
    document_id = '199260dd-92f7-467d-9631-669d81c0faa4'
    
    payload = {
        "project_id": project_id,
        "document_id": document_id
    }
    response = client.post("/project_document_unlink", json=payload)
    assert response.status_code == 200
    
def test_get_user_projects():
    # Test get_users_projects endpoint
    user_id = "test_user_id_123"
    
    for i in range(3):
        payload = {
            "name": f"test_project_{i}",
            "objective": f"test_objective_{i}",
            "user_id": user_id,
            "tasks": [{"description": f"description of the test task {i}"}]
        }
        response = client.post("/study_project", json=payload)
      
    response = client.get(f"/study_projects/{user_id}")
    assert response.status_code == 200
    assert len(response.json()) > 0
    

## Test for /study_project/{id}/related_documents
def test_study_related_documents():
    # Test get_study_related_documents endpoint
    # French Revolution project
    project_id = '60700311-8bfd-4cb0-a654-99d1ec0fdcdc'
    # Storming the bastille document
    document_id = '199260dd-92f7-467d-9631-669d81c0faa4'
                            
    response = client.get(f"/study_project/{project_id}/related_documents")
    assert response.status_code == 200
    assert len(response.json()) > 0
    doc_ids = []
    for doc in response.json():
        assert doc["title"] is not None
        assert doc["id"] is not None
        doc_ids.append(doc["id"])

    assert document_id in doc_ids
        