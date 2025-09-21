"""
iCognition Backend API
Modern FastAPI application with async support and proper structure
"""

import logging
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
from app.api.errors import (
    api_error_handler,
    http_error_handler, 
    validation_error_handler,
    APIError
)
from app.api.routes import users, bookmarks, documents
from app.utils.logging import get_logger

# Configure logging
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager for startup and shutdown events"""
    # Startup: Initialize resources
    logger.info("Starting up iCognition API")
    
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

# Add audit logging middleware
app.add_middleware(AuditLoggingMiddleware)
app.add_middleware(SecurityAuditMiddleware)

# Register exception handlers
app.add_exception_handler(APIError, api_error_handler)
app.add_exception_handler(Exception, http_error_handler)
app.add_exception_handler(RequestValidationError, validation_error_handler)

# Register API routes
app.include_router(users.router, prefix="/api/v1")
app.include_router(bookmarks.router)
app.include_router(documents.router, prefix="/api/v1")


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


@app.get("/security/status")
async def security_status():
    """Security status endpoint for monitoring"""
    from app.core.security_config import security_auditor
    
    return {
        "security_enabled": True,
        "rate_limiting_enabled": security_config.enable_security_headers,
        "audit_logging_enabled": security_config.log_security_violations,
        "recent_audit_summary": security_auditor.get_audit_summary(hours=1)
    }


@app.get("/audit/events")
async def get_audit_events(
    hours: int = 24,
    limit: int = 100,
    user_context: UserContext = Depends(get_authenticated_user_context)
):
    """Get recent audit events (admin only)"""
    if not user_context.is_authenticated:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required"
        )
    
    # TODO: Add admin role check here
    # For now, allow any authenticated user to view audit events
    
    start_time = datetime.utcnow() - timedelta(hours=hours)
    events = audit_logger.get_events(start_time=start_time, limit=limit)
    
    return {
        "timeframe_hours": hours,
        "total_events": len(events),
        "events": [event.to_dict() for event in events]
    }


@app.get("/audit/user-activity/{user_id}")
async def get_user_activity(
    user_id: str,
    hours: int = 24,
    user_context: UserContext = Depends(get_authenticated_user_context)
):
    """Get user activity summary"""
    if not user_context.is_authenticated:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required"
        )
    
    # Users can only view their own activity
    if user_context.firebase_uid != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: Can only view own activity"
        )
    
    activity_summary = audit_logger.get_user_activity_summary(user_id, hours)
    return activity_summary


@app.get("/audit/security-summary")
async def get_security_summary(
    hours: int = 24,
    user_context: UserContext = Depends(get_authenticated_user_context)
):
    """Get security summary (admin only)"""
    if not user_context.is_authenticated:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required"
        )
    
    # TODO: Add admin role check here
    # For now, allow any authenticated user to view security summary
    
    security_summary = audit_logger.get_security_summary(hours)
    return security_summary


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level=settings.LOG_LEVEL.lower()
    )
