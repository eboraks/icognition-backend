"""
Comprehensive audit logging system for security-relevant operations
"""

from typing import Optional, Dict, Any, List, Union
from datetime import datetime, timedelta
from enum import Enum
from dataclasses import dataclass, asdict
import json
import logging
from collections import defaultdict, deque
import asyncio
from pathlib import Path

from app.core.security_config import security_auditor, SecurityLevel
from app.utils.logging import get_logger

logger = get_logger(__name__)


class AuditEventType(str, Enum):
    """Types of audit events"""
    # Authentication events
    USER_LOGIN = "user_login"
    USER_LOGOUT = "user_logout"
    USER_CREATED = "user_created"
    AUTHENTICATION_FAILED = "authentication_failed"
    
    # Data access events
    DATA_ACCESS = "data_access"
    DATA_CREATED = "data_created"
    DATA_UPDATED = "data_updated"
    DATA_DELETED = "data_deleted"
    DATA_EXPORTED = "data_exported"
    
    # Security events
    SECURITY_VIOLATION = "security_violation"
    RATE_LIMIT_EXCEEDED = "rate_limit_exceeded"
    SUSPICIOUS_ACTIVITY = "suspicious_activity"
    IP_BLOCKED = "ip_blocked"
    
    # System events
    SYSTEM_STARTUP = "system_startup"
    SYSTEM_SHUTDOWN = "system_shutdown"
    CONFIGURATION_CHANGED = "configuration_changed"
    
    # Document events
    DOCUMENT_ACCESSED = "document_accessed"
    DOCUMENT_CREATED = "document_created"
    DOCUMENT_UPDATED = "document_updated"
    DOCUMENT_DELETED = "document_deleted"
    DOCUMENT_SHARED = "document_shared"
    
    # API events
    API_REQUEST = "api_request"
    API_RESPONSE = "api_response"
    API_ERROR = "api_error"


