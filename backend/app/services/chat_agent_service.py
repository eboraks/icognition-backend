from app.utils.logging import get_logger
from app.core.config import settings
from app.utils.langsmith_tracing import enable_langsmith_tracing
from typing import Optional
import uuid
from bs4 import BeautifulSoup
from contextlib import AbstractAsyncContextManager

from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.prebuilt import create_react_agent
from langchain_core.messages import HumanMessage, AIMessage
from langchain_core.tools import tool
from sqlalchemy.ext.asyncio import AsyncSession
from tenacity import RetryError

from app.db.database import get_session, get_database_url
from app.services.chat_session_service import ChatSessionService
from app.services.document_service import DocumentService

logger = get_logger(__name__)

try:
    # AsyncPostgresSaver is in the aio module
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
except ImportError:
    logger.error("Failed to import AsyncPostgresSaver. Please ensure langgraph-checkpoint-postgres is installed.")
    raise

# Global checkpointer instance (initialized lazily)
_checkpointer: Optional[AsyncPostgresSaver] = None
_checkpointer_cm: Optional[AbstractAsyncContextManager[AsyncPostgresSaver]] = None


async def get_checkpointer() -> AsyncPostgresSaver:
    """
    Get or create the PostgreSQL checkpointer for LangGraph.
    This maintains conversation state across requests.
    """
    global _checkpointer
    global _checkpointer_cm
    
    if _checkpointer is not None:
        return _checkpointer

    # Get database URL and ensure it's in the right format for the checkpointer
    db_url = get_database_url()
    # The checkpointer expects a sync postgresql:// URL (not asyncpg)
    if db_url.startswith("postgresql+asyncpg://"):
        db_url = db_url.replace("postgresql+asyncpg://", "postgresql://", 1)
    elif db_url.startswith("postgresql+psycopg://"):
        db_url = db_url.replace("postgresql+psycopg://", "postgresql://", 1)
    
    try:
        logger.info("Initializing LangGraph PostgreSQL checkpointer...")
        _checkpointer_cm = AsyncPostgresSaver.from_conn_string(db_url)
        _checkpointer = await _checkpointer_cm.__aenter__()
        # setup() creates the necessary tables and indexes. 
        # By calling this during startup, we avoid deadlocks with request transactions.
        await _checkpointer.setup()
        logger.info("✅ LangGraph PostgreSQL checkpointer initialized successfully")
    except Exception as e:
        logger.error(f"❌ Failed to initialize checkpointer: {e}", exc_info=True)
        # Reset globals if initialization failed so it can be retried
        _checkpointer = None
        _checkpointer_cm = None
        raise
        
    return _checkpointer


def strip_html_and_clean(text: str) -> str:
    """
    Strip HTML tags and clean up text for better readability.
    This helps prevent raw HTML from appearing in chat responses.
    """
    if not text:
        return ""
    
    try:
        soup = BeautifulSoup(text, "html.parser")
        # Get text and clean up whitespace
        cleaned = soup.get_text(separator=" ", strip=True)
        # Normalize multiple spaces to single space
        cleaned = " ".join(cleaned.split())
        return cleaned
    except Exception as e:
        logger.warning(f"Error stripping HTML: {e}, returning original text")
        return text


