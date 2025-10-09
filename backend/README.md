# iCognition Backend

FastAPI-based backend service for the iCognition document analysis platform.

## 🏗️ Architecture

- **Framework**: FastAPI with async/await support
- **Database**: PostgreSQL with pgvector for embeddings
- **Authentication**: Firebase Authentication (optional)
- **AI Services**: Google Gemini AI for content analysis
- **Storage**: Google Cloud Storage integration
- **Testing**: pytest with async support

## 🚀 Quick Start

### Prerequisites

- Python 3.12+
- PostgreSQL (or Docker)
- Google AI API key
- Firebase project (optional)

### 1. Environment Setup

```bash
# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Environment Configuration

Create a `.env` file in the backend directory:

```bash
# Copy example file
cp .env.example .env
```

Edit `.env` with your configuration:

```bash
# Database Configuration
DATABASE_URL=postgresql://app:2214@localhost:5432/icog_dev_db

# Firebase Configuration (Optional - set DISABLE_AUTH=true to skip)
FIREBASE_PROJECT_ID=your-firebase-project-id
FIREBASE_PRIVATE_KEY_ID=your-private-key-id
FIREBASE_PRIVATE_KEY="-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n"
FIREBASE_CLIENT_EMAIL=your-service-account@your-project.iam.gserviceaccount.com
FIREBASE_CLIENT_ID=your-client-id
FIREBASE_AUTH_URI=https://accounts.google.com/o/oauth2/auth
FIREBASE_TOKEN_URI=https://oauth2.googleapis.com/token
FIREBASE_AUTH_PROVIDER_X509_CERT_URL=https://www.googleapis.com/oauth2/v1/certs
FIREBASE_CLIENT_X509_CERT_URL=https://www.googleapis.com/robot/v1/metadata/x509/your-service-account%40your-project.iam.gserviceaccount.com

# Google AI Configuration
GOOGLE_API_KEY=your-google-ai-api-key

# Google Cloud Storage (Optional)
GOOGLE_CLOUD_PROJECT_ID=your-gcp-project-id
GOOGLE_CLOUD_STORAGE_BUCKET=your-storage-bucket

# Application Settings
DISABLE_AUTH=true  # Set to true to disable authentication for development
LOG_LEVEL=INFO
BACKEND_CORS_ORIGINS=["http://localhost:8080", "http://127.0.0.1:8080"]
```

### 3. Database Setup

#### Option A: Using Docker (Recommended)

```bash
# Start PostgreSQL with pgvector
docker-compose up -d

# Run migrations
alembic upgrade head
```

#### Option B: Local PostgreSQL

```bash
# Create database
createdb icog_dev_db

# Run migrations
alembic upgrade head
```

### 4. Start the Server

```bash
# Development server with auto-reload
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Production server
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### 5. Verify Installation

- **API**: http://localhost:8000
- **Documentation**: http://localhost:8000/docs
- **Health Check**: http://localhost:8000/health

## 🔐 Authentication Setup

### Option 1: Disable Authentication (Development)

Set `DISABLE_AUTH=true` in your `.env` file. This allows development without Firebase setup.

### Option 2: Enable Firebase Authentication

1. **Get Firebase Service Account**:
   - Go to Firebase Console → Project Settings → Service Accounts
   - Generate new private key
   - Download JSON file

2. **Configure Environment**:
   - Copy service account JSON to `icognition-app-firebase-adminsdk-*.json`
   - Update `.env` with Firebase configuration
   - Set `DISABLE_AUTH=false`

3. **Test Authentication**:
   ```bash
   curl http://localhost:8000/auth/test
   ```

## 🧪 Testing

### Run All Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=app tests/

# Run specific test file
pytest tests/test_bookmark_endpoints.py

# Run tests in watch mode
pytest-watch
```

### Test Categories

- **Unit Tests**: `tests/test_*.py`
- **Integration Tests**: `tests/test_*_endpoints.py`
- **API Tests**: `tests/test_api_*.py`

### Test Configuration

Tests use a separate test database and mock Firebase authentication. The test configuration is in `tests/conftest.py`.

## 📚 API Documentation

### Interactive Documentation

Visit http://localhost:8000/docs for interactive API documentation with:
- Request/response examples
- Authentication testing
- Schema validation

### Core Endpoints

#### System
- `GET /` - Root endpoint
- `GET /ping` - Health ping
- `GET /health` - Detailed health status

#### Authentication
- `GET /auth/test` - Test authentication

#### Bookmarks
- `POST /bookmarks/` - Create bookmark
- `GET /bookmarks/` - List bookmarks
- `GET /bookmarks/{id}` - Get bookmark
- `PUT /bookmarks/{id}` - Update bookmark
- `DELETE /bookmarks/{id}` - Delete bookmark
- `POST /bookmarks/{id}/re-analyze` - Re-analyze content

#### Documents
- `POST /documents/` - Create document
- `GET /documents/` - List documents
- `GET /documents/{id}` - Get document
- `PUT /documents/{id}` - Update document
- `DELETE /documents/{id}` - Delete document
- `GET /documents/{id}/content` - Get content
- `POST /documents/{id}/embed` - Generate embedding

### Request Examples

#### Create Bookmark
```bash
curl -X POST "http://localhost:8000/bookmarks/" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://example.com/article",
    "title": "Example Article",
    "description": "A sample article for testing"
  }'
