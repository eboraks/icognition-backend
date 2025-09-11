"""
Bookmark service for managing bookmark operations with automatic user creation
"""

from typing import Optional, List, Dict, Any
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete
from sqlalchemy.exc import IntegrityError
import logging

from app.db.models import Bookmark, User
from app.services.user_service import UserService
from app.services.base_service import UserIsolatedService, DataIsolationValidator
from app.utils.logging import get_logger

logger = get_logger(__name__)


class BookmarkService(UserIsolatedService[Bookmark]):
    """Service class for bookmark management operations with enforced user isolation"""
    
    def __init__(self):
        super().__init__(Bookmark)
    
    @staticmethod
    async def create_bookmark(
        session: AsyncSession,
        firebase_uid: str,
        url: str,
        title: str,
        description: Optional[str] = None,
        content: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Optional[Bookmark]:
        """
        Create a new bookmark with automatic user creation.
        This is the main function that demonstrates automatic user creation on first bookmark.
        """
        try:
            # First, get or create the user (this is the key automatic user creation)
            user = await UserService.get_or_create_user(
                session=session,
                firebase_uid=firebase_uid
            )
            
            if not user:
                logger.error(f"Failed to get or create user for Firebase UID: {firebase_uid}")
                return None
            
            # Create the bookmark
            bookmark = Bookmark(
                user_id=user.id,
                url=url,
                title=title,
                description=description,
                content=content,
                bookmark_metadata=metadata or {},
                is_processed=False,
                processing_status="pending"
            )
            
            session.add(bookmark)
            await session.commit()
            await session.refresh(bookmark)
            
            logger.info(f"Created bookmark {bookmark.id} for user {user.id} (Firebase UID: {firebase_uid})")
            return bookmark
            
        except IntegrityError as e:
            await session.rollback()
            logger.error(f"Integrity error creating bookmark for Firebase UID {firebase_uid}: {e}")
            return None
        except Exception as e:
            await session.rollback()
            logger.error(f"Error creating bookmark for Firebase UID {firebase_uid}: {e}")
            return None
    
    async def get_user_bookmarks(
        self,
        session: AsyncSession,
        firebase_uid: str,
        limit: int = 50,
        offset: int = 0,
        is_processed: Optional[bool] = None
    ) -> List[Bookmark]:
        """Get bookmarks for a specific user with optional filters"""
        filters = {}
        if is_processed is not None:
            filters['is_processed'] = is_processed
        
        return await self.get_user_records(
            session=session,
            firebase_uid=firebase_uid,
            limit=limit,
            offset=offset,
            **filters
        )
    
    async def get_bookmark_by_id(
        self,
        session: AsyncSession,
        bookmark_id: int,
        firebase_uid: str
    ) -> Optional[Bookmark]:
        """Get a specific bookmark by ID, ensuring user ownership"""
        return await self.get_user_record_by_id(
            session=session,
            record_id=bookmark_id,
            firebase_uid=firebase_uid
        )
    
    async def update_bookmark(
        self,
        session: AsyncSession,
        bookmark_id: int,
        firebase_uid: str,
        title: Optional[str] = None,
        description: Optional[str] = None,
        content: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        is_processed: Optional[bool] = None,
        processing_status: Optional[str] = None
    ) -> bool:
        """Update bookmark, ensuring user ownership"""
        update_data = {}
        if title is not None:
            update_data['title'] = title
        if description is not None:
            update_data['description'] = description
        if content is not None:
            update_data['content'] = content
        if metadata is not None:
            update_data['bookmark_metadata'] = metadata
        if is_processed is not None:
            update_data['is_processed'] = is_processed
        if processing_status is not None:
            update_data['processing_status'] = processing_status
        
        if update_data:
            update_data['updated_at'] = datetime.utcnow()
        
        return await self.update_user_record(
            session=session,
            record_id=bookmark_id,
            firebase_uid=firebase_uid,
            **update_data
        )
    
    async def delete_bookmark(
        self,
        session: AsyncSession,
        bookmark_id: int,
        firebase_uid: str
    ) -> bool:
        """Delete bookmark, ensuring user ownership"""
        return await self.delete_user_record(
            session=session,
            record_id=bookmark_id,
            firebase_uid=firebase_uid
        )
    
    async def count_user_bookmarks(
        self,
        session: AsyncSession,
        firebase_uid: str,
        is_processed: Optional[bool] = None
    ) -> int:
        """Count bookmarks for a specific user with optional filters"""
        filters = {}
        if is_processed is not None:
            filters['is_processed'] = is_processed
        
        return await self.count_user_records(
            session=session,
            firebase_uid=firebase_uid,
            **filters
        )
    
    async def get_bookmarks_by_url(
        self,
        session: AsyncSession,
        firebase_uid: str,
        url: str
    ) -> List[Bookmark]:
        """Get bookmarks by URL for a specific user"""
        return await self.get_user_records(
            session=session,
            firebase_uid=firebase_uid,
            url=url
        )
    
    async def mark_bookmark_processed(
        self,
        session: AsyncSession,
        bookmark_id: int,
        firebase_uid: str,
        processing_status: str = "completed"
    ) -> bool:
        """Mark bookmark as processed, ensuring user ownership"""
        return await self.update_bookmark(
            session=session,
            bookmark_id=bookmark_id,
            firebase_uid=firebase_uid,
            is_processed=True,
            processing_status=processing_status
        )
