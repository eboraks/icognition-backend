# iCognition

An AI-powered document analysis and knowledge management platform that helps users organize, analyze, and extract insights from their documents and web content.

## 🏗️ Architecture

iCognition is a full-stack application consisting of:

- **Frontend**: Vue.js 3 + TypeScript + PrimeVue UI framework
- **Backend**: FastAPI + Python 3.12 + PostgreSQL with pgvector
- **AI Services**: Google Gemini AI for content analysis and embeddings
- **Authentication**: Firebase Authentication (optional - can be disabled for development)
- **Storage**: Google Cloud Storage for file management
- **Deployment**: Docker containers with GCP Cloud Build

## 🚀 Quick Start

### Prerequisites

- **Node.js** 18+ and **npm/yarn**
- **Python** 3.12+
- **Docker** and **Docker Compose**
- **PostgreSQL** (or use Docker)
- **Firebase CLI** (optional - for authentication)

### 1. Clone the Repository

```bash
git clone <repository-url>
cd icognition
```

### 2. Backend Setup

```bash
cd backend

# Create Python virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Set up environment variables
cp .env.example .env
# Edit .env with your configuration (see Environment Configuration section)

# Start database with Docker
docker-compose up -d

# Run database migrations
alembic upgrade head

# Start the backend server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 3. Frontend Setup

```bash
cd frontend

# Install dependencies
yarn install

# Set up environment configuration
# Edit environment.ts with your backend URL

# Start development server
yarn local  # For local development (no auth)
# or
yarn dev    # For development with auth
```

### 4. Access the Application

- **Frontend**: http://localhost:8080
- **Backend API**: http://localhost:8000
- **API Documentation**: http://localhost:8000/docs

## 🔧 Environment Configuration

### Backend Environment Variables

Create a `.env` file in the `backend/` directory:

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

### Frontend Environment Configuration

Edit `frontend/src/config/environment.ts`:

```typescript
export const environment = {
  production: false,
  apiUrl: 'http://localhost:8000',
  firebase: {
    // Firebase config (optional - only needed if using authentication)
    apiKey: 'your-api-key',
    authDomain: 'your-project.firebaseapp.com',
    projectId: 'your-project-id',
    // ... other Firebase config
  }
};
```

## 🔐 Authentication Setup (Optional)

### Option 1: Disable Authentication (Recommended for Development)

Set `DISABLE_AUTH=true` in your backend `.env` file. This allows you to develop and test without setting up Firebase.

### Option 2: Enable Firebase Authentication

1. **Create a Firebase Project**:
   - Go to [Firebase Console](https://console.firebase.google.com/)
   - Create a new project
   - Enable Authentication with your preferred providers

2. **Get Service Account Key**:
   - Go to Project Settings → Service Accounts
   - Generate a new private key
   - Download the JSON file

3. **Configure Backend**:
   - Copy the service account JSON to `backend/icognition-app-firebase-adminsdk-*.json`
   - Update your `.env` file with Firebase configuration
   - Set `DISABLE_AUTH=false`

4. **Configure Frontend**:
   - Update `frontend/src/config/environment.ts` with your Firebase config
   - Use `yarn dev` instead of `yarn local`

## 🧪 Testing

### Backend Tests

```bash
cd backend

# Run all tests
pytest

# Run specific test files
pytest tests/test_bookmark_endpoints.py
pytest tests/test_system_endpoints.py

# Run tests with coverage
pytest --cov=app tests/

# Run tests in watch mode
pytest-watch
```

### Frontend Tests

```bash
cd frontend

# Run unit tests (if configured)
yarn test

