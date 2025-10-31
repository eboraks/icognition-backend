from app.utils.logging import get_logger
from app.core.config import settings
from langgraph.checkpoint.postgres import PostgresSaver
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.agents import create_agent
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.tools import tool
from app.services.document_service import DocumentService
from app.services.chat_session_service import ChatSessionService
from app.db.database import get_database_url, get_session
from sqlalchemy.ext.asyncio import AsyncSession
import os
from typing import Optional
import json

logger = get_logger(__name__)


def create_retrieve_documents_tool(user_id: str, scope_type: str, scope_id: Optional[int], db_session: AsyncSession):
    """
    Create a context-aware document retrieval tool for a specific chat session.
    """
    @tool
    async def retrieve_documents_tool(query: str) -> str:
        """
        Retrieves relevant documents from the user's library to answer a question.
        Use this tool when the user asks questions that might be answered by documents in their library.
        
        Args:
            query: The search query or question to find relevant documents for.
        
        Returns:
            A formatted string with relevant document titles and content snippets.
        """
        try:
            document_service = DocumentService(db_session)
            
            # Get relevant documents using vector search
            # user_id is Firebase UID (string), which matches Document.user_id type
            documents = await document_service.get_relevant_documents_for_chat(
                user_id=user_id,
                query=query,
                scope_type=scope_type,
                scope_id=scope_id,
                limit=5
            )
            
            if not documents:
                return f"No relevant documents found in your library for the query: '{query}'"
            
            # Format documents for the agent
            result_parts = [f"Found {len(documents)} relevant document(s):"]
            for i, doc in enumerate(documents, 1):
                content_preview = doc.content[:500] if doc.content else "No content available"
                result_parts.append(f"\n{i}. **{doc.title}**")
                if doc.url:
                    result_parts.append(f"   URL: {doc.url}")
                result_parts.append(f"   Content preview: {content_preview}...")
            
            return "\n".join(result_parts)
        except Exception as e:
            logger.error(f"Error retrieving documents: {e}", exc_info=True)
            return f"Error retrieving documents: {str(e)}"
    
    return retrieve_documents_tool


class ChatAgentService:
    """
    Service for handling chat interactions using a LangGraph agent.
    """

    def __init__(self, checkpointer):
        self.checkpointer = checkpointer


    async def get_stream(self, session_id: int, message: str, user_id: str):
        logger.info(f"Streaming response for session {session_id} for user {user_id}")
        
        # Get database session for this request
        async_gen = get_session()
        db_session = await async_gen.__anext__()
        
        try:
            # Load chat session to get scope information
            chat_session_service = ChatSessionService(db_session)
            chat_session = await chat_session_service.get_session_by_id(session_id, user_id)
            
            if not chat_session:
                logger.error(f"Chat session {session_id} not found for user {user_id}")
                yield "Error: Chat session not found."
                return
            
            # Create context-aware tools with session scope
            retrieve_tool = create_retrieve_documents_tool(
                user_id=user_id,
                scope_type=chat_session.scope_type or "all_library",
                scope_id=chat_session.scope_id,
                db_session=db_session
            )
            
            # Create agent executor with context-aware tools
            llm = ChatGoogleGenerativeAI(model=settings.GEMINI_FLASH_MODEL, google_api_key=settings.GOOGLE_API_KEY)
            tools = [retrieve_tool]
            
            system_prompt = (
                "You are a helpful research assistant that can answer questions using the user's document library. "
                "When users ask questions, use the retrieve_documents_tool to find relevant documents from their library, "
                "then provide comprehensive answers based on the retrieved content. If the documents don't contain relevant "
                "information, let the user know clearly."
            )
            
            agent_executor = create_agent(
                llm,
                tools=tools,
                system_prompt=system_prompt
            )
            
            inputs = {"messages": [("human", message)]}

            # Stream agent values and forward the latest message content to the websocket
            async for value in agent_executor.astream(inputs, stream_mode="values"):
                try:
                    messages = value.get("messages") or []
                    if not messages:
                        continue

                    latest = messages[-1]
                    msg_type = getattr(latest, "type", None) or getattr(latest, "role", None)
                    if msg_type and msg_type != "ai":
                        # Only forward assistant output to client
                        continue

                    content = getattr(latest, "content", None)
                    if content is None:
                        continue

                    # Normalize content to string
                    text = None
                    if isinstance(content, str):
                        text = content
                    elif isinstance(content, list):
                        parts = []
                        for part in content:
                            if isinstance(part, dict) and "text" in part:
                                parts.append(str(part.get("text", "")))
                            elif isinstance(part, str):
                                parts.append(part)
                            else:
                                parts.append(str(part))
                        text = "".join(parts)
                    else:
                        text = str(content)

                    if text:
                        yield text
                except Exception:
                    # Silently skip malformed chunks
                    continue
        finally:
            # Close the database session
            await db_session.close()

                    
_chat_agent_service: Optional[ChatAgentService] = None

def get_chat_agent_service() -> ChatAgentService:
    """
    Get the chat agent service instance, creating it if it doesn't exist.
    """
    global _chat_agent_service
    if _chat_agent_service is None:
        # Build a sync connection string using psycopg (v3) from the configured async URL
        async_url = get_database_url()
        if "+asyncpg" in async_url:
            conn_str = async_url.replace("+asyncpg", "+psycopg")
        else:
            conn_str = async_url
            if conn_str.startswith("postgresql://"):
                conn_str = conn_str.replace("postgresql://", "postgresql+psycopg://", 1)
        checkpointer = PostgresSaver.from_conn_string(conn_str)
        _chat_agent_service = ChatAgentService(checkpointer)
    return _chat_agent_service
