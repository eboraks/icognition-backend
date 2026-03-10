"""
Security configuration and utilities
"""

from typing import Optional, Dict, Any, List
from pydantic_settings import BaseSettings
from pydantic import ConfigDict
from enum import Enum
from datetime import datetime, timedelta
from collections import defaultdict
import logging

from app.utils.logging import get_logger

logger = get_logger(__name__)


class SecurityLevel(str, Enum):
    """Security levels for different operations"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class SecurityConfig(BaseSettings):
    """Security configuration settings"""
    
    # Rate limiting
    rate_limit_per_minute: int = 300
    rate_limit_burst: int = 30
    
    # Authentication
    max_failed_attempts: int = 5
    lockout_duration_minutes: int = 15
    session_timeout_minutes: int = 30
    
    # WebSocket security
    max_websocket_connections_per_user: int = 5
    websocket_ping_interval: int = 30
    
    # Security headers
    enable_security_headers: bool = True
    enable_cors_security: bool = True
    enable_csrf_protection: bool = True
    
    # Logging
    enable_security_logging: bool = True
    log_security_violations: bool = True
    log_data_access: bool = True
    
    # Encryption
    enable_data_encryption: bool = True
    encryption_key_length: int = 32
    
    # Firebase
    firebase_project_id: Optional[str] = None
    firebase_private_key: Optional[str] = None
    firebase_client_email: Optional[str] = None
    
    model_config = ConfigDict(
        env_prefix="SECURITY_",
        case_sensitive=False
    )


class SecurityPolicy:
    """Security policy definitions"""
    
    def __init__(self, config: SecurityConfig):
        self.config = config
        self.policies = self._initialize_policies()
    
    def _initialize_policies(self) -> Dict[str, Dict[str, Any]]:
        """Initialize security policies"""
        return {
            "api_access": {
                "rate_limit": self.config.rate_limit_per_minute,
                "max_failed_attempts": self.config.max_failed_attempts,
                "lockout_duration": self.config.lockout_duration_minutes,
                "security_level": SecurityLevel.MEDIUM
            },
            "websocket_access": {
                "max_connections": self.config.max_websocket_connections_per_user,
                "ping_interval": self.config.websocket_ping_interval,
                "security_level": SecurityLevel.HIGH
            },
            "data_access": {
                "enable_encryption": self.config.enable_data_encryption,
                "audit_logging": self.config.log_data_access,
                "security_level": SecurityLevel.CRITICAL
            },
            "authentication": {
                "session_timeout": self.config.session_timeout_minutes,
                "max_failed_attempts": self.config.max_failed_attempts,
                "security_level": SecurityLevel.CRITICAL
            }
        }
    
    def get_policy(self, policy_name: str) -> Dict[str, Any]:
        """Get security policy by name"""
        return self.policies.get(policy_name, {})
    
    def is_policy_enabled(self, policy_name: str) -> bool:
        """Check if a security policy is enabled"""
        policy = self.get_policy(policy_name)
        return policy.get("enabled", True)
    
    def get_security_level(self, policy_name: str) -> SecurityLevel:
        """Get security level for a policy"""
        policy = self.get_policy(policy_name)
        return policy.get("security_level", SecurityLevel.MEDIUM)


class SecurityAuditor:
    """Security audit and monitoring utilities"""
    
    def __init__(self, config: SecurityConfig):
        self.config = config
        self.audit_log: List[Dict[str, Any]] = []
        self.violation_log: List[Dict[str, Any]] = []
    
    def log_security_event(
        self,
        event_type: str,
        user_id: Optional[str],
        details: Dict[str, Any],
        security_level: SecurityLevel = SecurityLevel.MEDIUM
    ) -> None:
        """Log a security event"""
        if not self.config.enable_security_logging:
            return
        
        event = {
            "timestamp": datetime.utcnow().isoformat(),
            "event_type": event_type,
            "user_id": user_id,
            "details": details,
            "security_level": security_level.value
        }
        
        self.audit_log.append(event)
        
        # Log based on security level
        if security_level == SecurityLevel.CRITICAL:
            logger.critical(f"SECURITY EVENT: {event}")
        elif security_level == SecurityLevel.HIGH:
            logger.error(f"SECURITY EVENT: {event}")
        elif security_level == SecurityLevel.MEDIUM:
            logger.warning(f"SECURITY EVENT: {event}")
        else:
            logger.info(f"SECURITY EVENT: {event}")
    
    def log_security_violation(
        self,
        violation_type: str,
        user_id: Optional[str],
        details: Dict[str, Any],
        severity: str = "medium"
    ) -> None:
        """Log a security violation"""
        if not self.config.log_security_violations:
            return
        
        violation = {
            "timestamp": datetime.utcnow().isoformat(),
            "violation_type": violation_type,
            "user_id": user_id,
            "details": details,
            "severity": severity
        }
        
        self.violation_log.append(violation)
        logger.error(f"SECURITY VIOLATION: {violation}")
    
    def get_audit_summary(self, hours: int = 24) -> Dict[str, Any]:
        """Get audit summary for the last N hours"""
        cutoff_time = datetime.utcnow() - timedelta(hours=hours)
        
        recent_events = [
            event for event in self.audit_log
            if datetime.fromisoformat(event["timestamp"]) > cutoff_time
        ]
        
        recent_violations = [
            violation for violation in self.violation_log
            if datetime.fromisoformat(violation["timestamp"]) > cutoff_time
        ]
        
        return {
            "timeframe_hours": hours,
            "total_events": len(recent_events),
            "total_violations": len(recent_violations),
            "events_by_type": self._count_by_type(recent_events, "event_type"),
            "violations_by_type": self._count_by_type(recent_violations, "violation_type"),
            "events_by_security_level": self._count_by_type(recent_events, "security_level")
        }
    
    def _count_by_type(self, items: List[Dict[str, Any]], field: str) -> Dict[str, int]:
        """Count items by a specific field"""
        counts = defaultdict(int)
        for item in items:
            counts[item.get(field, "unknown")] += 1
        return dict(counts)


class SecurityValidator:
    """Security validation utilities"""
    
    @staticmethod
    def validate_firebase_uid(firebase_uid: str) -> bool:
        """Validate Firebase UID format"""
        if not firebase_uid or not isinstance(firebase_uid, str):
            return False
        
        # Firebase UID should be 28 characters, alphanumeric
        if len(firebase_uid) != 28:
            return False
        
        # Should contain only alphanumeric characters and hyphens/underscores
        if not firebase_uid.replace('-', '').replace('_', '').isalnum():
            return False
        
        return True
    
    @staticmethod
    def validate_email(email: str) -> bool:
        """Validate email format"""
        import re
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return re.match(pattern, email) is not None
    
    @staticmethod
    def validate_password_strength(password: str) -> Dict[str, Any]:
        """Validate password strength"""
        result = {
            "is_valid": True,
            "score": 0,
            "issues": []
        }
        
        if len(password) < 8:
            result["issues"].append("Password must be at least 8 characters long")
            result["is_valid"] = False
        
        if not any(c.isupper() for c in password):
            result["issues"].append("Password must contain at least one uppercase letter")
            result["score"] += 1
        
        if not any(c.islower() for c in password):
            result["issues"].append("Password must contain at least one lowercase letter")
            result["score"] += 1
        
        if not any(c.isdigit() for c in password):
            result["issues"].append("Password must contain at least one number")
            result["score"] += 1
        
        if not any(c in "!@#$%^&*()_+-=[]{}|;:,.<>?" for c in password):
            result["issues"].append("Password must contain at least one special character")
            result["score"] += 1
        
        # Calculate final score
        result["score"] = min(5, result["score"] + (len(password) // 2))
        
        return result
    
    @staticmethod
    def sanitize_input(input_string: str) -> str:
        """Sanitize user input to prevent injection attacks"""
        if not isinstance(input_string, str):
            return str(input_string)
        
        # Remove or escape potentially dangerous characters
        dangerous_chars = ['<', '>', '"', "'", '&', ';', '(', ')', '|', '`', '$']
        sanitized = input_string
        
        for char in dangerous_chars:
            sanitized = sanitized.replace(char, '')
        
        return sanitized.strip()


# Global security configuration
security_config = SecurityConfig()
security_policy = SecurityPolicy(security_config)
security_auditor = SecurityAuditor(security_config)
security_validator = SecurityValidator()
