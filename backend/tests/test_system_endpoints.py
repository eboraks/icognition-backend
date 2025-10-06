"""
Integration tests for system endpoints
Tests require a running FastAPI server and PostgreSQL database
"""

import pytest
import httpx


class TestSystemEndpoints:
    """Test system endpoints"""

    @pytest.mark.asyncio
    async def test_root_endpoint(self, client: httpx.AsyncClient):
        """Test root endpoint"""
        response = await client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert data["message"] == "Welcome to iCognition API"

    @pytest.mark.asyncio
    async def test_ping_endpoint(self, client: httpx.AsyncClient):
        """Test ping endpoint"""
        response = await client.get("/ping")
        assert response.status_code == 200
        data = response.json()
        assert data == {"status": "healthy", "message": "pong"}

    @pytest.mark.asyncio
    async def test_health_endpoint(self, client: httpx.AsyncClient):
        """Test health endpoint"""
        response = await client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "message" in data
        assert "version" in data
        assert data["status"] == "healthy"
        assert data["message"] == "iCognition API is running"
        assert data["version"] == "0.1.0"

    @pytest.mark.asyncio
    async def test_health_endpoint_structure(self, client: httpx.AsyncClient):
        """Test health endpoint response structure"""
        response = await client.get("/health")
        assert response.status_code == 200
        data = response.json()
        
        # Check required fields
        required_fields = ["status", "message", "version"]
        for field in required_fields:
            assert field in data
        
        # Check data types
        assert isinstance(data["status"], str)
        assert isinstance(data["message"], str)
        assert isinstance(data["version"], str)

    @pytest.mark.asyncio
    async def test_root_endpoint_structure(self, client: httpx.AsyncClient):
        """Test root endpoint response structure"""
        response = await client.get("/")
        assert response.status_code == 200
        data = response.json()
        
        # Check required fields
        required_fields = ["message"]
        for field in required_fields:
            assert field in data
        
        # Check data types
        assert isinstance(data["message"], str)

    @pytest.mark.asyncio
    async def test_ping_endpoint_structure(self, client: httpx.AsyncClient):
        """Test ping endpoint response structure"""
        response = await client.get("/ping")
        assert response.status_code == 200
        data = response.json()
        
        # Check required fields
        required_fields = ["message", "status"]
        for field in required_fields:
            assert field in data
        
        # Check data types
        assert isinstance(data["status"], str)
        assert isinstance(data["message"], str)

    @pytest.mark.asyncio
    async def test_health_endpoint_consistency(self, client: httpx.AsyncClient):
        """Test health endpoint returns consistent data"""
        response1 = await client.get("/health")
        response2 = await client.get("/health")
        
        assert response1.status_code == 200
        assert response2.status_code == 200
        
        data1 = response1.json()
        data2 = response2.json()
        
        # Status, message and version should be consistent
        assert data1["status"] == data2["status"]
        assert data1["message"] == data2["message"]
        assert data1["version"] == data2["version"]

    @pytest.mark.asyncio
    async def test_ping_endpoint_consistency(self, client: httpx.AsyncClient):
        """Test ping endpoint returns consistent data"""
        response1 = await client.get("/ping")
        response2 = await client.get("/ping")
        
        assert response1.status_code == 200
        assert response2.status_code == 200
        
        data1 = response1.json()
        data2 = response2.json()
        
        # Should be identical
        assert data1 == data2
        assert data1["status"] == "healthy"
        assert data1["message"] == "pong"

    @pytest.mark.asyncio
    async def test_root_endpoint_consistency(self, client: httpx.AsyncClient):
        """Test root endpoint returns consistent data"""
        response1 = await client.get("/")
        response2 = await client.get("/")
        
        assert response1.status_code == 200
        assert response2.status_code == 200
        
        data1 = response1.json()
        data2 = response2.json()
        
        # Should be identical
        assert data1 == data2
        assert data1["message"] == "Welcome to iCognition API"

    @pytest.mark.asyncio
    async def test_system_endpoints_headers(self, client: httpx.AsyncClient):
        """Test system endpoints return appropriate headers"""
        root_response = await client.get("/")
        ping_response = await client.get("/ping")
        health_response = await client.get("/health")
        
        assert root_response.status_code == 200
        assert ping_response.status_code == 200
        assert health_response.status_code == 200
        
        # Check for common headers (e.g., Content-Type)
        assert "content-type" in root_response.headers
        assert "content-type" in ping_response.headers
        assert "content-type" in health_response.headers
        
        assert root_response.headers["content-type"] == "application/json"
        assert ping_response.headers["content-type"] == "application/json"
        assert health_response.headers["content-type"] == "application/json"

    @pytest.mark.asyncio
    async def test_system_endpoints_methods(self, client: httpx.AsyncClient):
        """Test system endpoints only respond to GET requests"""
        # Root endpoint
        assert (await client.post("/")).status_code == 405
        assert (await client.put("/")).status_code == 405
        assert (await client.delete("/")).status_code == 405
        
        # Ping endpoint
        assert (await client.post("/ping")).status_code == 405
        assert (await client.put("/ping")).status_code == 405
        assert (await client.delete("/ping")).status_code == 405
        
        # Health endpoint
        assert (await client.post("/health")).status_code == 405
        assert (await client.put("/health")).status_code == 405
        assert (await client.delete("/health")).status_code == 405

    @pytest.mark.asyncio
    async def test_system_endpoints_with_parameters(self, client: httpx.AsyncClient):
        """Test system endpoints ignore query parameters"""
        root_response = await client.get("/?test=value")
        ping_response = await client.get("/ping?test=value")
        health_response = await client.get("/health?test=value")
        
        assert root_response.status_code == 200
        assert ping_response.status_code == 200
        assert health_response.status_code == 200
        
        # Responses should be the same as without parameters
        root_data = root_response.json()
        ping_data = ping_response.json()
        health_data = health_response.json()
        
        assert root_data["message"] == "Welcome to iCognition API"
        assert ping_data["status"] == "healthy"
        assert health_data["status"] == "healthy"

    @pytest.mark.asyncio
    async def test_system_endpoints_performance(self, client: httpx.AsyncClient):
        """Test system endpoints respond quickly"""
        import time
        
        start_time = time.time()
        await client.get("/")
        root_time = time.time() - start_time
        
        start_time = time.time()
        await client.get("/ping")
        ping_time = time.time() - start_time
        
        start_time = time.time()
        await client.get("/health")
        health_time = time.time() - start_time
        
        # Should respond quickly (less than 1 second)
        assert root_time < 1.0
        assert ping_time < 1.0
        assert health_time < 1.0

    @pytest.mark.asyncio
    async def test_health_endpoint_timestamp_format(self, client: httpx.AsyncClient):
        """Test health endpoint response format"""
        response = await client.get("/health")
        assert response.status_code == 200
        data = response.json()
        
        # Check that required fields exist and have correct types
        assert "status" in data
        assert "message" in data
        assert "version" in data
        assert isinstance(data["status"], str)
        assert isinstance(data["message"], str)
        assert isinstance(data["version"], str)

    @pytest.mark.asyncio
    async def test_system_endpoints_error_handling(self, client: httpx.AsyncClient):
        """Test system endpoints handle errors gracefully"""
        # These endpoints should not fail under normal circumstances
        response = await client.get("/nonexistent-endpoint")
        
        assert response.status_code == 404
        assert "detail" in response.json()
        assert response.json()["detail"] == "Not Found"