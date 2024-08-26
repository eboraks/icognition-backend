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
    id = 29
    response = client.get(f"/study_project/{id}")
    assert response.status_code == 200
    assert response.json()["id"] == id

def test_delete_study_project():
    # Test delete_study_project endpoint
    id = 30
    response = client.delete(f"/study_project/{id}")
    assert response.status_code == 204

def test_create_study_task():
    # Test create_study_task endpoint
    project_id = 19
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
    project_id = 18
    response = client.get(f"/study_project_tasks/{project_id}")
    assert response.status_code == 200
    assert len(response.json()) > 0


def test_study_related_entities():
    # Test get_study_related_entities endpoint
    project_id = 18
                            
    response = client.get(f"/study_project/{project_id}/related_entities")
    assert response.status_code == 200
    assert len(response.json()) > 0
    for node in response.json():
        assert node["label"] is not None
        for entity in node["children"]:
            assert entity["label"] is not None
            assert entity["data"] is not None



def test_create_project_document_link():
    # Test create_project_document_link endpoint
    project_id = 18
    document_id = 129
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
    project_id = 18
    document_id = 129
    payload = {
        "project_id": project_id,
        "document_id": document_id
    }
    response = client.post("/project_document_unlink", json=payload)
    assert response.status_code == 200
    

    