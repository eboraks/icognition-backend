import asyncio
import re

from app.utils.logging import get_logger
from app.core.config import settings
from app.utils.langsmith_tracing import enable_langsmith_tracing
from typing import Optional, List
import uuid
from bs4 import BeautifulSoup
from contextlib import AbstractAsyncContextManager


def _build_chat_context_event(chunk: dict, response_text: str) -> dict:
    """Extract entity IDs from graph state and doc IDs from source tags in the response."""
    entity_ids = list(set(chunk.get("context_entity_ids", [])))
    # Extract doc IDs from <source doc_id="N"> tags in the raw response
    doc_ids = list(set(int(m) for m in re.findall(r'<source\s+doc_id=["\'](\d+)["\']>', response_text)))
    return {
        "type": "chat_context",
        "entity_ids": entity_ids,
        "document_ids": doc_ids,
    }

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from sqlalchemy.ext.asyncio import AsyncSession
from tenacity import RetryError
from app.chat_workflows.research_graph import build_research_graph, fetch_graph_prompts

from app.db.database import get_session, get_database_url
from app.services.chat_session_service import ChatSessionService
from app.services.document_service import DocumentService
from app.services.prompt_service import get_prompt
from app.services.prompt_utils import PromptType
from app.utils.langfuse_worker import get_langfuse_handler

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


from app.chat_workflows.tools import create_retrieve_documents_tool, create_knowledge_graph_tool, strip_html_and_clean

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
                # Gemini returns {"type": "text", "text": "..."} parts
                text_value = item.get("text")
                if text_value:
                    parts.append(str(text_value))
                elif item.get("content"):
                    parts.append(str(item["content"]))
            else:
                text_attr = getattr(item, "text", None)
                if text_attr:
                    parts.append(str(text_attr))
        result = "".join(parts)
        if not result and content:
            # List was non-empty but no text extracted — log and fallback
            logger.warning(
                f"extract_text_from_content: non-empty list yielded no text. "
                f"Types: {[type(i).__name__ for i in content[:3]]}. "
                f"First item: {repr(content[0])[:200] if content else 'N/A'}"
            )
            return str(content)
        return result

    # Fallback: convert to string
    return str(content)