```

#### List Bookmarks
```bash
curl "http://localhost:8000/bookmarks/?page=1&page_size=10"
```

## 🛠️ Development

### Project Structure

```
backend/
├── app/
│   ├── api/              # API routes and models
│   │   ├── routes/       # Endpoint definitions
│   │   └── models/       # Request/response models
│   ├── core/             # Core functionality
│   │   ├── config.py     # Configuration settings
│   │   ├── firebase_auth.py  # Firebase authentication
│   │   ├── security_middleware.py  # Security middleware
│   │   └── user_context.py  # User context management
│   ├── services/         # Business logic services
│   │   ├── bookmark_service.py
│   │   ├── document_service.py
│   │   └── content_analysis_service.py
│   ├── db/               # Database configuration
│   │   └── database.py   # Database connection
│   ├── models.py         # SQLModel database models
│   └── main.py           # FastAPI application
├── tests/                # Test files
├── migrations/           # Alembic database migrations
└── requirements.txt      # Python dependencies
```

### Adding New Features

1. **Create Service**:
   ```python
   # app/services/new_service.py
   from app.services.base_service import UserIsolatedService
   
   class NewService(UserIsolatedService):
       async def create_item(self, user_id: str, data: dict):
           # Implementation
           pass
   ```

2. **Create API Route**:
   ```python
   # app/api/routes/new_feature.py
   from fastapi import APIRouter
   from app.services.new_service import NewService
   
   router = APIRouter(prefix="/new-feature", tags=["new-feature"])
   
   @router.post("/")
   async def create_item(
       data: CreateItemRequest,
       user_context: UserContext = Depends(get_authenticated_user_context),
       session: AsyncSession = Depends(get_session)
   ):
       service = NewService(session)
       return await service.create_item(user_context.user.id, data.dict())
   ```

3. **Register Route**:
   ```python
   # app/main.py
   from app.api.routes import new_feature
   app.include_router(new_feature.router)
   ```

### Database Migrations

```bash
# Create migration
alembic revision --autogenerate -m "Add new table"

# Apply migration
alembic upgrade head

# Rollback migration
alembic downgrade -1
```

### Code Quality

```bash
# Format code
black app/
isort app/

# Lint code
flake8 app/

# Type checking
mypy app/
```

## 🐳 Docker Development

### Using Docker Compose

```bash
# Start all services
docker-compose up -d

# View logs
docker-compose logs -f backend

# Stop services
docker-compose down
```

### Database Management

```bash
# Connect to database
docker exec -it pgvector_container psql -U app -d icog_dev_db

# Run migrations in container
docker-compose exec backend alembic upgrade head

# Reset database
docker-compose down -v
docker-compose up -d
```

## 🚨 Troubleshooting

### Common Issues

1. **Database Connection Error**:
   ```bash
   # Check if database is running
   docker-compose ps
   
   # Check database logs
   docker-compose logs db
   ```

2. **Import Errors**:
   ```bash
   # Ensure virtual environment is activated
   source .venv/bin/activate
   
   # Reinstall dependencies
   pip install -r requirements.txt
   ```

3. **Firebase Authentication Issues**:
   - Verify service account JSON file
   - Check Firebase project configuration
   - Use `DISABLE_AUTH=true` for development

4. **Port Already in Use**:
   ```bash
   # Find process using port 8000
   lsof -i :8000
   
   # Kill process
   kill -9 <PID>
   ```

### Debug Mode

```bash
# Run with debug logging
LOG_LEVEL=DEBUG uvicorn app.main:app --reload

# Run with detailed error messages
uvicorn app.main:app --reload --log-level debug
```

## 📊 Monitoring

### Health Checks

- `GET /health` - Application health status
- `GET /ping` - Simple connectivity test

### Logging

Logs are written to:
- Console (development)
- `logs/audit.log` (audit events)
- Application logs (structured JSON)

### Metrics

The application includes:
- Request/response logging
- Security event tracking
- Performance monitoring
- Error tracking

## 🔒 Security

### Security Features

- **Rate Limiting**: Configurable per-IP rate limits
- **CORS Protection**: Configurable allowed origins
- **Security Headers**: Standard security headers
- **Input Validation**: Pydantic model validation
- **SQL Injection Protection**: SQLAlchemy ORM
- **Authentication**: Firebase JWT tokens

### Security Configuration

```python
# app/core/security_config.py
security_config = SecurityConfig(
    rate_limit_per_minute=60,
    max_failed_attempts=5,
    lockout_duration_minutes=15,
    enable_cors_security=True,
    enable_security_headers=True
)
```

## 🚀 Deployment

### Production Deployment

1. **Environment Setup**:
   ```bash
   # Set production environment variables
   export DATABASE_URL="postgresql://user:pass@host:5432/db"
   export DISABLE_AUTH=false
   export LOG_LEVEL=INFO
   ```

2. **Run Migrations**:
   ```bash
   alembic upgrade head
   ```

3. **Start Server**:
   ```bash
   uvicorn app.main:app --host 0.0.0.0 --port 8000
   ```

### Docker Production

```bash
# Build image
docker build -t icognition-backend .

# Run container
docker run -p 8000:8000 --env-file .env icognition-backend
```

## 📄 License

This project is proprietary software. All rights reserved.