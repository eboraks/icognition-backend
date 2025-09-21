"""
Security middleware for access control and authentication
"""

from typing import Optional, Dict, Any, List
from fastapi import Request, Response, HTTPException, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp
import time
import logging
from datetime import datetime, timedelta
from collections import defaultdict, deque

from app.services.base_service import DataIsolationValidator, SecurityError
from app.utils.logging import get_logger

logger = get_logger(__name__)


class SecurityMiddleware(BaseHTTPMiddleware):
    """
    Security middleware for access control, rate limiting, and security monitoring.
    """
    
    def __init__(
        self,
        app: ASGIApp,
        rate_limit_per_minute: int = 60,
        max_failed_attempts: int = 5,
        lockout_duration_minutes: int = 15,
        enable_cors_security: bool = True,
        enable_security_headers: bool = True
    ):
        super().__init__(app)
        self.rate_limit_per_minute = rate_limit_per_minute
        self.max_failed_attempts = max_failed_attempts
        self.lockout_duration_minutes = lockout_duration_minutes
        self.enable_cors_security = enable_cors_security
        self.enable_security_headers = enable_security_headers
        
        # Rate limiting tracking
        self.rate_limit_tracker: Dict[str, deque] = defaultdict(deque)
        
        # Failed attempt tracking
        self.failed_attempts: Dict[str, List[datetime]] = defaultdict(list)
        self.locked_ips: Dict[str, datetime] = {}
        
        # Security event tracking
        self.security_events: List[Dict[str, Any]] = []
    
    async def dispatch(self, request: Request, call_next):
        """Main middleware dispatch method"""
        start_time = time.time()
        
        try:
            # Extract client information
            client_ip = self._get_client_ip(request)
            user_agent = request.headers.get("user-agent", "unknown")
            firebase_uid = self._extract_firebase_uid(request)
            
            # Security checks
            await self._perform_security_checks(request, client_ip, firebase_uid)
            
            # Process request
            response = await call_next(request)
            
            # Add security headers
            if self.enable_security_headers:
                self._add_security_headers(response)
            
            # Log successful request
            self._log_request(request, response, client_ip, firebase_uid, start_time)
            
            return response
            
        except SecurityError as e:
            # Log security violation
            self._log_security_violation(request, str(e), client_ip, firebase_uid)
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={"detail": "Access denied", "error": "security_violation"}
            )
        except HTTPException as e:
            # Log HTTP exceptions
            self._log_http_exception(request, e, client_ip, firebase_uid)
            return JSONResponse(
                status_code=e.status_code,
                content={"detail": e.detail}
            )
        except Exception as e:
            # Log unexpected errors
            logger.error(f"Unexpected error in security middleware: {e}")
            self._log_security_violation(request, f"Unexpected error: {e}", client_ip, firebase_uid)
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={"detail": "Internal server error"}
            )
    
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
    
    async def _perform_security_checks(
        self, 
        request: Request, 
        client_ip: str, 
        firebase_uid: Optional[str]
    ) -> None:
        """Perform comprehensive security checks"""
        
        # Check if IP is locked out
        if self._is_ip_locked(client_ip):
            raise SecurityError(f"IP {client_ip} is temporarily locked due to suspicious activity")
        
        # Rate limiting check
        if not self._check_rate_limit(client_ip):
            raise SecurityError(f"Rate limit exceeded for IP {client_ip}")
        
        # Validate Firebase UID format if present
        if firebase_uid and not DataIsolationValidator.validate_firebase_uid_format(firebase_uid):
            self._record_failed_attempt(client_ip)
            raise SecurityError("Invalid authentication token format")
        
        # Check for suspicious patterns
        self._check_suspicious_patterns(request, client_ip, firebase_uid)
    
    def _is_ip_locked(self, client_ip: str) -> bool:
        """Check if IP is currently locked out"""
        if client_ip in self.locked_ips:
            lockout_time = self.locked_ips[client_ip]
            if datetime.utcnow() < lockout_time:
                return True
            else:
                # Lockout expired, remove it
                del self.locked_ips[client_ip]
        return False
    
    def _check_rate_limit(self, client_ip: str) -> bool:
        """Check if client has exceeded rate limit"""
        now = datetime.utcnow()
        minute_ago = now - timedelta(minutes=1)
        
        # Clean old entries
        while self.rate_limit_tracker[client_ip] and self.rate_limit_tracker[client_ip][0] < minute_ago:
            self.rate_limit_tracker[client_ip].popleft()
        
        # Check if limit exceeded
        if len(self.rate_limit_tracker[client_ip]) >= self.rate_limit_per_minute:
            return False
        
        # Add current request
        self.rate_limit_tracker[client_ip].append(now)
        return True
    
    def _check_suspicious_patterns(
        self, 
        request: Request, 
        client_ip: str, 
        firebase_uid: Optional[str]
    ) -> None:
        """Check for suspicious request patterns"""
        
        # Check for SQL injection patterns
        suspicious_patterns = [
            "union select", "drop table", "delete from", "insert into",
            "update set", "exec(", "script>", "<script", "javascript:",
            "../../", "..\\", "cmd.exe", "powershell"
        ]
        
        # Check URL path
        url_lower = request.url.path.lower()
        for pattern in suspicious_patterns:
            if pattern in url_lower:
                self._record_failed_attempt(client_ip)
                raise SecurityError(f"Suspicious pattern detected in URL: {pattern}")
        
        # Check query parameters
        for param_name, param_value in request.query_params.items():
            param_lower = str(param_value).lower()
            for pattern in suspicious_patterns:
                if pattern in param_lower:
                    self._record_failed_attempt(client_ip)
                    raise SecurityError(f"Suspicious pattern detected in parameter {param_name}: {pattern}")
    
    def _record_failed_attempt(self, client_ip: str) -> None:
        """Record a failed authentication attempt"""
        now = datetime.utcnow()
        self.failed_attempts[client_ip].append(now)
        
        # Clean old attempts (older than lockout duration)
        cutoff_time = now - timedelta(minutes=self.lockout_duration_minutes)
        self.failed_attempts[client_ip] = [
            attempt for attempt in self.failed_attempts[client_ip] 
            if attempt > cutoff_time
        ]
        
        # Check if IP should be locked
        if len(self.failed_attempts[client_ip]) >= self.max_failed_attempts:
            lockout_until = now + timedelta(minutes=self.lockout_duration_minutes)
            self.locked_ips[client_ip] = lockout_until
            
            # Log security violation
            DataIsolationValidator.log_security_violation(
                client_ip, "ip_lockout", 
                f"IP locked due to {len(self.failed_attempts[client_ip])} failed attempts",
                None
            )
    
    def _add_security_headers(self, response: Response) -> None:
        """Add security headers to response"""
        security_headers = {
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "X-XSS-Protection": "1; mode=block",
            "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
            "Referrer-Policy": "strict-origin-when-cross-origin",
            "Content-Security-Policy": "default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; img-src 'self' data: https://fastapi.tiangolo.com;",
            "Permissions-Policy": "geolocation=(), microphone=(), camera=()"
        }
        
        for header, value in security_headers.items():
            response.headers[header] = value
    
    def _log_request(
        self, 
        request: Request, 
        response: Response, 
        client_ip: str, 
        firebase_uid: Optional[str], 
        start_time: float
    ) -> None:
        """Log successful request"""
        duration = time.time() - start_time
        
        log_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "method": request.method,
            "url": str(request.url),
            "client_ip": client_ip,
            "firebase_uid": firebase_uid,
            "status_code": response.status_code,
            "duration_ms": round(duration * 1000, 2),
            "user_agent": request.headers.get("user-agent", "unknown")
        }
        
        logger.info(f"REQUEST: {log_entry}")
    
    def _log_security_violation(
        self, 
        request: Request, 
        violation: str, 
        client_ip: str, 
        firebase_uid: Optional[str]
    ) -> None:
        """Log security violation"""
        log_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "violation_type": "security_violation",
            "violation": violation,
            "method": request.method,
            "url": str(request.url),
            "client_ip": client_ip,
            "firebase_uid": firebase_uid,
            "user_agent": request.headers.get("user-agent", "unknown")
        }
        
        DataIsolationValidator.log_security_violation(
            client_ip, "security_violation", violation, None
        )
        logger.warning(f"SECURITY VIOLATION: {log_entry}")
    
    def _log_http_exception(
        self, 
        request: Request, 
        exception: HTTPException, 
        client_ip: str, 
        firebase_uid: Optional[str]
    ) -> None:
        """Log HTTP exception"""
        log_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "exception_type": "http_exception",
            "status_code": exception.status_code,
            "detail": exception.detail,
            "method": request.method,
            "url": str(request.url),
            "client_ip": client_ip,
            "firebase_uid": firebase_uid
        }
        
        logger.warning(f"HTTP EXCEPTION: {log_entry}")