# Run linting
yarn lint:js
```

## 📚 API Documentation

### Core Endpoints

#### System Endpoints
- `GET /` - Health check
- `GET /ping` - Simple ping endpoint
- `GET /health` - Detailed health status
- `GET /docs` - Interactive API documentation

#### Authentication Endpoints
- `GET /auth/test` - Test authentication status

#### Bookmark Management
- `POST /bookmarks/` - Create a new bookmark
- `GET /bookmarks/` - List user bookmarks (paginated)
- `GET /bookmarks/{id}` - Get specific bookmark
- `PUT /bookmarks/{id}` - Update bookmark
- `DELETE /bookmarks/{id}` - Delete bookmark
- `GET /bookmarks/find?query={url}` - Find bookmark by URL
- `POST /bookmarks/{id}/re-analyze` - Re-analyze bookmark content

#### Document Management
- `POST /documents/` - Create document from URL or content
- `GET /documents/` - List user documents (paginated)
- `GET /documents/{id}` - Get specific document
- `PUT /documents/{id}` - Update document
- `DELETE /documents/{id}` - Delete document
- `GET /documents/{id}/content` - Get document content
- `POST /documents/{id}/embed` - Generate document embedding

### Authentication

When authentication is enabled, include the Firebase ID token in the Authorization header:

```bash
curl -H "Authorization: Bearer <firebase-id-token>" http://localhost:8000/bookmarks/
```

When authentication is disabled (`DISABLE_AUTH=true`), no authentication headers are required.

## 🛠️ Development Workflow

### 1. Daily Development

```bash
# Start database
docker-compose up -d

# Start backend (in one terminal)
cd backend
source .venv/bin/activate
uvicorn app.main:app --reload

# Start frontend (in another terminal)
cd frontend
yarn local
```

### 2. Making Changes

1. **Backend Changes**:
   - Make changes to Python files
   - Backend auto-reloads with `--reload` flag
   - Run tests: `pytest tests/`

2. **Frontend Changes**:
   - Make changes to Vue/TypeScript files
   - Frontend hot-reloads automatically
   - Check browser console for errors

3. **Database Changes**:
   - Create migration: `alembic revision --autogenerate -m "description"`
   - Apply migration: `alembic upgrade head`

### 3. Code Quality

```bash
# Backend linting and formatting
black app/
isort app/
flake8 app/

# Frontend linting
cd frontend
yarn lint:js
```

## 🐳 Docker Development

### Using Docker Compose

```bash
# Start all services
docker-compose up -d

# View logs
docker-compose logs -f

# Stop services
docker-compose down
```

### Database Management

```bash
# Connect to database
docker exec -it pgvector_container psql -U app -d icog_dev_db

# Run migrations
docker-compose exec backend alembic upgrade head

# Reset database
docker-compose down -v
docker-compose up -d
```

## 🚨 Troubleshooting

### Common Issues

1. **Database Connection Errors**:
   ```bash
   # Check if database is running
   docker-compose ps
   
   # Restart database
   docker-compose restart db
   ```

2. **Port Already in Use**:
   ```bash
   # Kill process on port 8000
   lsof -ti:8000 | xargs kill -9
   
   # Kill process on port 8080
   lsof -ti:8080 | xargs kill -9
   ```

3. **Python Dependencies Issues**:
   ```bash
   # Recreate virtual environment
   rm -rf .venv
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

4. **Firebase Authentication Issues**:
   - Verify service account JSON file is correct
   - Check Firebase project configuration
   - Use `DISABLE_AUTH=true` for development

### Getting Help

- Check the [API Documentation](http://localhost:8000/docs) for endpoint details
- Review test files in `backend/tests/` for usage examples
- Check application logs for detailed error messages

## 📁 Project Structure

```
icognition/
├── backend/                 # FastAPI backend
│   ├── app/                # Application code
│   │   ├── api/           # API routes and models
│   │   ├── core/          # Core functionality (auth, security)
│   │   ├── services/      # Business logic services
│   │   ├── db/            # Database configuration
│   │   └── legacy_files/  # Legacy code (moved for cleanup)
│   ├── tests/             # Test files
│   ├── migrations/        # Database migrations
│   └── requirements.txt   # Python dependencies
├── frontend/              # Vue.js frontend
│   ├── src/              # Source code
│   │   ├── components/   # Vue components
│   │   ├── views/        # Page views
│   │   ├── services/     # API services
│   │   └── config/       # Configuration
│   └── package.json      # Node.js dependencies
├── docker-compose.yml     # Docker services
└── README.md             # This file
```

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/your-feature`
3. Make your changes
4. Run tests: `pytest` (backend) and `yarn lint:js` (frontend)
5. Commit your changes: `git commit -m 'Add your feature'`
6. Push to the branch: `git push origin feature/your-feature`
7. Submit a pull request

## 📄 License

This project is proprietary software. All rights reserved.
