from app.utils.logging import get_logger
from app.core.config import settings
from app.utils.langsmith_tracing import enable_langsmith_tracing
import asyncio
import atexit
from contextlib import ExitStack
from typing import Optional
import uuid

from langgraph.checkpoint.postgres import PostgresSaver
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.agents import create_agent
from langchain_core.messages import HumanMessage, AIMessage
from langchain_core.tools import tool
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.engine import make_url
from tenacity import RetryError

from app.db.database import get_database_url, get_session
from app.services.chat_session_service import ChatSessionService
from app.services.document_service import DocumentService

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


class AsyncPostgresSaver(PostgresSaver):
    """Async wrapper around PostgresSaver using thread offloading."""

    async def aget_tuple(self, config):  # type: ignore[override]
        return await asyncio.to_thread(self.get_tuple, config)

    async def alist(self, config=None, *, filter=None, before=None, limit=None):  # type: ignore[override]
        def _collect():
            results = []
            for item in self.list(config, filter=filter, before=before, limit=limit):
                results.append(item)
            return results

        items = await asyncio.to_thread(_collect)
        for item in items:
            yield item

    async def aput(self, config, checkpoint, metadata, new_versions):  # type: ignore[override]
        return await asyncio.to_thread(
            super().put, config, checkpoint, metadata, new_versions
        )

    async def aput_writes(self, config, writes, task_id, task_path=""):  # type: ignore[override]
        return await asyncio.to_thread(
            super().put_writes, config, writes, task_id, task_path
        )

    async def adelete_thread(self, thread_id):  # type: ignore[override]
        await asyncio.to_thread(super().delete_thread, thread_id)


