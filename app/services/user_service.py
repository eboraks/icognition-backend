"""
User service for managing user operations and automatic user creation
"""

from typing import Optional, Dict, Any
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
import logging

from app.db.models import User
from app.utils.logging import get_logger

logger = get_logger(__name__)


class UserService:
    """Service class for user management operations"""
    
    @staticmethod
    async def get_user_by_firebase_uid(session: AsyncSession, firebase_uid: str) -> Optional[User]:
        """Get user by Firebase UID"""
        try:
            result = await session.execute(
                select(User).where(User.firebase_uid == firebase_uid)
            )
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Error getting user by Firebase UID {firebase_uid}: {e}")
            return None
    
    @staticmethod
    async def get_user_by_email(session: AsyncSession, email: str) -> Optional[User]:
        """Get user by email"""
        try:
            result = await session.execute(
                select(User).where(User.email == email)
            )
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Error getting user by email {email}: {e}")
            return None
    
    @staticmethod
    async def create_user(
        session: AsyncSession,
        firebase_uid: str,
        email: Optional[str] = None,
        display_name: Optional[str] = None,
        photo_url: Optional[str] = None,
        preferences: Optional[Dict[str, Any]] = None
    ) -> Optional[User]:
        """Create a new user with automatic timestamp handling"""
        try:
            now = datetime.utcnow()
            user = User(
                firebase_uid=firebase_uid,
                email=email,
                display_name=display_name,
                photo_url=photo_url,
                preferences=preferences or {},
                is_active=True,
                is_verified=False,
                first_login=now,
                last_login=now,
                last_active=now
            )
            
            session.add(user)
            await session.commit()
            await session.refresh(user)
            
            logger.info(f"Created new user with Firebase UID: {firebase_uid}")
            return user
            
        except IntegrityError as e:
            await session.rollback()
            logger.warning(f"User with Firebase UID {firebase_uid} already exists: {e}")
            return None
        except Exception as e:
            await session.rollback()
            logger.error(f"Error creating user with Firebase UID {firebase_uid}: {e}")
            return None
    
    @staticmethod
    async def get_or_create_user(
        session: AsyncSession,
        firebase_uid: str,
        email: Optional[str] = None,
        display_name: Optional[str] = None,
        photo_url: Optional[str] = None,
        preferences: Optional[Dict[str, Any]] = None
    ) -> Optional[User]:
        """
        Get existing user or create new one if not exists.
        This is the main function for automatic user creation on first bookmark.
        """
        try:
            # First, try to get existing user
            user = await UserService.get_user_by_firebase_uid(session, firebase_uid)
            
            if user:
                # Update last_active timestamp
                await UserService.update_last_active(session, user.id)
                return user
            
            # User doesn't exist, create new one
            logger.info(f"User with Firebase UID {firebase_uid} not found, creating new user")
            return await UserService.create_user(
                session=session,
                firebase_uid=firebase_uid,
                email=email,
                display_name=display_name,
                photo_url=photo_url,
                preferences=preferences
            )
            
        except Exception as e:
            logger.error(f"Error in get_or_create_user for Firebase UID {firebase_uid}: {e}")
            return None
    
    @staticmethod
    async def update_last_active(session: AsyncSession, user_id: int) -> bool:
        """Update user's last_active timestamp"""
        try:
            await session.execute(
                update(User)
                .where(User.id == user_id)
                .values(last_active=datetime.utcnow())
            )
            await session.commit()
            return True
        except Exception as e:
            logger.error(f"Error updating last_active for user {user_id}: {e}")
            return False
    
    @staticmethod
    async def update_last_login(session: AsyncSession, user_id: int) -> bool:
        """Update user's last_login timestamp"""
        try:
            await session.execute(
                update(User)
                .where(User.id == user_id)
                .values(last_login=datetime.utcnow())
            )
            await session.commit()
            return True
        except Exception as e:
            logger.error(f"Error updating last_login for user {user_id}: {e}")
            return False
    
    @staticmethod
    async def update_user_profile(
        session: AsyncSession,
        user_id: int,
        email: Optional[str] = None,
        display_name: Optional[str] = None,
        photo_url: Optional[str] = None,
        preferences: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Update user profile information"""
        try:
            update_data = {}
            if email is not None:
                update_data['email'] = email
            if display_name is not None:
                update_data['display_name'] = display_name
            if photo_url is not None:
                update_data['photo_url'] = photo_url
            if preferences is not None:
                update_data['preferences'] = preferences
            
            if update_data:
                update_data['updated_at'] = datetime.utcnow()
                await session.execute(
                    update(User)
                    .where(User.id == user_id)
                    .values(**update_data)
                )
                await session.commit()
            
            return True
        except Exception as e:
            logger.error(f"Error updating user profile for user {user_id}: {e}")
            return False
    
    @staticmethod
    async def deactivate_user(session: AsyncSession, user_id: int) -> bool:
        """Deactivate user account"""
        try:
            await session.execute(
                update(User)
                .where(User.id == user_id)
                .values(is_active=False, updated_at=datetime.utcnow())
            )
            await session.commit()
            return True
        except Exception as e:
            logger.error(f"Error deactivating user {user_id}: {e}")
            return False