class AuditSeverity(str, Enum):
    """Severity levels for audit events"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class AuditEvent:
    """Audit event data structure"""
    timestamp: datetime
    event_type: AuditEventType
    severity: AuditSeverity
    user_id: Optional[str]
    session_id: Optional[str]
    ip_address: Optional[str]
    user_agent: Optional[str]
    resource_type: Optional[str]
    resource_id: Optional[str]
    action: str
    details: Dict[str, Any]
    success: bool
    error_message: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        data = asdict(self)
        data['timestamp'] = self.timestamp.isoformat()
        return data


class AuditLogger:
    """
    Comprehensive audit logging system for security-relevant operations.
    """
    
    def __init__(
        self,
        max_events: int = 10000,
        retention_days: int = 90,
        enable_file_logging: bool = True,
        log_file_path: Optional[str] = None
    ):
        self.max_events = max_events
        self.retention_days = retention_days
        self.enable_file_logging = enable_file_logging
        self.log_file_path = log_file_path or "logs/audit.log"
        
        # In-memory event storage
        self.events: deque = deque(maxlen=max_events)
        self.event_counts: Dict[str, int] = defaultdict(int)
        self.user_activity: Dict[str, List[datetime]] = defaultdict(list)
        
        # File logging setup
        if self.enable_file_logging:
            self._setup_file_logging()
    
    def _setup_file_logging(self) -> None:
        """Setup file logging for audit events"""
        try:
            # Create logs directory if it doesn't exist
            log_path = Path(self.log_file_path)
            log_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Setup file handler
            file_handler = logging.FileHandler(log_path)
            file_handler.setLevel(logging.INFO)
            
            # Create formatter
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            file_handler.setFormatter(formatter)
            
            # Add handler to audit logger
            audit_logger = logging.getLogger('audit')
            audit_logger.addHandler(file_handler)
            audit_logger.setLevel(logging.INFO)
            
        except Exception as e:
            logger.error(f"Failed to setup file logging: {e}")
    
    def log_event(
        self,
        event_type: AuditEventType,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        action: str = "",
        details: Optional[Dict[str, Any]] = None,
        success: bool = True,
        error_message: Optional[str] = None,
        severity: Optional[AuditSeverity] = None
    ) -> None:
        """
        Log an audit event.
        
        Args:
            event_type: Type of audit event
            user_id: User ID associated with the event
            session_id: Session ID associated with the event
            ip_address: IP address of the client
            user_agent: User agent string
            resource_type: Type of resource being accessed
            resource_id: ID of the resource being accessed
            action: Action being performed
            details: Additional details about the event
            success: Whether the action was successful
            error_message: Error message if the action failed
            severity: Severity level of the event
        """
        # Determine severity if not provided
        if severity is None:
            severity = self._determine_severity(event_type, success)
        
        # Create audit event
        event = AuditEvent(
            timestamp=datetime.utcnow(),
            event_type=event_type,
            severity=severity,
            user_id=user_id,
            session_id=session_id,
            ip_address=ip_address,
            user_agent=user_agent,
            resource_type=resource_type,
            resource_id=resource_id,
            action=action,
            details=details or {},
            success=success,
            error_message=error_message
        )
        
        # Store event
        self.events.append(event)
        self.event_counts[event_type.value] += 1
        
        # Track user activity
        if user_id:
            self.user_activity[user_id].append(event.timestamp)
            # Keep only recent activity (last 24 hours)
            cutoff = datetime.utcnow() - timedelta(hours=24)
            self.user_activity[user_id] = [
                activity for activity in self.user_activity[user_id]
                if activity > cutoff
            ]
        
        # Log to file if enabled
        if self.enable_file_logging:
            self._log_to_file(event)
        
        # Log to console based on severity
        self._log_to_console(event)
    
    def _determine_severity(
        self, 
        event_type: AuditEventType, 
        success: bool
    ) -> AuditSeverity:
        """Determine severity level based on event type and success"""
        if not success:
            if event_type in [
                AuditEventType.AUTHENTICATION_FAILED,
                AuditEventType.SECURITY_VIOLATION,
                AuditEventType.SUSPICIOUS_ACTIVITY
            ]:
                return AuditSeverity.HIGH
            else:
                return AuditSeverity.MEDIUM
        
        if event_type in [
            AuditEventType.DATA_DELETED,
            AuditEventType.CONFIGURATION_CHANGED,
            AuditEventType.SYSTEM_SHUTDOWN
        ]:
            return AuditSeverity.HIGH
        
        if event_type in [
            AuditEventType.DATA_CREATED,
            AuditEventType.DATA_UPDATED,
            AuditEventType.USER_CREATED
        ]:
            return AuditSeverity.MEDIUM
        
        return AuditSeverity.LOW
    
    def _log_to_file(self, event: AuditEvent) -> None:
        """Log event to file"""
        try:
            audit_logger = logging.getLogger('audit')
            audit_logger.info(json.dumps(event.to_dict()))
        except Exception as e:
            logger.error(f"Failed to log audit event to file: {e}")
    
    def _log_to_console(self, event: AuditEvent) -> None:
        """Log event to console based on severity"""
        log_message = f"AUDIT: {event.event_type.value} - {event.action}"
        if event.user_id:
            log_message += f" (User: {event.user_id})"
        if event.resource_type and event.resource_id:
            log_message += f" (Resource: {event.resource_type}:{event.resource_id})"
        if not event.success:
            log_message += f" - FAILED: {event.error_message}"
        
        if event.severity == AuditSeverity.CRITICAL:
            logger.critical(log_message)
        elif event.severity == AuditSeverity.HIGH:
            logger.error(log_message)
        elif event.severity == AuditSeverity.MEDIUM:
            logger.warning(log_message)
        else:
            logger.info(log_message)
    
    def get_events(
        self,
        event_type: Optional[AuditEventType] = None,
        user_id: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 100
    ) -> List[AuditEvent]:
        """
        Get audit events with optional filtering.
        
        Args:
            event_type: Filter by event type
            user_id: Filter by user ID
            start_time: Filter events after this time
            end_time: Filter events before this time
            limit: Maximum number of events to return
        
        Returns:
            List of audit events matching the criteria
        """
        filtered_events = []
        
        for event in reversed(self.events):  # Most recent first
            if len(filtered_events) >= limit:
                break
            
            # Apply filters
            if event_type and event.event_type != event_type:
                continue
            
            if user_id and event.user_id != user_id:
                continue
            
            if start_time and event.timestamp < start_time:
                continue
            
            if end_time and event.timestamp > end_time:
                continue
            
            filtered_events.append(event)
        
        return filtered_events
    
    def get_user_activity_summary(
        self, 
        user_id: str, 
        hours: int = 24
    ) -> Dict[str, Any]:
        """
        Get user activity summary for the last N hours.
        
        Args:
            user_id: User ID to get summary for
            hours: Number of hours to look back
        
        Returns:
            Dictionary with activity summary
        """
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        
        # Get recent events for user
        recent_events = self.get_events(
            user_id=user_id,
            start_time=cutoff
        )
        
        # Count events by type
        event_counts = defaultdict(int)
        for event in recent_events:
            event_counts[event.event_type.value] += 1
        
        # Get activity timestamps
        activity_timestamps = [
            activity for activity in self.user_activity.get(user_id, [])
            if activity > cutoff
        ]
        
        return {
            "user_id": user_id,
            "timeframe_hours": hours,
            "total_events": len(recent_events),
            "event_counts": dict(event_counts),
            "activity_timestamps": [ts.isoformat() for ts in activity_timestamps],
            "last_activity": activity_timestamps[-1].isoformat() if activity_timestamps else None
        }
    
    def get_security_summary(self, hours: int = 24) -> Dict[str, Any]:
        """
        Get security summary for the last N hours.
        
        Args:
            hours: Number of hours to look back
        
        Returns:
            Dictionary with security summary
        """
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        
        # Get recent security events
        security_events = self.get_events(
            start_time=cutoff,
            limit=1000
        )
        
        # Filter security-relevant events
        security_relevant = [
            event for event in security_events
            if event.event_type in [
                AuditEventType.SECURITY_VIOLATION,
                AuditEventType.AUTHENTICATION_FAILED,
                AuditEventType.RATE_LIMIT_EXCEEDED,
                AuditEventType.SUSPICIOUS_ACTIVITY,
                AuditEventType.IP_BLOCKED
            ]
        ]
        
        # Count by severity
        severity_counts = defaultdict(int)
        for event in security_relevant:
            severity_counts[event.severity.value] += 1
        
        # Count by event type
        event_type_counts = defaultdict(int)
        for event in security_relevant:
            event_type_counts[event.event_type.value] += 1
        
        return {
            "timeframe_hours": hours,
            "total_security_events": len(security_relevant),
            "severity_breakdown": dict(severity_counts),
            "event_type_breakdown": dict(event_type_counts),
            "critical_events": len([
                event for event in security_relevant
                if event.severity == AuditSeverity.CRITICAL
            ])
        }
    
    def cleanup_old_events(self) -> None:
        """Clean up old events based on retention policy"""
        cutoff = datetime.utcnow() - timedelta(days=self.retention_days)
        
        # Remove old events
        while self.events and self.events[0].timestamp < cutoff:
            self.events.popleft()
        
        # Clean up old user activity
        for user_id in list(self.user_activity.keys()):
            self.user_activity[user_id] = [
                activity for activity in self.user_activity[user_id]
                if activity > cutoff
            ]
            
            # Remove empty entries
            if not self.user_activity[user_id]:
                del self.user_activity[user_id]


# Global audit logger instance
audit_logger = AuditLogger()


# Convenience functions for common audit operations
def log_user_login(
    user_id: str,
    ip_address: str,
    user_agent: str,
    success: bool = True,
    error_message: Optional[str] = None
) -> None:
    """Log user login event"""
    audit_logger.log_event(
        event_type=AuditEventType.USER_LOGIN,
        user_id=user_id,
        ip_address=ip_address,
        user_agent=user_agent,
        action="user_login",
        success=success,
        error_message=error_message
    )


def log_data_access(
    user_id: str,
    resource_type: str,
    resource_id: str,
    action: str,
    ip_address: Optional[str] = None,
    success: bool = True,
    error_message: Optional[str] = None
) -> None:
    """Log data access event"""
    audit_logger.log_event(
        event_type=AuditEventType.DATA_ACCESS,
        user_id=user_id,
        resource_type=resource_type,
        resource_id=resource_id,
        action=action,
        ip_address=ip_address,
        success=success,
        error_message=error_message
    )


def log_security_violation(
    user_id: Optional[str],
    violation_type: str,
    ip_address: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None
) -> None:
    """Log security violation event"""
    audit_logger.log_event(
        event_type=AuditEventType.SECURITY_VIOLATION,
        user_id=user_id,
        ip_address=ip_address,
        action=violation_type,
        details=details or {},
        success=False,
        severity=AuditSeverity.HIGH
    )


def log_api_request(
    user_id: Optional[str],
    endpoint: str,
    method: str,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
    success: bool = True,
    status_code: Optional[int] = None
) -> None:
    """Log API request event"""
    audit_logger.log_event(
        event_type=AuditEventType.API_REQUEST,
        user_id=user_id,
        ip_address=ip_address,
        user_agent=user_agent,
        action=f"{method} {endpoint}",
        details={
            "endpoint": endpoint,
            "method": method,
            "status_code": status_code
        },
        success=success
    )