class ChatAgentService:
    """
    Service for handling chat interactions using a LangGraph agent.
    """

    def __init__(self, checkpointer):
        self.checkpointer = checkpointer


    async def get_stream(self, session_id: int, message: str, user_id: str):
        logger.info(f"Starting stream for session {session_id}, user {user_id}, message length: {len(message)}")
        
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
            
            logger.info(f"Found chat session: scope_type={chat_session.scope_type}, scope_id={chat_session.scope_id}, thread_id={chat_session.thread_id}")
            
            # Ensure thread_id exists for conversation continuity
            if not chat_session.thread_id:
                chat_session.thread_id = str(uuid.uuid4())
                db_session.add(chat_session)
                await db_session.commit()
                await db_session.refresh(chat_session)
                logger.info(f"Generated new thread_id: {chat_session.thread_id}")
            
            # Load conversation history from database
            previous_messages = await chat_session_service.get_session_messages(session_id, user_id)
            logger.info(f"Loaded {len(previous_messages)} previous messages from database")
            
            # Create context-aware tools with session scope
            retrieve_tool = create_retrieve_documents_tool(
                user_id=user_id,
                scope_type=chat_session.scope_type or "all_library",
                scope_id=chat_session.scope_id,
                db_session=db_session
            )
            
            # Create agent executor with context-aware tools
            try:
                llm = ChatGoogleGenerativeAI(model=settings.GEMINI_FLASH_MODEL, google_api_key=settings.GOOGLE_API_KEY)
                logger.info(f"Initialized LLM with model: {settings.GEMINI_FLASH_MODEL}")
            except Exception as e:
                logger.error(f"Failed to initialize LLM: {e}", exc_info=True)
                yield "Error: Failed to initialize AI model."
                return
            
            tools = [retrieve_tool]
            logger.info(f"Created {len(tools)} tool(s)")
            
            system_prompt = (
                "You are a helpful research assistant that can answer questions using the user's document library. "
                "When users ask questions, use the retrieve_documents_tool to find relevant documents from their library, "
                "then provide comprehensive answers based on the retrieved content. If the documents don't contain relevant "
                "information, let the user know clearly."
            )
            
            # Build message history from stored messages to keep conversations scoped per tab/session
            message_history = []
            if previous_messages:
                for stored_message in previous_messages:
                    if stored_message.role == "user":
                        message_history.append(HumanMessage(content=stored_message.content))
                    elif stored_message.role == "assistant":
                        message_history.append(AIMessage(content=stored_message.content))
                    else:
                        logger.debug(
                            "Skipping unsupported message role '%s' for session %s", 
                            stored_message.role, 
                            session_id
                        )

                if message_history:
                    logger.info(
                        "Prepared %s message(s) for LangGraph history for session %s",
                        len(message_history),
                        session_id,
                    )
                else:
                    logger.warning(
                        "No supported messages found when preparing history for session %s; falling back to current message only",
                        session_id,
                    )
                    message_history = [HumanMessage(content=message)]
            else:
                logger.info("No previous messages, starting fresh conversation")
                message_history = [HumanMessage(content=message)]
            
            # Create agent with checkpointer for conversation memory
            try:
                agent_executor = create_agent(
                    model=llm,
                    tools=tools,
                    system_prompt=system_prompt,
                    checkpointer=self.checkpointer
                )
                logger.info("Created agent executor with checkpointer")
            except Exception as e:
                logger.error(f"Failed to create agent: {e}", exc_info=True)
                yield "Error: Failed to create chat agent."
                return
            
            # Prepare inputs with proper message format
            inputs = {
                "messages": message_history
            }
            
            # Configure checkpointer with thread_id for conversation continuity
            config = {
                "configurable": {"thread_id": chat_session.thread_id},
                "metadata": {
                    "chat_session_id": session_id,
                    "user_id": user_id,
                    "scope_type": chat_session.scope_type,
                    "scope_id": chat_session.scope_id,
                    "chat_session_title": chat_session.title,
                },
                "tags": [
                    "icognition",
                    "chat",
                    f"user:{user_id}",
                    f"session:{session_id}",
                ],
            }
            
            logger.info(f"Starting agent stream with thread_id: {chat_session.thread_id}")
            
            # Stream agent values and forward the latest message content to the websocket
            chunk_count = 0
            last_full_content = ""  # Track the last full content we've sent
            
            try:
                async for value in agent_executor.astream(inputs, stream_mode="values", config=config):
                    chunk_count += 1
                    try:
                        messages = value.get("messages") or []
                        if not messages:
                            logger.debug(f"Chunk {chunk_count}: No messages in value")
                            continue

                        # Get the latest AI message
                        ai_messages = [msg for msg in messages if getattr(msg, "type", None) in ("ai", "assistant") or getattr(msg, "role", None) in ("ai", "assistant")]
                        
                        if not ai_messages:
                            logger.debug(f"Chunk {chunk_count}: No AI messages found")
                            continue
                        
                        latest_ai = ai_messages[-1]
                        
                        content = getattr(latest_ai, "content", None)
                        if content is None:
                            continue

                        # Normalize content to string
                        text = None
                        if isinstance(content, str):
                            text = content
                        elif isinstance(content, list):
                            parts = []
                            for part in content:
                                if isinstance(part, dict):
                                    # Handle different content types
                                    if "text" in part:
                                        parts.append(str(part.get("text", "")))
                                    elif "type" in part and part.get("type") == "text":
                                        parts.append(str(part.get("text", "")))
                                    else:
                                        # Fallback: stringify the dict
                                        parts.append(str(part))
                                elif isinstance(part, str):
                                    parts.append(part)
                                else:
                                    parts.append(str(part))
                            text = "".join(parts)
                        else:
                            text = str(content)

                        # Only yield incremental content (new text since last chunk)
                        if text and len(text) > len(last_full_content):
                            # Check if it's a continuation or a new message
                            if text.startswith(last_full_content):
                                # It's a continuation - yield only the new part
                                new_text = text[len(last_full_content):]
                                last_full_content = text
                                logger.debug(f"Yielding incremental update: {len(new_text)} new characters (total: {len(text)})")
                                yield new_text
                            else:
                                # It's a completely new message (shouldn't happen with values mode, but handle it)
                                logger.warning(f"New message detected without continuation - full length: {len(text)}")
                                last_full_content = text
                                yield text
                                
                    except Exception as e:
                        logger.error(f"Error processing chunk {chunk_count}: {e}", exc_info=True)
                        continue
                
                logger.info(f"Stream completed: {chunk_count} chunks processed, final content length: {len(last_full_content)}")
            except RetryError as e:
                logger.error(f"Network error while contacting AI service: {e}", exc_info=True)
                yield "I'm having trouble connecting to the AI service. Please check the backend's network connection and DNS settings."
            except Exception as e:
                logger.error(f"Error during agent streaming: {e}", exc_info=True)
                yield f"\n\nError: {str(e)}"
        finally:
            # Close the database session
            await db_session.close()
            logger.info(f"Closed database session for session {session_id}")

                    
_chat_agent_service: Optional[ChatAgentService] = None
_checkpointer_exit_stack: Optional[ExitStack] = None


def get_chat_agent_service() -> ChatAgentService:
    """Get the chat agent service instance, creating it if it doesn't exist."""
    global _chat_agent_service, _checkpointer_exit_stack
    if _chat_agent_service is None:
        try:
            enable_langsmith_tracing()
            # Build a psycopg-compatible connection string from the configured async URL
            async_url = get_database_url()
            url = make_url(async_url)

            if url.drivername.endswith("+asyncpg"):
                url = url.set(drivername="postgresql")
            elif url.drivername.endswith("+psycopg"):
                url = url.set(drivername="postgresql")
            elif url.drivername == "postgresql+psycopg3":
                url = url.set(drivername="postgresql")

            conn_str = url.render_as_string(hide_password=False)

            logger.info("Initializing PostgresSaver checkpointer")

            exit_stack = ExitStack()
            checkpointer_context = AsyncPostgresSaver.from_conn_string(conn_str)
            checkpointer = exit_stack.enter_context(checkpointer_context)
            logger.info("PostgresSaver checkpointer created successfully")

            # Ensure resources are cleaned up on process exit
            atexit.register(exit_stack.close)
            _checkpointer_exit_stack = exit_stack

            # Ensure schema exists before usage
            checkpointer.setup()

            _chat_agent_service = ChatAgentService(checkpointer)
            logger.info("ChatAgentService initialized successfully")
        except Exception as e:
            logger.error(f"Failed to create ChatAgentService: {e}", exc_info=True)
            raise

    return _chat_agent_service
