"""
Bookmark service for managing bookmark operations with automatic user creation
"""

from typing import Optional, List, Dict, Any
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete, func
from sqlalchemy.exc import IntegrityError
import logging

from app.services.user_service import UserService
from app.models import Bookmark, User, Document, ChatSession, ChatMessage, EntityDocument, EntityRelationship
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
        """
        Delete bookmark AND cascade delete associated document and chats if no other bookmarks use it.
        """
        try:
            # 1. Get the bookmark first to identify document
            stmt = select(Bookmark).where(
                Bookmark.id == bookmark_id,
                Bookmark.user_id == firebase_uid
            )
            result = await session.execute(stmt)
            bookmark = result.scalar_one_or_none()
            
            if not bookmark:
                logger.warning(f"Bookmark {bookmark_id} not found for deletion.")
                return False
            
            document_id = bookmark.document_id
            
            # 2. Delete the bookmark
            await session.delete(bookmark)
            await session.flush() # Ensure delete is registered for count check
            
            # 3. If linked to a document, check if we should cascade delete
            if document_id:
                # Check if any other bookmarks reference this document
                # (Documents are user-specific, so we check only this document ID)
                count_stmt = select(func.count(Bookmark.id)).where(Bookmark.document_id == document_id)
                count_result = await session.execute(count_stmt)
                remaining_bookmarks = count_result.scalar() or 0
                
                if remaining_bookmarks == 0:
                    logger.info(f"Cascading delete for document {document_id} and associated resources")
                    
                    # A. Delete associated ChatSessions (scoped to this document)
                    chat_stmt = select(ChatSession.id).where(
                        ChatSession.scope_type == 'document',
                        ChatSession.scope_id == document_id
                    )
                    chat_result = await session.execute(chat_stmt)
                    session_ids = chat_result.scalars().all()
                    
                    if session_ids:
                        # Delete messages first
                        await session.execute(
                            delete(ChatMessage).where(ChatMessage.session_id.in_(session_ids))
                        )
                        # Delete sessions
                        await session.execute(
                            delete(ChatSession).where(ChatSession.id.in_(session_ids))
                        )
                        logger.info(f"Deleted {len(session_ids)} chat sessions for document {document_id}")
                    
                    # B. Delete EntityDocument links
                    await session.execute(
                        delete(EntityDocument).where(EntityDocument.document_id == document_id)
                    )

                    # C. Delete EntityRelationship rows sourced from this document
                    await session.execute(
                        delete(EntityRelationship).where(EntityRelationship.source_document_id == document_id)
                    )

                    # D. Delete the Document itself
                    await session.execute(
                        delete(Document).where(Document.id == document_id)
                    )
                    logger.info(f"Deleted document {document_id}")
                else:
                    logger.info(f"Document {document_id} preserved (used by {remaining_bookmarks} other bookmarks)")

            await session.commit()
            return True
            
        except Exception as e:
            await session.rollback()
            logger.error(f"Error executing cascading delete for bookmark {bookmark_id}: {e}")
            return False
    
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
