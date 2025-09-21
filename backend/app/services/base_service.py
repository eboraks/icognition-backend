"""
Base service class for enforcing user-specific data isolation and security
"""

from typing import Optional, TypeVar, Generic, List, Any, Dict, Union
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete, and_
from sqlalchemy.orm import DeclarativeBase
import logging
from datetime import datetime
import traceback

from app.services.user_service import UserService
from app.utils.logging import get_logger

logger = get_logger(__name__)

T = TypeVar('T', bound=DeclarativeBase)


class SecurityError(Exception):
    """Custom exception for security-related errors"""
    pass


class UserIsolatedService(Generic[T]):
    """
    Base service class that enforces user-specific data isolation and security.
    All derived services must ensure that data operations are scoped to the authenticated user.
    """
    
    def __init__(self, model_class: type[T]):
        self.model_class = model_class
        self._validate_model_has_user_id()
    
    def _validate_model_has_user_id(self) -> None:
        """Validate that the model has a user_id field for data isolation"""
        if not hasattr(self.model_class, 'user_id'):
            raise ValueError(f"Model {self.model_class.__name__} must have a 'user_id' field for data isolation")
    
    async def _get_user_id(self, session: AsyncSession, firebase_uid: str) -> Optional[int]:
        """Get user ID from Firebase UID with enhanced error handling"""
        try:
            user = await UserService.get_user_by_firebase_uid(session, firebase_uid)
            if user:
                # Log successful user resolution
                DataIsolationValidator.log_data_access(
                    firebase_uid, "user_resolution", "user", user.id
                )
                return user.id
            return None
        except Exception as e:
            logger.error(f"Error resolving user ID for Firebase UID {firebase_uid}: {e}")
            DataIsolationValidator.log_data_access(
                firebase_uid, "user_resolution_failed", "user", None
            )
            return None
    
    async def _ensure_user_isolation(
        self, 
        session: AsyncSession, 
        firebase_uid: str,
        operation: str = "access"
    ) -> int:
        """
        Ensure user exists and return user_id for data isolation.
        Raises SecurityError if user not found.
        """
        user_id = await self._get_user_id(session, firebase_uid)
        if not user_id:
            error_msg = f"User not found for Firebase UID: {firebase_uid}"
            logger.warning(f"Security violation: {error_msg} during {operation}")
            DataIsolationValidator.log_data_access(
                firebase_uid, f"unauthorized_{operation}", self.model_class.__name__, None
            )
            raise SecurityError(error_msg)
        return user_id
    
    async def get_user_records(
        self,
        session: AsyncSession,
        firebase_uid: str,
        limit: int = 50,
        offset: int = 0,
        **filters
    ) -> List[T]:
        """
        Get records for a specific user with optional filters.
        This is the base method that all user-scoped queries should use.
        """
        try:
            user_id = await self._ensure_user_isolation(session, firebase_uid, "get_records")
            
            # Build query with user isolation
            query = select(self.model_class).where(
                getattr(self.model_class, 'user_id') == user_id
            )
            
            # Apply additional filters
            for key, value in filters.items():
                if hasattr(self.model_class, key) and value is not None:
                    query = query.where(getattr(self.model_class, key) == value)
            
            # Apply pagination
            query = query.limit(limit).offset(offset)
            
            result = await session.execute(query)
            records = result.scalars().all()
            
            # Log successful data access
            DataIsolationValidator.log_data_access(
                firebase_uid, "get_records", self.model_class.__name__, 
                f"count:{len(records)}"
            )
            
            return records
            
        except SecurityError:
            # Re-raise security errors
            raise
        except Exception as e:
            logger.error(f"Error getting user records for Firebase UID {firebase_uid}: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            DataIsolationValidator.log_data_access(
                firebase_uid, "get_records_failed", self.model_class.__name__, None
            )
            return []
    
    async def get_user_record_by_id(
        self,
        session: AsyncSession,
        record_id: int,
        firebase_uid: str
    ) -> Optional[T]:
        """
        Get a specific record by ID, ensuring user ownership.
        This prevents users from accessing other users' data.
        """
        try:
            user_id = await self._ensure_user_isolation(session, firebase_uid, "get_record")
            
            result = await session.execute(
                select(self.model_class)
                .where(self.model_class.id == record_id)
                .where(getattr(self.model_class, 'user_id') == user_id)
            )
            
            record = result.scalar_one_or_none()
            
            if record:
                # Log successful data access
                DataIsolationValidator.log_data_access(
                    firebase_uid, "get_record", self.model_class.__name__, record_id
                )
            else:
                # Log attempted access to non-existent or unauthorized record
                DataIsolationValidator.log_data_access(
                    firebase_uid, "get_record_not_found", self.model_class.__name__, record_id
                )
            
            return record
            
        except SecurityError:
            # Re-raise security errors
            raise
        except Exception as e:
            logger.error(f"Error getting record {record_id} for Firebase UID {firebase_uid}: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            DataIsolationValidator.log_data_access(
                firebase_uid, "get_record_failed", self.model_class.__name__, record_id
            )
            return None
    
    async def update_user_record(
        self,
        session: AsyncSession,
        record_id: int,
        firebase_uid: str,
        **update_data
    ) -> bool:
        """
        Update a record, ensuring user ownership.
        This prevents users from modifying other users' data.
        """
        try:
            user_id = await self._ensure_user_isolation(session, firebase_uid, "update_record")
            
            # Remove user_id from update_data if present (should not be updatable)
            update_data.pop('user_id', None)
            
            if not update_data:
                logger.warning(f"No update data provided for record {record_id}")
                return False
            
            # Check if record exists and belongs to user before updating
            existing_record = await self.get_user_record_by_id(session, record_id, firebase_uid)
            if not existing_record:
                DataIsolationValidator.log_data_access(
                    firebase_uid, "update_record_not_found", self.model_class.__name__, record_id
                )
                return False
            
            await session.execute(
                update(self.model_class)
                .where(self.model_class.id == record_id)
                .where(getattr(self.model_class, 'user_id') == user_id)
                .values(**update_data)
            )
            await session.commit()
            
            # Log successful update
            DataIsolationValidator.log_data_access(
                firebase_uid, "update_record", self.model_class.__name__, record_id
            )
            
            return True
            
        except SecurityError:
            # Re-raise security errors
            raise
        except Exception as e:
            logger.error(f"Error updating record {record_id} for Firebase UID {firebase_uid}: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            DataIsolationValidator.log_data_access(
                firebase_uid, "update_record_failed", self.model_class.__name__, record_id
            )
            return False
    
    async def delete_user_record(
        self,
        session: AsyncSession,
        record_id: int,
        firebase_uid: str
    ) -> bool:
        """
        Delete a record, ensuring user ownership.
        This prevents users from deleting other users' data.
        """
        try:
            user_id = await self._ensure_user_isolation(session, firebase_uid, "delete_record")
            
            # Check if record exists and belongs to user before deleting
            existing_record = await self.get_user_record_by_id(session, record_id, firebase_uid)
            if not existing_record:
                DataIsolationValidator.log_data_access(
                    firebase_uid, "delete_record_not_found", self.model_class.__name__, record_id
                )
                return False
            
            await session.execute(
                delete(self.model_class)
                .where(self.model_class.id == record_id)
                .where(getattr(self.model_class, 'user_id') == user_id)
            )
            await session.commit()
            
            # Log successful deletion
            DataIsolationValidator.log_data_access(
                firebase_uid, "delete_record", self.model_class.__name__, record_id
            )
            
            logger.info(f"Deleted record {record_id} for user {user_id}")
            return True
            
        except SecurityError:
            # Re-raise security errors
            raise
        except Exception as e:
            logger.error(f"Error deleting record {record_id} for Firebase UID {firebase_uid}: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            DataIsolationValidator.log_data_access(
                firebase_uid, "delete_record_failed", self.model_class.__name__, record_id
            )
            return False
    
    async def count_user_records(
        self,
        session: AsyncSession,
        firebase_uid: str,
        **filters
    ) -> int:
        """
        Count records for a specific user with optional filters.
        Useful for pagination and statistics.
        """
        try:
            user_id = await self._ensure_user_isolation(session, firebase_uid, "count_records")
            
            # Build query with user isolation
            query = select(self.model_class).where(
                getattr(self.model_class, 'user_id') == user_id
            )
            
            # Apply additional filters
            for key, value in filters.items():
                if hasattr(self.model_class, key) and value is not None:
                    query = query.where(getattr(self.model_class, key) == value)
            
            result = await session.execute(query)
            count = len(result.scalars().all())
            
            # Log successful count operation
            DataIsolationValidator.log_data_access(
                firebase_uid, "count_records", self.model_class.__name__, f"count:{count}"
            )
            
            return count
            
        except SecurityError:
            # Re-raise security errors
            raise
        except Exception as e:
            logger.error(f"Error counting records for Firebase UID {firebase_uid}: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            DataIsolationValidator.log_data_access(
                firebase_uid, "count_records_failed", self.model_class.__name__, None
            )
            return 0
    
    async def verify_record_ownership(
        self,
        session: AsyncSession,
        record_id: int,
        firebase_uid: str
    ) -> bool:
        """
        Verify that a record belongs to the specified user.
        Returns True if the record exists and belongs to the user, False otherwise.
        """
        try:
            record = await self.get_user_record_by_id(session, record_id, firebase_uid)
            return record is not None
        except SecurityError:
            return False
        except Exception as e:
            logger.error(f"Error verifying ownership for record {record_id}: {e}")
            return False
    
    async def get_user_record_count_by_status(
        self,
        session: AsyncSession,
        firebase_uid: str,
        status: str
    ) -> int:
        """
        Get count of user records with a specific status.
        Useful for dashboard statistics and monitoring.
        """
        return await self.count_user_records(session, firebase_uid, status=status)


