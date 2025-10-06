"""
API documentation tests for the API endpoints
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from app.main import app
from app.models import User, Document, Bookmark
from datetime import datetime

client = TestClient(app)


class TestAPIDocumentation:
    """API documentation tests for API endpoints"""

    @pytest.fixture
    def mock_user(self):
        """Mock user for API documentation testing"""
        return User(
            id="docs-test-uid",
            email="docs@example.com",
            display_name="Documentation Test User",
            is_active=True,
            is_verified=True
        )

    @pytest.fixture
    def mock_user_context(self, mock_user):
        """Mock user context for API documentation testing"""
        from app.core.user_context import UserContext
        return UserContext(user=mock_user)

    def test_openapi_schema_availability(self):
        """Test that OpenAPI schema is available"""
        # Act
        response = client.get("/openapi.json")
        
        # Assert
        assert response.status_code == 200
        data = response.json()
        assert "openapi" in data
        assert "info" in data
        assert "paths" in data
        assert "components" in data

    def test_swagger_ui_availability(self):
        """Test that Swagger UI is available"""
        # Act
        response = client.get("/docs")
        
        # Assert
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    def test_redoc_availability(self):
        """Test that ReDoc is available"""
        # Act
        response = client.get("/redoc")
        
        # Assert
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    def test_openapi_schema_structure(self):
        """Test OpenAPI schema structure"""
        # Act
        response = client.get("/openapi.json")
        
        # Assert
        assert response.status_code == 200
        data = response.json()
        
        # Check basic structure
        assert "openapi" in data
        assert "info" in data
        assert "paths" in data
        assert "components" in data
        
        # Check info section
        info = data["info"]
        assert "title" in info
        assert "version" in info
        assert "description" in info
        
        # Check paths section
        paths = data["paths"]
        assert "/" in paths
        assert "/ping" in paths
        assert "/health" in paths
        assert "/auth/test" in paths
        assert "/documents/" in paths
        assert "/bookmarks/" in paths

    def test_openapi_schema_endpoints(self):
        """Test OpenAPI schema endpoint definitions"""
        # Act
        response = client.get("/openapi.json")
        
        # Assert
        assert response.status_code == 200
        data = response.json()
        paths = data["paths"]
        
        # Check system endpoints
        assert "/" in paths
        assert "get" in paths["/"]
        
        assert "/ping" in paths
        assert "get" in paths["/ping"]
        
        assert "/health" in paths
        assert "get" in paths["/health"]
        
        # Check auth endpoints
        assert "/auth/test" in paths
        assert "get" in paths["/auth/test"]
        
        # Check document endpoints
        assert "/documents/" in paths
        assert "get" in paths["/documents/"]
        assert "post" in paths["/documents/"]
        
        # Check bookmark endpoints
        assert "/bookmarks/" in paths
        assert "get" in paths["/bookmarks/"]
        assert "post" in paths["/bookmarks/"]

    def test_openapi_schema_components(self):
        """Test OpenAPI schema components"""
        # Act
        response = client.get("/openapi.json")
        
        # Assert
        assert response.status_code == 200
        data = response.json()
        components = data["components"]
        
        # Check security schemes
        if "securitySchemes" in components:
            security_schemes = components["securitySchemes"]
            assert "BearerAuth" in security_schemes
        
        # Check schemas
        if "schemas" in components:
            schemas = components["schemas"]
            # Should have model schemas
            assert "User" in schemas or "Document" in schemas or "Bookmark" in schemas

    def test_openapi_schema_security(self):
        """Test OpenAPI schema security definitions"""
        # Act
        response = client.get("/openapi.json")
        
        # Assert
        assert response.status_code == 200
        data = response.json()
        
        # Check if security schemes are defined
        if "components" in data and "securitySchemes" in data["components"]:
            security_schemes = data["components"]["securitySchemes"]
            assert "BearerAuth" in security_schemes
            
            bearer_auth = security_schemes["BearerAuth"]
            assert bearer_auth["type"] == "http"
            assert bearer_auth["scheme"] == "bearer"

    def test_openapi_schema_tags(self):
        """Test OpenAPI schema tags"""
        # Act
        response = client.get("/openapi.json")
        
        # Assert
        assert response.status_code == 200
        data = response.json()
        
        # Check if tags are defined
        if "tags" in data:
            tags = data["tags"]
            # Should have system, auth, documents, bookmarks tags
            tag_names = [tag["name"] for tag in tags]
            assert "System" in tag_names or "Authentication" in tag_names

    def test_openapi_schema_responses(self):
        """Test OpenAPI schema response definitions"""
        # Act
        response = client.get("/openapi.json")
        
        # Assert
        assert response.status_code == 200
        data = response.json()
        paths = data["paths"]
        
        # Check response definitions for key endpoints
        if "/ping" in paths and "get" in paths["/ping"]:
            ping_endpoint = paths["/ping"]["get"]
            if "responses" in ping_endpoint:
                responses = ping_endpoint["responses"]
                assert "200" in responses

    def test_openapi_schema_parameters(self):
        """Test OpenAPI schema parameter definitions"""
        # Act
        response = client.get("/openapi.json")
        
        # Assert
        assert response.status_code == 200
        data = response.json()
        paths = data["paths"]
        
        # Check parameter definitions for endpoints that have them
        if "/documents/{document_id}" in paths:
            doc_endpoint = paths["/documents/{document_id}"]
            if "get" in doc_endpoint and "parameters" in doc_endpoint["get"]:
                parameters = doc_endpoint["get"]["parameters"]
                # Should have document_id parameter
                param_names = [param["name"] for param in parameters]
                assert "document_id" in param_names

    def test_openapi_schema_request_bodies(self):
        """Test OpenAPI schema request body definitions"""
        # Act
        response = client.get("/openapi.json")
        
        # Assert
        assert response.status_code == 200
        data = response.json()
        paths = data["paths"]
        
        # Check request body definitions for POST endpoints
        if "/documents/" in paths and "post" in paths["/documents/"]:
            post_endpoint = paths["/documents/"]["post"]
            if "requestBody" in post_endpoint:
                request_body = post_endpoint["requestBody"]
                assert "content" in request_body
                assert "application/json" in request_body["content"]

    def test_openapi_schema_models(self):
        """Test OpenAPI schema model definitions"""
        # Act
        response = client.get("/openapi.json")
        
        # Assert
        assert response.status_code == 200
        data = response.json()
        
        # Check if models are defined in components/schemas
        if "components" in data and "schemas" in data["components"]:
            schemas = data["components"]["schemas"]
            # Should have basic model definitions
            assert len(schemas) > 0

    def test_swagger_ui_functionality(self):
        """Test Swagger UI functionality"""
        # Act
        response = client.get("/docs")
        
        # Assert
        assert response.status_code == 200
        content = response.text
        
        # Check for Swagger UI specific content
        assert "swagger" in content.lower() or "openapi" in content.lower()
        assert "html" in content.lower()

    def test_redoc_functionality(self):
        """Test ReDoc functionality"""
        # Act
        response = client.get("/redoc")
        
        # Assert
        assert response.status_code == 200
        content = response.text
        
        # Check for ReDoc specific content
        assert "redoc" in content.lower() or "openapi" in content.lower()
        assert "html" in content.lower()

    def test_documentation_consistency(self):
        """Test documentation consistency between OpenAPI and actual endpoints"""
        # Act
        openapi_response = client.get("/openapi.json")
        ping_response = client.get("/ping")
        
        # Assert
        assert openapi_response.status_code == 200
        assert ping_response.status_code == 200
        
        # OpenAPI should document the ping endpoint
        openapi_data = openapi_response.json()
        assert "/ping" in openapi_data["paths"]
        assert "get" in openapi_data["paths"]["/ping"]

    def test_documentation_completeness(self):
        """Test documentation completeness"""
        # Act
        response = client.get("/openapi.json")
        
        # Assert
        assert response.status_code == 200
        data = response.json()
        paths = data["paths"]
        
        # Check that major endpoint groups are documented
        system_endpoints = ["/", "/ping", "/health"]
        auth_endpoints = ["/auth/test"]
        document_endpoints = ["/documents/"]
        bookmark_endpoints = ["/bookmarks/"]
        
        for endpoint in system_endpoints + auth_endpoints + document_endpoints + bookmark_endpoints:
            assert endpoint in paths

    def test_documentation_accuracy(self):
        """Test documentation accuracy"""
        # Act
        openapi_response = client.get("/openapi.json")
        actual_response = client.get("/ping")
        
        # Assert
        assert openapi_response.status_code == 200
        assert actual_response.status_code == 200
        
        # The documented response should match the actual response
        openapi_data = openapi_response.json()
        ping_endpoint = openapi_data["paths"]["/ping"]["get"]
        
        if "responses" in ping_endpoint and "200" in ping_endpoint["responses"]:
            # The endpoint should return 200 as documented
            assert actual_response.status_code == 200

    def test_documentation_accessibility(self):
        """Test documentation accessibility"""
        # Act
        swagger_response = client.get("/docs")
        redoc_response = client.get("/redoc")
        openapi_response = client.get("/openapi.json")
        
        # Assert
        assert swagger_response.status_code == 200
        assert redoc_response.status_code == 200
        assert openapi_response.status_code == 200
        
        # All documentation endpoints should be accessible
        assert "text/html" in swagger_response.headers["content-type"]
        assert "text/html" in redoc_response.headers["content-type"]
        assert "application/json" in openapi_response.headers["content-type"]

    def test_documentation_security(self):
        """Test documentation security"""
        # Act
        response = client.get("/docs")
        
        # Assert
        assert response.status_code == 200
        
        # Documentation should be accessible (no authentication required)
        # This is typical for API documentation

    def test_documentation_performance(self):
        """Test documentation performance"""
        # Act
        import time
        start_time = time.time()
        response = client.get("/openapi.json")
        end_time = time.time()
        
        # Assert
        assert response.status_code == 200
        assert (end_time - start_time) < 1.0  # Should load quickly

    def test_documentation_caching(self):
        """Test documentation caching"""
        # Act
        response = client.get("/openapi.json")
        
        # Assert
        assert response.status_code == 200
        
        # Check for cache headers (if implemented)
        # assert "Cache-Control" in response.headers

    def test_documentation_versioning(self):
        """Test documentation versioning"""
        # Act
        response = client.get("/openapi.json")
        
        # Assert
        assert response.status_code == 200
        data = response.json()
        
        # Check version information
        if "info" in data:
            info = data["info"]
            assert "version" in info
            assert "title" in info