class WebSocketSecurityMiddleware:
    """
    Security middleware specifically for WebSocket connections.
    """
    
    def __init__(self, max_connections_per_user: int = 5):
        self.max_connections_per_user = max_connections_per_user
        self.user_connections: Dict[str, int] = defaultdict(int)
        self.connection_tracker: Dict[str, datetime] = {}
    
    async def authenticate_websocket(
        self, 
        websocket, 
        firebase_uid: Optional[str] = None
    ) -> Optional[str]:
        """
        Authenticate WebSocket connection and return Firebase UID.
        """
        try:
            # Extract Firebase UID from WebSocket headers or query params
            if not firebase_uid:
                firebase_uid = websocket.headers.get("X-Firebase-UID")
            
            if not firebase_uid:
                # Try query parameters
                firebase_uid = websocket.query_params.get("firebase_uid")
            
            if not firebase_uid:
                await websocket.close(code=4001, reason="Authentication required")
                return None
            
            # Validate Firebase UID format
            if not DataIsolationValidator.validate_firebase_uid_format(firebase_uid):
                await websocket.close(code=4002, reason="Invalid authentication token")
                return None
            
            # Check connection limits
            if self.user_connections[firebase_uid] >= self.max_connections_per_user:
                await websocket.close(code=4003, reason="Too many connections")
                return None
            
            # Track connection
            self.user_connections[firebase_uid] += 1
            self.connection_tracker[f"{firebase_uid}_{id(websocket)}"] = datetime.utcnow()
            
            # Log successful WebSocket authentication
            DataIsolationValidator.log_data_access(
                firebase_uid, "websocket_connect", "websocket", None
            )
            
            return firebase_uid
            
        except Exception as e:
            logger.error(f"WebSocket authentication error: {e}")
            await websocket.close(code=4000, reason="Authentication error")
            return None
    
    def disconnect_websocket(self, firebase_uid: str, websocket) -> None:
        """Track WebSocket disconnection"""
        if firebase_uid in self.user_connections:
            self.user_connections[firebase_uid] = max(0, self.user_connections[firebase_uid] - 1)
        
        connection_key = f"{firebase_uid}_{id(websocket)}"
        if connection_key in self.connection_tracker:
            del self.connection_tracker[connection_key]
        
        # Log WebSocket disconnection
        DataIsolationValidator.log_data_access(
            firebase_uid, "websocket_disconnect", "websocket", None
        )


# Global WebSocket security instance
websocket_security = WebSocketSecurityMiddleware()