class DataIsolationValidator:
    """
    Utility class for validating data isolation in database operations and security auditing.
    This can be used to audit and ensure that all queries properly isolate user data.
    """
    
    @staticmethod
    def validate_user_isolation_query(query_str: str, firebase_uid: str) -> bool:
        """
        Validate that a query string contains proper user isolation.
        This is a basic validation - in production, you'd want more sophisticated analysis.
        """
        # Check for user_id filter
        if 'user_id' not in query_str.lower():
            logger.warning(f"SECURITY WARNING: Query may not have user isolation: {query_str}")
            DataIsolationValidator.log_data_access(
                firebase_uid, "query_validation_failed", "query", None
            )
            return False
        
        # Check for proper WHERE clause
        if 'where' not in query_str.lower():
            logger.warning(f"SECURITY WARNING: Query may not have WHERE clause: {query_str}")
            DataIsolationValidator.log_data_access(
                firebase_uid, "query_validation_failed", "query", None
            )
            return False
        
        return True
    
    @staticmethod
    def log_data_access(
        firebase_uid: str,
        operation: str,
        resource_type: str,
        resource_id: Optional[Union[int, str]] = None
    ) -> None:
        """
        Log data access for audit purposes with enhanced security information.
        """
        timestamp = datetime.utcnow().isoformat()
        log_entry = {
            "timestamp": timestamp,
            "firebase_uid": firebase_uid,
            "operation": operation,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "security_level": "audit"
        }
        
        # Log at appropriate level based on operation type
        if "failed" in operation or "unauthorized" in operation:
            logger.warning(f"SECURITY AUDIT: {log_entry}")
        elif "delete" in operation or "update" in operation:
            logger.info(f"SECURITY AUDIT: {log_entry}")
        else:
            logger.debug(f"SECURITY AUDIT: {log_entry}")
    
    @staticmethod
    def log_security_violation(
        firebase_uid: str,
        violation_type: str,
        details: str,
        resource_id: Optional[Union[int, str]] = None
    ) -> None:
        """
        Log security violations for immediate attention and monitoring.
        """
        timestamp = datetime.utcnow().isoformat()
        log_entry = {
            "timestamp": timestamp,
            "firebase_uid": firebase_uid,
            "violation_type": violation_type,
            "details": details,
            "resource_id": resource_id,
            "security_level": "violation"
        }
        
        logger.error(f"SECURITY VIOLATION: {log_entry}")
    
    @staticmethod
    def validate_firebase_uid_format(firebase_uid: str) -> bool:
        """
        Validate Firebase UID format for basic security checks.
        """
        if not firebase_uid or not isinstance(firebase_uid, str):
            return False
        
        # Basic Firebase UID format validation (28 characters, alphanumeric)
        if len(firebase_uid) != 28:
            return False
        
        if not firebase_uid.replace('-', '').replace('_', '').isalnum():
            return False
        
        return True