class ChatAgentService:
    """
    Service for handling chat interactions using LangGraph's prebuilt ReAct agent.
    The agent uses PostgreSQL checkpointer to maintain conversation history across requests.
    """

    def __init__(self):
        """Initialize the chat agent service."""
        logger.info("ChatAgentService initialized")

    async def get_suggestion(
        self, 
        user_id: str, 
        session_id: int, 
        current_text: str,
        context: Optional[str] = None
    ) -> str:
        """
        Get a Gmail-style ghost text completion suggestion.
        """
        if not current_text or len(current_text) < 3:
            return ""

        # Use async for so Python guarantees aclose() is called on the generator
        # when the function exits (return or exception), properly releasing the connection.
        async for db_session in get_session():
            try:
                chat_session_service = ChatSessionService(db_session)
                messages = await chat_session_service.get_session_messages(session_id, user_id)

                # Format last 5 messages as history context
                history_parts = []
                for msg in messages[-5:]:
                    role = "User" if msg.role == "user" else "Assistant"
                    history_parts.append(f"{role}: {strip_html_and_clean(msg.content)}")
                history = "\n".join(history_parts)

                llm = ChatGoogleGenerativeAI(
                    model=settings.GEMINI_FLASH_LITE_MODEL,
                    google_api_key=settings.GOOGLE_API_KEY,
                    temperature=0.0,
                    max_tokens=20
                )

                db_prompt = get_prompt(PromptType.CHAT_AGENT_TYPE_AHEAD.value)

                if db_prompt:
                    system_prompt = db_prompt.system_prompt or "You are an AI writing assistant."
                    user_template = db_prompt.user_prompt
                    try:
                        user_prompt = user_template.format(
                            history=history,
                            context=context or "None",
                            current_text=current_text
                        )
                    except (KeyError, ValueError):
                        user_prompt = f"{user_template}\n\nHistory: {history}\nContext: {context}\nTyping: {current_text}"
                    prompt = f"{system_prompt}\n\n{user_prompt}"
                else:
                    prompt_parts = [
                        "You are an AI writing assistant. Continue the user's thought following the provided conversation history.",
                        f"\nConversation History:\n{history}" if history else "",
                    ]
                    if context:
                        prompt_parts.append(f"\nAdditional Context: {context}")
                    prompt_parts.append(f"\nUser is currently typing: '{current_text}'")
                    prompt_parts.append(
                        "\nProvide ONLY the characters or words that complete the current thought from where it left off. "
                        "Do NOT repeat any part of the input text. Do NOT explain yourself. "
                        "The completion should feel natural and continue the specific sentence or phrase the user is currently typing. "
                        "If no good completion is found, return nothing."
                    )
                    prompt = "\n".join(filter(None, prompt_parts))

                lf_handler = get_langfuse_handler()
                callbacks = [lf_handler] if lf_handler else []

                response = await llm.ainvoke(
                    prompt,
                    config={
                        "callbacks": callbacks,
                        "run_name": PromptType.CHAT_AGENT_TYPE_AHEAD.value
                    }
                )
                prediction = extract_text_from_content(response.content).strip()

                if prediction.startswith('"') and prediction.endswith('"'):
                    prediction = prediction[1:-1]
                if prediction.startswith("'") and prediction.endswith("'"):
                    prediction = prediction[1:-1]

                return prediction
            except Exception as e:
                logger.error(f"Error getting suggestion for session {session_id}: {e}", exc_info=True)
                return ""

    async def get_stream(self, session_id: int, message: str, user_id: str, skill_override: Optional[str] = None):
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
                yield {"type": "error", "content": "Chat session not found."}
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
            kg_tool = create_knowledge_graph_tool(user_id=user_id, db_session=db_session)
            
            # Initialize LLM
            try:
                llm = ChatGoogleGenerativeAI(model=settings.GEMINI_FLASH_MODEL, google_api_key=settings.GOOGLE_API_KEY)
                logger.info(f"Initialized LLM with model: {settings.GEMINI_FLASH_MODEL}")
            except Exception as e:
                logger.error(f"Failed to initialize LLM: {e}", exc_info=True)
                yield {"type": "error", "content": "Failed to initialize AI model."}
                return
            
            # Create LangGraph ReAct agent with checkpointer for memory
            try:
                # Get system prompt from YAML
                db_prompt = get_prompt(PromptType.CHAT_AGENT_SYSTEM.value)

                if db_prompt:
                    system_prompt = db_prompt.system_prompt or ""
                    if db_prompt.user_prompt:
                        system_prompt += f"\n\n{db_prompt.user_prompt}"
                    logger.info(f"[Session {session_id}] Using system prompt from YAML")
                else:
                    system_prompt = "You are a helpful research assistant."
                    logger.warning(f"[Session {session_id}] System prompt not found in YAML, using minimal fallback")

                # PRIME THE AGENT with document context if scoped
                if chat_session.scope_type == "document" and chat_session.scope_id:
                    try:
                        doc_service = DocumentService(db_session)
                        # We use the internal service methods to get the document
                        # No-Auth mode is handled inside DocumentService if configured
                        doc = await doc_service.get_document_by_id(user_id, chat_session.scope_id)
                        
                        if doc:
                            context_parts = [
                                "CURRENT CONTEXT (The user is specifically asking about this document):",
                                f"Title: {doc.title or 'Untitled'}",
                            ]

                            if doc.url:
                                context_parts.append(f"URL: {doc.url}")

                            # Add AI analysis summary if available
                            if doc.ai_is_about:
                                context_parts.append(f"Summary: {doc.ai_is_about}")

                            # Add AI-generated markdown summary
                            if doc.ai_markdown_content:
                                context_parts.append(f"\nDocument Analysis:\n{doc.ai_markdown_content}")

                            # Add the full original document content so the agent can reference
                            # specific details, paragraphs, and quotes that may not appear in the summary
                            if doc.content:
                                from app.chat_workflows.tools import strip_html_and_clean
                                full_content = strip_html_and_clean(doc.content)
                                # Truncate very long documents to avoid exceeding context limits
                                if len(full_content) > 15000:
                                    full_content = full_content[:15000] + "\n... [content truncated]"
                                context_parts.append(f"\nFull Document Content:\n{full_content}")
                            
                            # Prepend to system prompt
                            context_header = "\n".join(context_parts)
                            system_prompt = f"{context_header}\n\n---\n\n{system_prompt}"
                            logger.info(f"[Session {session_id}] Primed agent with metadata for document ID {doc.id}")
                        else:
                            logger.warning(f"[Session {session_id}] Scoped document {chat_session.scope_id} not found for priming")
                    except Exception as prime_err:
                        logger.error(f"[Session {session_id}] Error priming agent with document context: {prime_err}", exc_info=True)
                
                # Note: tools (retrieve, fetch_social_post, google_search) are assembled
                # inside build_research_graph — no need to build them here.

                logger.info(f"[Session {session_id}] Getting checkpointer and loading graph prompts...")
                graph_prompts = fetch_graph_prompts()
                checkpointer = await get_checkpointer()
                logger.info(f"[Session {session_id}] Checkpointer and prompts ready, creating Research Graph agent...")

                agent = build_research_graph(
                    checkpointer=checkpointer,
                    retrieve_tool=retrieve_tool,
                    kg_tool=kg_tool,
                    prompts=graph_prompts,
                    db_session=db_session,
                    user_id=user_id,
                    skill_override=skill_override,
                )
                logger.info(f"[Session {session_id}] Created Research Graph agent with tools and checkpointer")
            except Exception as e:
                logger.error(f"Failed to create agent: {e}", exc_info=True)
                yield {"type": "error", "content": "Failed to create chat agent."}
                return
            
            # Prepare the input with the new user message
            # LangGraph will automatically load previous messages from the checkpointer
            input_messages = []
            
            # Add document context if relevant (scoped interactions)
            if chat_session.scope_type == "document" and chat_session.scope_id and "CURRENT CONTEXT" in system_prompt:
                # Extract the context header from the prepared system prompt
                # We use the context part but not the full instruction prompt which is handled by the graph
                context_part = system_prompt.split("\n\n---\n\n")[0]
                input_messages.append(SystemMessage(content=context_part))
                
            input_messages.append(HumanMessage(content=message))
            
            logger.info(f"[Session {session_id}] Starting stream for thread_id: {thread_id}")
            
            # Stream agent responses using LangGraph's value stream (mirrors previous behavior)
            accumulated_text = ""
            chunk_count = 0
            
            # State tracking for UI feedback
            last_reflection_count = 0
            last_intent = None
            last_message_count = 0 
            last_processed_message_id = None
            
            try:
                # Add Langfuse tracing
                lf_handler = get_langfuse_handler()
                
                run_config = {"thread_id": thread_id}
                if lf_handler:
                    run_config["callbacks"] = [lf_handler]
                    run_config["run_name"] = PromptType.CHAT_AGENT_SYSTEM.value
                    # Add metadata for Langfuse traces to easily filter/search
                    run_config["metadata"] = {
                        "session_id": str(session_id),
                        "user_id": str(user_id),
                        "thread_id": thread_id,
                        "scope_type": chat_session.scope_type,
                        "scope_id": str(chat_session.scope_id) if chat_session.scope_id else None
                    }

                pending_ai_message = None
                
                logger.info(f"[Session {session_id}] Calling agent.astream()...")
                async for chunk in agent.astream(
                    {"messages": input_messages},
                    config=run_config,
                    stream_mode="values"
                ):
                    chunk_count += 1
                    logger.info(f"[Session {session_id}] Received chunk #{chunk_count}")
                    
                    # --- Status Feedback Logic ---
                    current_intent = chunk.get("intent")
                    current_message_list = chunk.get("messages", [])
                    
                    # 1. Intent Classified
                    if current_intent and current_intent != last_intent:
                        logger.info(f"[Session {session_id}] Intent detected: {current_intent}")
                        yield {
                            "type": "status",
                            "status_type": "thinking",
                            "content": f"analyzing request ({current_intent})"
                        }
                        last_intent = current_intent
 
                    # 2. Check for Reflection Outcome (Did we just reject a message?)
                    # If we had a pending message, and the new state has a critique (HumanMessage) 
                    # OR is explicitly not satisfactory but we moved past the generation step...
                    # Actually, we can check if the last message is a HumanMessage (Critique)
                    if current_message_list:
                        last_msg = current_message_list[-1]
                        
                        # If the last message is a HumanMessage (Critique) and we have a pending AI message,
                        # it means the AI message was rejected. Discard it.
                        if isinstance(last_msg, HumanMessage) and pending_ai_message:
                             logger.info(f"[Session {session_id}] Discarding pending AI message due to negative reflection.")
                             pending_ai_message = None 
                             yield {
                                "type": "status", 
                                "status_type": "thinking", 
                                "content": "refining answer based on critique"
                             }
                             
                        # If the last message is a System Note (Search), handled below, but also implies refinement
                        if isinstance(last_msg, HumanMessage) and "SYSTEM NOTE" in str(last_msg.content):
                             if getattr(last_msg, 'id', None) != last_processed_message_id:
                                logger.info(f"[Session {session_id}] Google Search executed")
                                yield {
                                    "type": "status",
                                    "status_type": "thinking",
                                    "content": "searching google for updated info"
                                }
                                last_processed_message_id = getattr(last_msg, 'id', None)
                                # If we searched, we definitely discard any previous AI answer (it was insufficient)
                                pending_ai_message = None

                        # If the last message is an AIMessage, we BUFFER it.
                        # We do NOT yield it yet. We wait for the next step (Reflection) to validate it.
                        if isinstance(last_msg, AIMessage):
                            # Skip tool-calling messages — they are intermediate, not final answers
                            if last_msg.tool_calls:
                                logger.info(f"[Session {session_id}] Skipping AI message with tool_calls (not a final answer).")
                                pending_ai_message = None
                            else:
                                if last_msg != pending_ai_message:
                                    logger.info(f"[Session {session_id}] Buffering new AI message candidate.")
                                    pending_ai_message = last_msg

                                # If is_satisfactory is TRUE in this chunk AND we have actual content,
                                # we can yield it immediately.
                                text = extract_text_from_content(pending_ai_message.content) if pending_ai_message else ""
                                if chunk.get("is_satisfactory") and text:
                                    content_type = type(pending_ai_message.content).__name__
                                    logger.info(f"[Session {session_id}] Message verified satisfactory. Yielding. Content type={content_type}, length={len(text)}")
                                    yield {"type": "content", "content": text}
                                    # Yield chat context (entity + doc IDs) for graph filtering
                                    yield _build_chat_context_event(chunk, text)
                                    pending_ai_message = None # Flushed
                                    return # End stream, we are done
                                elif chunk.get("is_satisfactory") and not text:
                                    logger.warning(f"[Session {session_id}] is_satisfactory=True but content is empty — not yielding, waiting for more chunks")
                                
                # If loop finishes and we still have a pending message (e.g. max reflections reached),
                # we must yield it as best-effort.
                if pending_ai_message:
                     logger.info(f"[Session {session_id}] Yielding final buffered message (Max reflections or End of Stream).")
                     text = extract_text_from_content(pending_ai_message.content)
                     yield {"type": "content", "content": text}
                     yield _build_chat_context_event(chunk, text)
                elif chunk_count == 0:
                     # Graph produced zero chunks — something went wrong silently
                     logger.error(f"[Session {session_id}] Stream completed with ZERO chunks — graph likely crashed silently")
                     yield {"type": "error", "content": "Failed to generate a response. The AI agent did not produce any output. Please try again."}
                else:
                     # We got chunks but no AI message was buffered — likely all were discarded by reflection
                     logger.warning(f"[Session {session_id}] Stream completed with {chunk_count} chunks but no AI message to yield")
                     yield {"type": "error", "content": "The AI could not generate a satisfactory response after multiple attempts. Please try rephrasing your question."}

                logger.info(f"[Session {session_id}] Stream loop completed.")

            except RetryError as e:
                logger.error(f"Network error while contacting AI service: {e}", exc_info=True)
                yield {"type": "error", "content": "I'm having trouble connecting to the AI service. Please check the backend's network connection and DNS settings."}
            except Exception as e:
                logger.error(f"Error during agent streaming: {e}", exc_info=True)
                yield {"type": "error", "content": f"\n\nError: {str(e)}"}
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
