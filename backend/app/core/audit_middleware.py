"""
Audit logging middleware for automatic security event logging
"""

from typing import Optional, Dict, Any
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp
import time
import logging

from app.core.audit_logging import audit_logger, AuditEventType, log_api_request
from app.core.security_middleware import SecurityMiddleware
from app.utils.logging import get_logger

logger = get_logger(__name__)


class AuditLoggingMiddleware(BaseHTTPMiddleware):
    """
    Middleware for automatic audit logging of API requests and responses.
    """
    
    def __init__(
        self,
        app: ASGIApp,
        log_requests: bool = True,
        log_responses: bool = True,
        log_errors: bool = True,
        exclude_paths: Optional[list] = None
    ):
        super().__init__(app)
        self.log_requests = log_requests
        self.log_responses = log_responses
        self.log_errors = log_errors
        self.exclude_paths = exclude_paths or [
            "/health",
            "/ping",
            "/docs",
            "/redoc",
            "/openapi.json",
            "/favicon.ico"
        ]
    
    async def dispatch(self, request: Request, call_next):
        """Main middleware dispatch method"""
        start_time = time.time()
        
        # Skip logging for excluded paths
        if request.url.path in self.exclude_paths:
            return await call_next(request)
        
        # Extract request information
        client_ip = self._get_client_ip(request)
        user_agent = request.headers.get("user-agent", "unknown")
        firebase_uid = self._extract_firebase_uid(request)
        
        # Log request
        if self.log_requests:
            log_api_request(
                user_id=firebase_uid,
                endpoint=request.url.path,
                method=request.method,
                ip_address=client_ip,
                user_agent=user_agent,
                success=True  # Will be updated if there's an error
            )
        
        try:
            # Process request
            response = await call_next(request)
            
            # Log successful response
            if self.log_responses:
                duration = time.time() - start_time
                audit_logger.log_event(
                    event_type=AuditEventType.API_RESPONSE,
                    user_id=firebase_uid,
                    ip_address=client_ip,
                    user_agent=user_agent,
                    action=f"{request.method} {request.url.path}",
                    details={
                        "endpoint": request.url.path,
                        "method": request.method,
                        "status_code": response.status_code,
                        "duration_ms": round(duration * 1000, 2),
                        "response_size": response.headers.get("content-length", "unknown")
                    },
                    success=response.status_code < 400
                )
            
            return response
            
        except Exception as e:
            # Log error
            if self.log_errors:
                duration = time.time() - start_time
                audit_logger.log_event(
                    event_type=AuditEventType.API_ERROR,
                    user_id=firebase_uid,
                    ip_address=client_ip,
                    user_agent=user_agent,
                    action=f"{request.method} {request.url.path}",
                    details={
                        "endpoint": request.url.path,
                        "method": request.method,
                        "error_type": type(e).__name__,
                        "duration_ms": round(duration * 1000, 2)
                    },
                    success=False,
                    error_message=str(e)
                )
            
            # Re-raise the exception
            raise
    
    def _get_client_ip(self, request: Request) -> str:
        """Extract client IP address"""
        # Check for forwarded headers (for reverse proxy setups)
        forwarded_for = request.headers.get("x-forwarded-for")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()
        
        real_ip = request.headers.get("x-real-ip")
        if real_ip:
            return real_ip
        
        # Fallback to direct connection IP
        return request.client.host if request.client else "unknown"
    
    def _extract_firebase_uid(self, request: Request) -> Optional[str]:
        """Extract Firebase UID from request headers"""
        # Try Authorization header first
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            # For now, assume the token contains the Firebase UID
            # In production, this would validate the Firebase token
            return auth_header.split(" ")[1]
        
        # Try custom header
        return request.headers.get("X-Firebase-UID")


class SecurityAuditMiddleware(BaseHTTPMiddleware):
    """
    Middleware for logging security-relevant events.
    """
    
    def __init__(self, app: ASGIApp):
        super().__init__(app)
    
    async def dispatch(self, request: Request, call_next):
        """Main middleware dispatch method"""
        client_ip = self._get_client_ip(request)
        firebase_uid = self._extract_firebase_uid(request)
        
        try:
            response = await call_next(request)
            
            # Log security-relevant events based on response status
            if response.status_code == 401:
                audit_logger.log_event(
                    event_type=AuditEventType.AUTHENTICATION_FAILED,
                    user_id=firebase_uid,
                    ip_address=client_ip,
                    action="authentication_failed",
                    details={
                        "endpoint": request.url.path,
                        "method": request.method,
                        "reason": "Invalid or missing authentication"
                    },
                    success=False
                )
            elif response.status_code == 403:
                audit_logger.log_event(
                    event_type=AuditEventType.SECURITY_VIOLATION,
                    user_id=firebase_uid,
                    ip_address=client_ip,
                    action="access_denied",
                    details={
                        "endpoint": request.url.path,
                        "method": request.method,
                        "reason": "Insufficient permissions"
                    },
                    success=False
                )
            elif response.status_code == 429:
                audit_logger.log_event(
                    event_type=AuditEventType.RATE_LIMIT_EXCEEDED,
                    user_id=firebase_uid,
                    ip_address=client_ip,
                    action="rate_limit_exceeded",
                    details={
                        "endpoint": request.url.path,
                        "method": request.method,
                        "reason": "Rate limit exceeded"
                    },
                    success=False
                )
            
            return response
            
        except Exception as e:
            # Log unexpected errors as security events
            audit_logger.log_event(
                event_type=AuditEventType.SECURITY_VIOLATION,
                user_id=firebase_uid,
                ip_address=client_ip,
                action="unexpected_error",
                details={
                    "endpoint": request.url.path,
                    "method": request.method,
                    "error_type": type(e).__name__
                },
                success=False,
                error_message=str(e)
            )
            
            # Re-raise the exception
            raise
    
    def _get_client_ip(self, request: Request) -> str:
        """Extract client IP address"""
        forwarded_for = request.headers.get("x-forwarded-for")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()
        
        real_ip = request.headers.get("x-real-ip")
        if real_ip:
            return real_ip
        
        return request.client.host if request.client else "unknown"
    
    def _extract_firebase_uid(self, request: Request) -> Optional[str]:
        """Extract Firebase UID from request headers"""
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            return auth_header.split(" ")[1]
        
        return request.headers.get("X-Firebase-UID")


# Integration with existing security components
def integrate_audit_logging_with_security():
    """
    Integrate audit logging with existing security components.
    This function should be called during application startup.
    """
    logger.info("Integrating audit logging with security components")
    
    # The audit logging is already integrated through:
    # 1. SecurityMiddleware - logs security violations
    # 2. UserIsolatedService - logs data access events
    # 3. DocumentOwnershipVerifier - logs ownership verification events
    # 4. SecurityAuditor - logs security events
    
    logger.info("Audit logging integration completed")
