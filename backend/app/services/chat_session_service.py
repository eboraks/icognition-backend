from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from app.db.database import get_session
from app.models import ChatSession, ChatMessage
from typing import List, Optional
from fastapi import Depends
from datetime import datetime, timezone
from app.utils.chat_formatting import format_chat_message, process_source_tags
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

class ChatSessionService:
    """
    Service for managing chat sessions.
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_chat_session(self, user_id: str, title: str, scope_type: str, scope_id: Optional[int]) -> ChatSession:
        """
        Create a new chat session.
        """
        chat_session = ChatSession(
            user_id=user_id,
            title=title,
            scope_type=scope_type,
            scope_id=scope_id
        )
        try:
            self.session.add(chat_session)
            await self.session.commit()
            await self.session.refresh(chat_session)
            return chat_session
        except Exception as e:
            raise

    async def get_user_sessions(self, user_id: str) -> List[ChatSession]:
        """
        Get all chat sessions for a user.
        """
        stmt = select(ChatSession)
        if not settings.DISABLE_AUTH:
            stmt = stmt.where(ChatSession.user_id == user_id)
        
        stmt = stmt.order_by(ChatSession.updated_at.desc(), ChatSession.id.desc())
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_session_messages(self, session_id: int, user_id: str) -> List[ChatMessage]:
        """
        Get all messages for a chat session.
        Raises ValueError if the session doesn't exist or doesn't belong to the user.
        """
        session = await self.get_session_by_id(session_id, user_id)
        if not session:
            logger.warning(
                "User %s attempted to access messages for session %s they do not own or that does not exist",
                user_id,
                session_id,
            )
            raise ValueError(f"Chat session {session_id} not found or not owned by user")

        stmt = (
            select(ChatMessage)
            .join(ChatSession, ChatSession.id == ChatMessage.session_id)
            .where(ChatSession.id == session_id)
        )
        if not settings.DISABLE_AUTH:
            stmt = stmt.where(ChatSession.user_id == user_id)
        
        stmt = stmt.order_by(ChatMessage.created_at, ChatMessage.id)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_session_by_id(self, session_id: int, user_id: str) -> Optional[ChatSession]:
        stmt = select(ChatSession).where(ChatSession.id == session_id)
        if not settings.DISABLE_AUTH:
            stmt = stmt.where(ChatSession.user_id == user_id)
            
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_session_by_scope(self, user_id: str, scope_type: str, scope_id: int) -> Optional[ChatSession]:
        """
        Find an existing chat session for a specific scope.
        Always filters by user_id to prevent returning another user's session
        (even when DISABLE_AUTH is true, the user_id is consistent as test_user_12345).
        """
        stmt = select(ChatSession).where(
            ChatSession.scope_type == scope_type,
            ChatSession.scope_id == scope_id,
            ChatSession.user_id == user_id,
        )

        # Order by updated_at to get the most recent one if multiple exist (though ideally there's only one)
        stmt = stmt.order_by(ChatSession.updated_at.desc())
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def save_message(self, session_id: int, role: str, content: str) -> ChatMessage:
        """
        Save a message to a chat session.
        """
        has_prior_user_message = True
        if role == "user":
            prior_user_stmt = (
                select(ChatMessage.id)
                .where(ChatMessage.session_id == session_id)
                .where(ChatMessage.role == "user")
                .limit(1)
            )
            prior_user_result = await self.session.execute(prior_user_stmt)
            has_prior_user_message = prior_user_result.first() is not None

        chat_session = await self.session.get(ChatSession, session_id)
        if not chat_session:
            logger.error("Attempted to save message to missing session %s", session_id)
            raise ValueError("Chat session not found")

        # Assistant messages are rendered by the frontend via marked.js — store
        # raw markdown so headings, code blocks, tables, etc. render correctly.
        # Only apply source-tag → interactive HTML conversion so citation
        # buttons still work. User messages still go through full HTML
        # escaping (format_chat_message) because the frontend inserts them via
        # v-html without a markdown parser.
        raw = content or ""
        if role == "assistant":
            formatted_content = process_source_tags(raw)
        else:
            formatted_content = format_chat_message(raw)

        try:
            logger.info(f"Database: Attempting to save {role} message for session {session_id}")
            message = ChatMessage(
                session_id=session_id,
                role=role,  # "user" or "assistant"
                content=formatted_content
            )
            self.session.add(message)

            if role == "user" and not has_prior_user_message:
                new_title = (content or "").strip()[:60]
                chat_session.title = new_title or chat_session.title
                logger.debug(f"Database: Updating session title to: {new_title}")

            chat_session.updated_at = datetime.now(timezone.utc)

            await self.session.commit()
            await self.session.refresh(message)
            logger.info(f"Database: Successfully committed {role} message (ID: {message.id}) to session {session_id}")
            return message
        except Exception as e:
            logger.error(f"Database: Error saving {role} message to session {session_id}: {e}", exc_info=True)
            await self.session.rollback()
            raise

    async def delete_session(self, session_id: int, user_id: str):
        """
        Delete a chat session and all its messages.
        """
        try:
            logger.info(f"Deleting chat session {session_id} for user {user_id}")
            
            # First delete all messages in the session using bulk delete
            delete_messages_stmt = delete(ChatMessage).where(ChatMessage.session_id == session_id)
            messages_result = await self.session.execute(delete_messages_stmt)
            messages_deleted = messages_result.rowcount
            logger.info(f"Deleted {messages_deleted} messages for session {session_id}")
            
            # Then delete the session itself using direct DELETE statement
            # This is more reliable than session.delete() as it executes the SQL directly
            delete_session_stmt = delete(ChatSession).where(ChatSession.id == session_id)
            if not settings.DISABLE_AUTH:
                delete_session_stmt = delete_session_stmt.where(ChatSession.user_id == user_id)
            
            session_result = await self.session.execute(delete_session_stmt)
            sessions_deleted = session_result.rowcount
            logger.info(f"Deleted {sessions_deleted} session(s) for session_id {session_id}")
            
            if sessions_deleted == 0:
                logger.warning(f"No session was deleted - session {session_id} may have already been deleted or doesn't belong to user {user_id}")
                await self.session.rollback()
                return False
            
            # Commit the deletion
            await self.session.commit()
            logger.info(f"Successfully committed deletion of chat session {session_id} and {messages_deleted} messages")
            
            return True
        except Exception as e:
            logger.error(f"Error deleting chat session {session_id}: {e}", exc_info=True)
            await self.session.rollback()
            raise

    async def update_session_title(self, session_id: int, user_id: str, title: str) -> Optional[ChatSession]:
        stmt = select(ChatSession).where(ChatSession.id == session_id)
        if not settings.DISABLE_AUTH:
            stmt = stmt.where(ChatSession.user_id == user_id)
            
        result = await self.session.execute(stmt)
        chat_session = result.scalar_one_or_none()
        if not chat_session:
            return None
        chat_session.title = title
        await self.session.commit()
        await self.session.refresh(chat_session)
        return chat_session

def get_chat_session_service(session: AsyncSession = Depends(get_session)) -> ChatSessionService:
    """
    Dependency injector for ChatSessionService.
    """
    return ChatSessionService(session)
