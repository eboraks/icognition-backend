import json
import time
import asyncio
import logging
from typing import Dict, Optional, Tuple, Union
from datetime import datetime, timedelta
from app.gemini_chat_client import ChatClient
from app.models import Chat_Message, EventName
from app.response_models import Answer
import app.getters as getters
from uuid import UUID

logger = logging.getLogger(__name__)

class ChatSession:
    def __init__(self, user_id: str, context_id: str, context_type: str = "document", system_instruction: str = None):
        """
        Initialize a chat session
        
        Args:
            user_id: The user ID
            context_id: Document ID or Collection ID
            context_type: "document" or "collection"
            system_instruction: Optional system instruction for the chat client
        """
        self.user_id = user_id
        self.context_id = context_id
        self.context_type = context_type
        self.created_at = datetime.now()
        self.last_activity = datetime.now()
        
        # Load system instruction if not provided
        if not system_instruction:
            try:
                with open("app/chat_workflows/chat_system_instructions.txt", "r") as f:
                    system_instruction = f.read()
            except Exception as e:
                logger.error(f"Error loading system instruction: {str(e)}")
                system_instruction = "You are a helpful assistant."
        
        # Load context data
        if context_type == "document":
            self.context_data = getters.get_document_by_id(context_id)
        else:  # collection
            self.context_data = getters.get_study_collection_by_id(context_id)
        
        # Load chat history
        chat_history = None
        try:
            # Get all chat history for this context
            chat_history = getters.get_chat_history(context_id)
            
            # Sort by creation time to ensure proper order
            chat_history.sort(key=lambda x: x.created_at)
            logger.info(f"Loaded {len(chat_history)} messages from chat history for context {context_id}")
        except Exception as e:
            logger.error(f"Error loading chat history: {str(e)}")
        
        # Initialize chat client with history
        self.chat_client = ChatClient(
            response_model=Answer, 
            system_instruction=system_instruction,
            chat_history=chat_history
        )

    
    def update_activity(self):
        """Update the last activity timestamp"""
        self.last_activity = datetime.now()
    
    def is_expired(self, timeout_minutes: int = 30) -> bool:
        """Check if the session has expired"""
        return datetime.now() > self.last_activity + timedelta(minutes=timeout_minutes)
    
    


class ChatSessionManager:
    """Manages chat sessions for multiple users"""
    
    def __init__(self, session_timeout_minutes: int = 30, cleanup_interval_minutes: int = 5):
        # Dictionary to store chat sessions: {(user_id, context_id, context_type): ChatSession}
        self._sessions: Dict[Tuple[str, str, str], ChatSession] = {}
        self._session_timeout_minutes = session_timeout_minutes
        self._cleanup_interval_minutes = cleanup_interval_minutes
        self._cleanup_task = None
    
    def start_cleanup_task(self):
        """Start the background task to clean up expired sessions"""
        if self._cleanup_task is None:
            self._cleanup_task = asyncio.create_task(self._cleanup_expired_sessions())
    
    async def _cleanup_expired_sessions(self):
        """Background task to clean up expired sessions"""
        while True:
            try:
                # Find expired sessions
                expired_keys = [
                    key for key, session in self._sessions.items() 
                    if session.is_expired(self._session_timeout_minutes)
                ]
                
                # Remove expired sessions
                for key in expired_keys:
                    logger.info(f"Removing expired session for user {key[0]}, context {key[1]}")
                    del self._sessions[key]
                
                # Log current session count
                logger.debug(f"Active chat sessions: {len(self._sessions)}")
                
            except Exception as e:
                logger.error(f"Error in cleanup task: {str(e)}")
            
            # Sleep for the cleanup interval
            await asyncio.sleep(self._cleanup_interval_minutes * 60)
    
    def get_session(self, user_id: str, context_id: str, context_type: str = "document") -> Optional[ChatSession]:
        """Get an existing chat session or None if it doesn't exist"""
        key = (user_id, context_id, context_type)
        return self._sessions.get(key)
    
    def create_session(self, user_id: str, context_id: str, context_type: str = "document", system_instruction: str = None) -> ChatSession:
        """Create a new chat session"""
        key = (user_id, context_id, context_type)
        session = ChatSession(user_id, context_id, context_type, system_instruction)
        self._sessions[key] = session
        return session
    
    def get_or_create_session(self, user_id: str, context_id: str, context_type: str = "document", system_instruction: str = None) -> ChatSession:
        """Get an existing chat session or create a new one if it doesn't exist"""
        session = self.get_session(user_id, context_id, context_type)
        if session is None:
            session = self.create_session(user_id, context_id, context_type, system_instruction)
        return session
    
    def remove_session(self, user_id: str, context_id: str, context_type: str = "document") -> bool:
        """Remove a chat session"""
        key = (user_id, context_id, context_type)
        if key in self._sessions:
            del self._sessions[key]
            return True
        return False
    
    def get_user_sessions(self, user_id: str) -> Dict[Tuple[str, str], ChatSession]:
        """Get all sessions for a specific user"""
        return {key: session for key, session in self._sessions.items() if key[0] == user_id}


# Create a global instance of the chat session manager
chat_session_manager = ChatSessionManager() 