"""
iCognition Backend API
Modern FastAPI application with async support and proper structure
"""

from app.utils.logging import get_logger

# Configure logging
logger = get_logger(__name__)


from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import PlainTextResponse

from app.core.config import settings
from app.core.security_middleware import SecurityMiddleware
from app.core.security_config import security_config
from app.core.audit_middleware import AuditLoggingMiddleware, SecurityAuditMiddleware
from app.core.audit_logging import audit_logger
from app.core.user_context import UserContext, get_authenticated_user_context
from app.core.firebase_auth import firebase_auth
from app.api.errors import (
    api_error_handler,
    http_error_handler, 
    validation_error_handler,
    APIError
)
from app.api.routes import users, bookmarks, documents, websocket, system, chat

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager for startup and shutdown events"""
    # Startup: Initialize resources
    logger.info("Starting up iCognition API with Firebase authentication")
    
    # Initialize Firebase Admin SDK
    try:
        # Firebase is initialized in firebase_auth module on import
        logger.info("Firebase Admin SDK initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize Firebase: {e}")
        # Don't fail startup, but log the error
    
    # TODO: Initialize database connections, background tasks, etc.
    # chat_session_manager.start_cleanup_task()
    
    yield
    
    # Shutdown: Clean up resources
    logger.info("Shutting down iCognition API")
    # TODO: Clean up resources when the app shuts down


# Create FastAPI application
app = FastAPI(
    title="iCognition API",
    description="AI-powered document analysis and knowledge management platform",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# Add security scheme for OpenAPI docs
from fastapi.openapi.utils import get_openapi

def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    
    openapi_schema = get_openapi(
        title="iCognition API",
        version="0.1.0",
        description="AI-powered document analysis and knowledge management platform",
        routes=app.routes,
    )
    
    # Add security scheme for Bearer token authentication
    openapi_schema["components"]["securitySchemes"] = {
        "BearerAuth": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": "Firebase ID Token"
        }
    }
    
    # Apply security to all endpoints that require authentication
    for path in openapi_schema["paths"]:
        for method in openapi_schema["paths"][path]:
            if method in ["get", "post", "put", "delete", "patch"]:
                endpoint = openapi_schema["paths"][path][method]
                # Add security requirement to endpoints that have authentication dependencies
                if "security" not in endpoint:
                    endpoint["security"] = [{"BearerAuth": []}]
    
    app.openapi_schema = openapi_schema
    return app.openapi_schema

app.openapi = custom_openapi

# Configure CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.BACKEND_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["icognition-answer-type"],
)

# Add security middleware
app.add_middleware(
    SecurityMiddleware,
    rate_limit_per_minute=security_config.rate_limit_per_minute,
    max_failed_attempts=security_config.max_failed_attempts,
    lockout_duration_minutes=security_config.lockout_duration_minutes,
    enable_cors_security=security_config.enable_cors_security,
    enable_security_headers=security_config.enable_security_headers
)

# Add audit logging middleware (disabled for development)
# app.add_middleware(AuditLoggingMiddleware)
app.add_middleware(SecurityAuditMiddleware)

# Register exception handlers
app.add_exception_handler(APIError, api_error_handler)
app.add_exception_handler(Exception, http_error_handler)
app.add_exception_handler(RequestValidationError, validation_error_handler)

# Register API routes
app.include_router(users.router)
app.include_router(bookmarks.router)
app.include_router(documents.router)
app.include_router(websocket.router)
app.include_router(system.router)
app.include_router(chat.router)


@app.get("/")
async def root():
    """Root endpoint - API health check"""
    return {"message": "Welcome to iCognition API"}


@app.get("/ping")
async def ping():
    """Simple ping endpoint for health checks"""
    return {"message": "pong", "status": "healthy"}


@app.get("/health")
async def health_check():
    """Comprehensive health check endpoint"""
    # TODO: Add database connectivity check, external service checks, etc.
    return {
        "status": "healthy",
        "message": "iCognition API is running",
        "version": "0.1.0"
    }




@app.get("/auth/test", status_code=200, tags=["Authentication"])
async def test_firebase_auth(user_context: UserContext = Depends(get_authenticated_user_context)):
    """Test Firebase authentication - requires valid Firebase ID token"""
    return {
        "message": "Firebase authentication successful",
        "user": {
            "id": user_context.user.id,
            "firebase_uid": user_context.user.id,  # Firebase UID is now stored as id
            "email": user_context.user.email,
            "display_name": user_context.user.display_name,
            "is_active": user_context.user.is_active,
            "is_verified": user_context.user.is_verified
        }
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level=settings.LOG_LEVEL.lower()
    )