def extract_text_from_content(content) -> str:
    """
    Normalize LangChain/LangGraph content payloads into plain text.
    Handles strings, ChatModel content lists, and dict payloads.
    """
    if content is None:
        return ""

    if isinstance(content, str):
        return content

    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                # Chat model chunks commonly return {"type": "output_text", "text": "..."}
                text_value = item.get("text")
                if text_value:
                    parts.append(str(text_value))
            else:
                text_attr = getattr(item, "text", None)
                if text_attr:
                    parts.append(str(text_attr))
        return "".join(parts)

    # Fallback: convert to string
    return str(content)


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
            
            # Get relevant documents with matching chunks using vector search
            # user_id is Firebase UID (string), which matches Document.user_id type
            documents_with_chunks = await document_service.get_relevant_documents_with_chunks_for_chat(
                user_id=user_id,
                query=query,
                scope_type=scope_type,
                scope_id=scope_id,
                limit=5,
                similarity_threshold=0.55,  # Lower threshold for broader matching
                chunks_per_document=5  # Include up to 5 top chunks per document
            )
            
            if not documents_with_chunks:
                return f"No relevant documents found in your library for the query: '{query}'"
            
            # Format documents for the agent with matching chunks prominently displayed
            result_parts = [f"Found {len(documents_with_chunks)} relevant document(s):"]
            
            for i, doc_data in enumerate(documents_with_chunks, 1):
                doc = doc_data['document']
                chunks = doc_data['chunks']
                best_score = doc_data['best_score']
                
                result_parts.append(f"\n{i}. **{doc.title}**")
                if doc.url:
                    result_parts.append(f"   URL: {doc.url}")
                
                # Show matching chunks first - these are the actual text that matched the query
                if chunks:
                    result_parts.append(f"   Matching Content (similarity: {best_score:.2f}):")
                    for j, chunk in enumerate(chunks, 1):
                        # Clean chunk text
                        chunk_text = strip_html_and_clean(chunk['text'])
                        # Limit chunk length to avoid token limits (1500 chars per chunk)
                        if len(chunk_text) > 1500:
                            chunk_text = chunk_text[:1500] + "... [chunk truncated]"
                        
                        result_parts.append(f"   [{j}] {chunk_text}")
                        result_parts.append("")  # Empty line between chunks
                
                # Optionally include full document content as additional context
                # Only if chunks don't provide enough information or document is short
                if doc.content:
                    raw_content = doc.content
                    cleaned_content = strip_html_and_clean(raw_content)
                    # Only include full content if it's relatively short or chunks are few
                    if len(cleaned_content) < 3000 or len(chunks) < 2:
                        if len(cleaned_content) > 2000:
                            cleaned_content = cleaned_content[:2000] + "... [content truncated]"
                        result_parts.append(f"   Full Document Content: {cleaned_content}")
                else:
                    result_parts.append("   [No full content available]")
            
            return "\n".join(result_parts)
        except Exception as e:
            logger.error(f"Error retrieving documents: {e}", exc_info=True)
            return f"Error retrieving documents: {str(e)}"
    
    return retrieve_documents_tool


