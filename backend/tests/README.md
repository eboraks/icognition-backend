# Integration Testing Setup

This directory contains integration tests that require a running FastAPI server and PostgreSQL database.

## Prerequisites

1. **Running FastAPI Server**: The backend server must be running on `http://localhost:8000` (or set `TEST_BASE_URL` environment variable)
2. **PostgreSQL Database**: A PostgreSQL database must be running and accessible
3. **Firebase Configuration**: Firebase Admin SDK must be configured (or tests will use mocked authentication)

## Environment Variables

Set these environment variables for testing:

```bash
# Optional: Override the test server URL
export TEST_BASE_URL="http://localhost:8000"

# Optional: Override test Firebase token
export TEST_FIREBASE_TOKEN="your_test_firebase_token"

# Optional: Override test Firebase UID
export TEST_FIREBASE_UID="your_test_firebase_uid"
```

## Running Tests

### Start the Backend Server

```bash
# In the backend directory
uv run python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Run Tests

```bash
# Run all tests
uv run pytest tests/ -v

# Run specific test file
uv run pytest tests/test_auth_endpoints.py -v

# Run with coverage
uv run pytest tests/ --cov=app --cov-report=html
```

## Test Structure

- **`conftest.py`**: Pytest configuration and fixtures
- **`test_auth_endpoints.py`**: Authentication endpoint tests
- **`test_system_endpoints.py`**: System health endpoint tests
- **`test_document_endpoints.py`**: Document management endpoint tests
- **`test_bookmark_endpoints.py`**: Bookmark management endpoint tests

## Test Features

- **Real HTTP Requests**: Tests make actual HTTP requests to the running server
- **Database Integration**: Tests use the real PostgreSQL database
- **Authentication Mocking**: Firebase authentication is mocked for testing
- **Async Support**: All tests use async/await for proper FastAPI testing

## Benefits

1. **Real Integration**: Tests the actual API endpoints as they would be used
2. **Database Compatibility**: Uses PostgreSQL, matching production environment
3. **Simplified Setup**: No need for complex test database setup or SQLite compatibility
4. **Better Coverage**: Tests the full request/response cycle including middleware

## Troubleshooting

### Server Not Running
```
httpx.ConnectError: [Errno 61] Connection refused
```
Make sure the FastAPI server is running on the correct port.

### Database Connection Issues
```
sqlalchemy.exc.OperationalError: (psycopg2.OperationalError)
```
Ensure PostgreSQL is running and the database connection is properly configured.

### Authentication Issues
```
401 Unauthorized
```
Check that Firebase Admin SDK is properly configured or that the mock authentication is working.
