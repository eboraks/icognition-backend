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
        "tasks": [{"description": "test_task"}]
    }
    response = client.post("/study_project", json=payload)
    assert response.status_code == 200
    assert response.json()["name"] == "test_project"
    assert response.json()["objective"] == "test_objective"
    assert response.json()["user_id"] == "test_user"
    assert len(response.json()["tasks"]) > 0

@pytest.mark.asyncio
async def test_get_study_project():
    # Test get_study_project endpoint
    response = await client.get("/study_project/1")
    assert response.status_code == 200
    assert response.json()["id"] == 1

@pytest.mark.asyncio
async def test_delete_study_project():
    # Test delete_study_project endpoint
    response = await client.delete("/study_project/1")
    assert response.status_code == 204

@pytest.mark.asyncio
async def test_create_study_task():
    # Test create_study_task endpoint
    payload = {
        "project_id": 1,
        "description": "test_description"
    }
    response = await client.post("/study_task", json=payload)
    assert response.status_code == 200
    assert response.json()["project_id"] == 1
    assert response.json()["description"] == "test_description"

@pytest.mark.asyncio
async def test_get_study_tasks():
    # Test get_study_tasks endpoint
    response = await client.get("/study_tasks/1")
    assert response.status_code == 200
    assert len(response.json()) > 0
