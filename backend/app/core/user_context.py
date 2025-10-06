"""
User context management for request handling with Firebase authentication
"""

from typing import Optional, Dict, Any
from fastapi import Request, HTTPException, status, Depends
from sqlalchemy.ext.asyncio import AsyncSession
import logging

from app.models import User
from app.db.database import get_session
from app.services.user_service import UserService
from app.utils.logging import get_logger
from app.core.config import settings
from app.core.firebase_auth import firebase_auth

logger = get_logger(__name__)


class UserContext:
    """User context for request handling"""
    
    def __init__(self, user: Optional[User] = None):
        self.user = user
        self.is_authenticated = user is not None
    
    @property
    def user_id(self) -> Optional[str]:
        """Get user ID if authenticated"""
        return self.user.id if self.user else None
    
    @property
    def email(self) -> Optional[str]:
        """Get user email if authenticated"""
        return self.user.email if self.user else None
    
    @property
    def display_name(self) -> Optional[str]:
        """Get user display name if authenticated"""
        return self.user.display_name if self.user else None


class UserContextManager:
    """Manager for handling user context in requests"""
    
    @staticmethod
    async def get_user_from_request(
        request: Request,
        session: AsyncSession,
        firebase_uid: Optional[str] = None
    ) -> UserContext:
        """
        Extract user context from request using Firebase authentication.
        """
        try:
            decoded_token = None
            
            if not firebase_uid:
                # Try to get from Authorization header and verify Firebase token
                auth_header = request.headers.get("Authorization")
                if auth_header and auth_header.startswith("Bearer "):
                    id_token = auth_header.split(" ")[1]
                    try:
                        # Verify Firebase ID token
                        decoded_token = await firebase_auth.verify_id_token(id_token)
                        firebase_uid = decoded_token.get("uid")
                        logger.info(f"Successfully verified Firebase token for user: {firebase_uid}")
                    except HTTPException as e:
                        # Token verification failed
                        logger.warning(f"Firebase token verification failed: {e.detail}")
                        return UserContext()
                else:
                    # Try to get from custom header (fallback for testing)
                    firebase_uid = request.headers.get("X-Firebase-UID")
                    if firebase_uid:
                        logger.info(f"Using Firebase UID from custom header: {firebase_uid}")
            
            if not firebase_uid:
                logger.debug("No Firebase UID found in request")
                return UserContext()
            
            # Get or create user in local database
            user = await UserService.get_or_create_user(
                session=session,
                firebase_uid=firebase_uid,
                email=decoded_token.get("email") if decoded_token else None,
                display_name=decoded_token.get("name") if decoded_token else None,
                photo_url=decoded_token.get("picture") if decoded_token else None,
                email_verified=decoded_token.get("email_verified", False) if decoded_token else False
            )
            
            if not user:
                logger.error(f"Failed to get or create user for Firebase UID: {firebase_uid}")
                return UserContext()
            
            return UserContext(user=user)
            
        except Exception as e:
            logger.error(f"Error getting user from request: {e}")
            return UserContext()
    
    @staticmethod
    def require_authentication(user_context: UserContext) -> None:
        """Require user to be authenticated, raise HTTPException if not"""
        # Skip authentication if DISABLE_AUTH is enabled
        if settings.DISABLE_AUTH:
            logger.warning("Authentication is disabled via DISABLE_AUTH flag")
            return
            
        if not user_context.is_authenticated:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required"
            )
    
    @staticmethod
    def require_active_user(user_context: UserContext) -> None:
        """Require user to be active, raise HTTPException if not"""
        UserContextManager.require_authentication(user_context)
        
        # Skip active check if auth is disabled
        if settings.DISABLE_AUTH:
            return
            
        if not user_context.user or not user_context.user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User account is deactivated"
            )


# Dependency for FastAPI
async def get_user_context(
    request: Request,
    session: AsyncSession = Depends(get_session)
) -> UserContext:
    """FastAPI dependency to get user context"""
    return await UserContextManager.get_user_from_request(request, session)


async def get_authenticated_user_context(
    request: Request,
    session: AsyncSession = Depends(get_session)
) -> UserContext:
    """FastAPI dependency to get authenticated user context"""
    user_context = await UserContextManager.get_user_from_request(request, session)
    
    # If auth is disabled, create a default test user context
    if settings.DISABLE_AUTH:
        logger.warning("Creating default test user context (DISABLE_AUTH enabled)")
        
        # Create a simple mock user object for testing
        class MockUser:
            def __init__(self):
                self.id = "test_user_12345"  # Simple test user ID
                self.email = "test@example.com"
                self.name = "Test User"
                self.is_active = True
        
        mock_user = MockUser()
        user_context = UserContext(user=mock_user)
    
    UserContextManager.require_authentication(user_context)
    return user_context


async def get_active_user_context(
    request: Request,
    session: AsyncSession = Depends(get_session)
) -> UserContext:
    """FastAPI dependency to get active user context"""
    user_context = await UserContextManager.get_user_from_request(request, session)
    
    # If auth is disabled, create a default test user context
    if settings.DISABLE_AUTH:
        logger.warning("Creating default test user context (DISABLE_AUTH enabled)")
        
        # Create a simple mock user object for testing
        class MockUser:
            def __init__(self):
                self.id = "test_user_12345"  # Simple test user ID
                self.email = "test@example.com"
                self.name = "Test User"
                self.is_active = True
        
        mock_user = MockUser()
        user_context = UserContext(user=mock_user)
    
    UserContextManager.require_active_user(user_context)
    return user_context
