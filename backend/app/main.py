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
from fastapi.responses import PlainTextResponse, JSONResponse

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
from app.api.routes import users, bookmarks, documents, websocket, system, chat, knowledge, notifications

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
app.include_router(knowledge.router)
app.include_router(notifications.router)


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


@app.get("/status")
async def status_check():
    """
    Detailed status endpoint that checks database and Gemini connectivity.
    Returns the health status of critical services.
    """
    from app.db.database import async_session
    from app.services.gemini_service import get_gemini_service, GeminiModel, GeminiConfig
    from sqlalchemy import text
    
    status = {
        "timestamp": datetime.utcnow().isoformat(),
        "service": "iCognition API",
        "version": "0.1.0",
        "checks": {}
    }
    
    overall_healthy = True
    
    # Check database connectivity
    db_status = {
        "status": "unknown",
        "message": "",
        "details": {}
    }
    
    try:
        async with async_session() as session:
            # Simple query to test connection
            result = await session.execute(text("SELECT version(), current_database(), current_user"))
            row = result.fetchone()
            
            db_status["status"] = "healthy"
            db_status["message"] = "Database connection successful"
            db_status["details"] = {
                "postgresql_version": row[0] if row else "unknown",
                "database": row[1] if row else "unknown",
                "user": row[2] if row else "unknown"
            }
            
            # Test pgvector extension
            result = await session.execute(text("SELECT * FROM pg_extension WHERE extname = 'vector'"))
            extension = result.fetchone()
            db_status["details"]["pgvector_installed"] = extension is not None
            
    except Exception as e:
        db_status["status"] = "unhealthy"
        db_status["message"] = f"Database connection failed: {str(e)}"
        overall_healthy = False
    
    status["checks"]["database"] = db_status
    
    # Check Gemini API connectivity
    gemini_status = {
        "status": "unknown",
        "message": "",
        "details": {}
    }
    
    try:
        gemini_service = get_gemini_service()
        
        # Check if API key is configured
        api_key = getattr(gemini_service, 'api_key', None)
        if gemini_service.mock_mode:
            gemini_status["status"] = "unhealthy"
            gemini_status["message"] = "Gemini service is in mock mode (API key not configured)"
            overall_healthy = False
        elif not api_key:
            gemini_status["status"] = "unhealthy"
            gemini_status["message"] = "Gemini API key not configured"
            overall_healthy = False
        elif gemini_service.client is None:
            gemini_status["status"] = "unhealthy"
            gemini_status["message"] = "Gemini client not initialized"
            overall_healthy = False
        else:
            # Make a simple test call to verify connectivity
            # Use a minimal prompt to test the API
            test_response = await gemini_service.generate_content(
                prompt="Say 'OK' if you can read this.",
                model=GeminiModel.FLASH_LITE,
                config=GeminiConfig(
                    max_output_tokens=10,
                    temperature=0.1
                )
            )
            
            if test_response and test_response.get("text"):
                gemini_status["status"] = "healthy"
                gemini_status["message"] = "Gemini API connection successful"
                gemini_status["details"] = {
                    "model": GeminiModel.FLASH_LITE.value,
                    "test_response_received": True
                }
            else:
                gemini_status["status"] = "unhealthy"
                gemini_status["message"] = "Gemini API returned empty response"
                overall_healthy = False
                
    except Exception as e:
        gemini_status["status"] = "unhealthy"
        gemini_status["message"] = f"Gemini API connection failed: {str(e)}"
        overall_healthy = False
    
    status["checks"]["gemini"] = gemini_status
    
    # Set overall status
    status["status"] = "healthy" if overall_healthy else "degraded"
    
    # Return appropriate HTTP status code
    if overall_healthy:
        return status
    else:
        # Return 503 Service Unavailable if any check fails
        return JSONResponse(
            content=status,
            status_code=503
        )




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