class ChatAgentService:
    """
    Service for handling chat interactions using LangGraph's prebuilt ReAct agent.
    The agent uses PostgreSQL checkpointer to maintain conversation history across requests.
    """

    def __init__(self):
        """Initialize the chat agent service."""
        logger.info("ChatAgentService initialized")

    async def get_stream(self, session_id: int, message: str, user_id: str):
        """
        Stream agent responses for a chat message using LangGraph.
        The agent maintains conversation history via PostgreSQL checkpointer using thread_id.
        """
        logger.info(f"Starting stream for session {session_id}, user {user_id}, message length: {len(message)}")
        
        # Get database session for this request
        async_gen = get_session()
        db_session = await async_gen.__anext__()
        
        try:
            # Load chat session to get scope information and thread_id
            chat_session_service = ChatSessionService(db_session)
            chat_session = await chat_session_service.get_session_by_id(session_id, user_id)
            
            if not chat_session:
                logger.error(f"Chat session {session_id} not found for user {user_id}")
                yield "Error: Chat session not found."
                return
            
            logger.info(f"Found chat session: scope_type={chat_session.scope_type}, scope_id={chat_session.scope_id}")
            
            # Ensure thread_id is set for LangGraph checkpointer
            thread_id = chat_session.thread_id
            if not thread_id:
                # Generate a unique thread_id if not set
                thread_id = f"session_{session_id}_{uuid.uuid4().hex[:8]}"
                chat_session.thread_id = thread_id
                await db_session.commit()
                await db_session.refresh(chat_session)
                logger.info(f"Generated new thread_id for session {session_id}: {thread_id}")
            
            # Create context-aware tools with session scope
            retrieve_tool = create_retrieve_documents_tool(
                user_id=user_id,
                scope_type=chat_session.scope_type or "all_library",
                scope_id=chat_session.scope_id,
                db_session=db_session
            )
            
            # Initialize LLM
            try:
                llm = ChatGoogleGenerativeAI(model=settings.GEMINI_FLASH_MODEL, google_api_key=settings.GOOGLE_API_KEY)
                logger.info(f"Initialized LLM with model: {settings.GEMINI_FLASH_MODEL}")
            except Exception as e:
                logger.error(f"Failed to initialize LLM: {e}", exc_info=True)
                yield "Error: Failed to initialize AI model."
                return
            
            # Create LangGraph ReAct agent with checkpointer for memory
            try:
                # Try to get system prompt from database, fallback to hardcoded
                from app.services.prompt_service import PromptService
                prompt_service = PromptService(db_session)
                db_prompt = await prompt_service.get_latest_prompt("react_agent_system")
                
                if db_prompt:
                    system_prompt = db_prompt.content
                    logger.info(f"[Session {session_id}] Using system prompt from database (version {db_prompt.version})")
                else:
                    # Fallback to hardcoded prompt
                    system_prompt = (
                        "You are a helpful research assistant that can answer questions using the user's document library. "
                        "When users ask questions, use the retrieve_documents_tool to find relevant documents from their library. "
                        "IMPORTANT: After retrieving documents, you must synthesize the information and provide a comprehensive, "
                        "natural-language answer to the user's question. Do NOT simply repeat the tool output verbatim. "
                        "Use the retrieved document content to craft a clear, well-structured response that directly answers "
                        "the user's question. If the documents don't contain relevant information, let the user know clearly. "
                        "The tool returns cleaned text content - use it to inform your answer. Always cite document titles and URLs "
                        "when referencing specific documents."
                    )
                    logger.info(f"[Session {session_id}] Using fallback hardcoded system prompt")
                
                logger.info(f"[Session {session_id}] Getting checkpointer...")
                checkpointer = await get_checkpointer()
                logger.info(f"[Session {session_id}] Checkpointer obtained, creating ReAct agent...")
                agent = create_react_agent(
                    model=llm,
                    tools=[retrieve_tool],
                    prompt=system_prompt,
                    checkpointer=checkpointer
                )
                logger.info(f"[Session {session_id}] Created LangGraph ReAct agent with tools and checkpointer")
            except Exception as e:
                logger.error(f"Failed to create agent: {e}", exc_info=True)
                yield "Error: Failed to create chat agent."
                return
            
            # Prepare the input with the new user message
            # LangGraph will automatically load previous messages from the checkpointer
            input_messages = [HumanMessage(content=message)]
            
            logger.info(f"[Session {session_id}] Starting stream for thread_id: {thread_id}")
            
            # Stream agent responses using LangGraph's value stream (mirrors previous behavior)
            accumulated_text = ""
            chunk_count = 0
            try:
                logger.info(f"[Session {session_id}] Calling agent.astream()...")
                async for chunk in agent.astream(
                    {"messages": input_messages},
                    config={"thread_id": thread_id},
                    stream_mode="values"
                ):
                    chunk_count += 1
                    logger.info(f"[Session {session_id}] Received chunk #{chunk_count} from agent.astream()")
                    messages = chunk.get("messages", [])
                    if not messages:
                        logger.info(f"[Session {session_id}] Chunk #{chunk_count} has no messages, skipping")
                        continue

                    latest_message = messages[-1]
                    logger.info(f"[Session {session_id}] Latest message type: {type(latest_message).__name__}")
                    if not isinstance(latest_message, AIMessage):
                        logger.info(f"[Session {session_id}] Not an AIMessage, skipping")
                        continue
                    
                    text = extract_text_from_content(getattr(latest_message, "content", None))
                    if not text:
                        logger.info(f"[Session {session_id}] No text content extracted, skipping")
                        continue

                    if text.startswith(accumulated_text):
                        new_text = text[len(accumulated_text):]
                    else:
                        new_text = text

                    accumulated_text = text
                    if new_text:
                        logger.info(f"[Session {session_id}] Yielding chunk: {len(new_text)} chars (total: {len(accumulated_text)})")
                        yield new_text
                    else:
                        logger.info(f"[Session {session_id}] No new text to yield in this chunk")
                
                logger.info(f"[Session {session_id}] Stream loop completed. Total chunks: {chunk_count}, Total text: {len(accumulated_text)} chars")

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


def get_chat_agent_service() -> ChatAgentService:
    """Get the chat agent service instance, creating it if it doesn't exist."""
    global _chat_agent_service
    if _chat_agent_service is None:
        try:
            enable_langsmith_tracing()
            _chat_agent_service = ChatAgentService()
            logger.info("ChatAgentService initialized successfully with LangGraph")
        except Exception as e:
            logger.error(f"Failed to create ChatAgentService: {e}", exc_info=True)
            raise

    return _chat_agent_service
