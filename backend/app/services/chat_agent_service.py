from app.utils.logging import get_logger
from app.core.config import settings
from app.utils.langsmith_tracing import enable_langsmith_tracing
from typing import Optional
import uuid
from bs4 import BeautifulSoup
from contextlib import AbstractAsyncContextManager

from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.prebuilt import create_react_agent
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langchain_core.tools import tool, Tool
from langchain_google_community import GoogleSearchAPIWrapper
from sqlalchemy.ext.asyncio import AsyncSession
from tenacity import RetryError
from app.chat_workflows.research_graph import build_research_graph

from app.db.database import get_session, get_database_url
from app.services.chat_session_service import ChatSessionService
from app.services.document_service import DocumentService
from app.services.prompt_service import PromptService

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


from app.chat_workflows.tools import create_retrieve_documents_tool, strip_html_and_clean

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

        # Get database session for this request
        async_gen = get_session()
        db_session = await async_gen.__anext__()
        
        try:
            chat_session_service = ChatSessionService(db_session)
            # Use get_session_messages which already validates ownership
            messages = await chat_session_service.get_session_messages(session_id, user_id)
            
            # Format history for the model
            history_parts = []
            # Take last 5 messages for context
            for msg in messages[-5:]:
                role = "User" if msg.role == "user" else "Assistant"
                # Strip HTML for cleaner context
                content = strip_html_and_clean(msg.content)
                history_parts.append(f"{role}: {content}")
            
            history = "\n".join(history_parts)

            llm = ChatGoogleGenerativeAI(
                model=settings.GEMINI_FLASH_LITE_MODEL,
                google_api_key=settings.GOOGLE_API_KEY,
                temperature=0.0,
                max_tokens=20
            )

            # Try to get prompt from database
            from app.services.prompt_utils import PromptType
            prompt_service = PromptService(db_session)
            db_prompt = await prompt_service.get_latest_prompt(PromptType.CHAT_AGENT_TYPE_AHEAD.value)
            
            if db_prompt:
                system_prompt = db_prompt.system_prompt or "You are an AI writing assistant."
                user_template = db_prompt.user_prompt
                # The DB prompt might use different placeholders or just be the text
                try:
                    user_prompt = user_template.format(
                        history=history,
                        context=context or "None",
                        current_text=current_text
                    )
                except (KeyError, ValueError):
                    # Fallback if format fails
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

            response = await llm.ainvoke(prompt)
            prediction = extract_text_from_content(response.content).strip()
            
            # Simple cleanup: remove quotes if the model wrapped the response
            if prediction.startswith('"') and prediction.endswith('"'):
                prediction = prediction[1:-1]
            if prediction.startswith("'") and prediction.endswith("'"):
                prediction = prediction[1:-1]
            
            return prediction
        except Exception as e:
            logger.error(f"Error getting suggestion for session {session_id}: {e}", exc_info=True)
            return ""
        finally:
            await db_session.close()

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
                # Try to get system prompt from database, fallback to hardcoded
                from app.services.prompt_utils import PromptType
                prompt_service = PromptService(db_session)
                db_prompt = await prompt_service.get_latest_prompt(PromptType.CHAT_AGENT_SYSTEM.value)
                
                if db_prompt:
                    system_prompt = db_prompt.system_prompt
                    if db_prompt.user_prompt:
                        system_prompt += f"\n\n{db_prompt.user_prompt}"
                    logger.info(f"[Session {session_id}] Using system prompt from database (version {db_prompt.version})")
                else:
                    # Fallback to hardcoded prompt
                    system_prompt = (
                        "You are a helpful research assistant that can answer questions using the user's document library. "
                        "\n\nYour primary goal is to help the user understand and analyze their documents. You have two tools:"
                        "\n1. `retrieve_documents_tool`: Use this to find relevant information from the user's personal documents, articles, or bookmarks. This is your primary source of truth."
                        "\n2. `google_search_tool`: Use this ONLY to augment or validate information found in the documents, or to provide necessary context that helps explain the document's content. GROUND your search queries in the subject of the document and the current conversation. Do NOT use it for general, unrelated AI chat."
                        "\n\nWhen answering:"
                        "\n- ALWAYS prioritize information from the user's library."
                        "\n- Use Google Search to verify facts mentioned in the documents or to find updated information if requested (e.g., 'Has this legislation changed since this article was written?')."
                        "\n- Synthesize information from both sources, clearly distinguishing what comes from the library versus the web."
                        "\n- Provide a comprehensive, natural-language answer. Avoid verbatim tool output."
                        "\n- Always cite specific document titles and URLs when referencing the library."
                        "\n- If the documents don't contain relevant information and it's outside the scope of augmenting their content, inform the user clearly rather than just searching the web for a general answer."
                    )
                    logger.info(f"[Session {session_id}] Using fallback hardcoded system prompt")

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
                            
                            # Add key points if available
                            if doc.ai_bullet_points:
                                points = "\n- ".join(doc.ai_bullet_points)
                                context_parts.append(f"Key Points:\n- {points}")
                            
                            # Prepend to system prompt
                            context_header = "\n".join(context_parts)
                            system_prompt = f"{context_header}\n\n---\n\n{system_prompt}"
                            logger.info(f"[Session {session_id}] Primed agent with metadata for document ID {doc.id}")
                        else:
                            logger.warning(f"[Session {session_id}] Scoped document {chat_session.scope_id} not found for priming")
                    except Exception as prime_err:
                        logger.error(f"[Session {session_id}] Error priming agent with document context: {prime_err}", exc_info=True)
                
                # Initialize Google Search tool if configured
                tools = [retrieve_tool]
                if settings.GOOGLE_SEARCH_API and settings.GOOGLE_CSE_ID:
                    try:
                        search = GoogleSearchAPIWrapper(
                            google_api_key=settings.GOOGLE_SEARCH_API,
                            google_cse_id=settings.GOOGLE_CSE_ID,
                            k=5 # Limit to top 5 results
                        )
                        def search_with_metadata(query: str) -> str:
                            """Wrapper to include titles and links in search results."""
                            # DEBUG BREAKPOINT: Put a breakpoint on the line below to see raw results
                            results = search.results(query, num_results=5)
                            if not results:
                                return f"No Google search results found for: {query}"
                            
                            formatted = []
                            for i, r in enumerate(results, 1):
                                title = r.get("title", "No Title")
                                link = r.get("link", "No Link")
                                snippet = r.get("snippet", "No Snippet")
                                formatted.append(f"[{i}] {title}\nURL: {link}\nSnippet: {snippet}\n")
                            
                            logger.info(f"Google Search returned {len(results)} results for query: {query}")
                            return "\n---\n".join(formatted)

                        google_search_tool = Tool(
                            name="google_search_tool",
                            description="Searches Google for recent results to validate or augment document context.",
                            func=search_with_metadata,
                        )
                        tools.append(google_search_tool)
                        logger.info(f"[Session {session_id}] Google Search tool added to agent")
                    except Exception as e:
                        logger.error(f"Failed to initialize Google Search tool: {e}")
                else:
                    logger.warning(f"[Session {session_id}] Google Search tool NOT added (missing API key or CSE ID)")

                logger.info(f"[Session {session_id}] Getting checkpointer...")
                checkpointer = await get_checkpointer()
                logger.info(f"[Session {session_id}] Checkpointer obtained, creating Research Graph agent...")
                
                # Use the new Research Graph instead of generic ReAct
                # Note: System prompt is now handled inside the graph nodes based on intent/context
                # We can pass the base system prompt to the builder if we want to support it, 
                # but for now we'll rely on the logic in research_graph.py
                agent = build_research_graph(
                    checkpointer=checkpointer,
                    retrieve_tool=retrieve_tool,
                    db_session=db_session
                )
                logger.info(f"[Session {session_id}] Created Research Graph agent with tools and checkpointer")
            except Exception as e:
                logger.error(f"Failed to create agent: {e}", exc_info=True)
                yield {"type": "error", "content": "Failed to create chat agent."}
                return
            
            # Prepare the input with the new user message
            # LangGraph will automatically load previous messages from the checkpointer
            input_messages = [HumanMessage(content=message)]
            
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
                logger.info(f"[Session {session_id}] Calling agent.astream()...")
                async for chunk in agent.astream(
                    {"messages": input_messages},
                    config={"thread_id": thread_id},
                    stream_mode="values"
                ):
                    chunk_count += 1
                    logger.info(f"[Session {session_id}] Received chunk #{chunk_count}")
                    
                    # --- Status Feedback Logic ---
                    current_intent = chunk.get("intent")
                    current_reflection_count = chunk.get("reflection_count", 0)
                    
                    # 1. Intent Classified - Only emit if truly changed/new and not None
                    if current_intent and current_intent != last_intent:
                        logger.info(f"[Session {session_id}] Intent detected: {current_intent}")
                        yield {
                            "type": "status",
                            "status_type": "thinking",
                            "content": f"analyzing request ({current_intent})"
                        }
                        last_intent = current_intent

                    # 2. Reflection Step
                    if current_reflection_count > last_reflection_count:
                        logger.info(f"[Session {session_id}] Reflecting (count: {current_reflection_count})")
                        yield {
                            "type": "status",
                            "status_type": "thinking",
                            "content": "reflecting on answer"
                        }
                        last_reflection_count = current_reflection_count

                    messages = chunk.get("messages", [])
                    if not messages:
                        continue

                    latest_message = messages[-1]
                    
                    # 3. Search Step (Detect System Note)
                    if isinstance(latest_message, HumanMessage) and "SYSTEM NOTE" in str(latest_message.content):
                        # Ensure we don't spam this if state didn't change efficiently
                        if getattr(latest_message, 'id', None) != last_processed_message_id:
                            logger.info(f"[Session {session_id}] Google Search executed")
                            yield {
                                "type": "status",
                                "status_type": "thinking",
                                "content": "searching google"
                            }
                            last_processed_message_id = getattr(latest_message, 'id', None)
                            accumulated_text = "" # Reset for new message
                        continue

                    # Standard text streaming for AIMessages
                    if not isinstance(latest_message, AIMessage):
                        continue
                    
                    # Check for Message Boundary based on list length
                    current_message_count = len(messages)
                    
                    # If we have more messages than before, we encountered a new message step
                    if current_message_count > last_message_count:
                        # If we were previously streaming (accumulated_text > 0) and now have a new message,
                        # it implies we moved past that previous message.
                        if accumulated_text and last_message_count > 0:
                            # We are starting a fresh message. 
                            # If this new message is an AIMessage, it might be a refinement or new turn.
                            # We can emit a separator to be safe if it's a follow-up AI message.
                            logger.info(f"[Session {session_id}] New message detected (Count: {last_message_count} -> {current_message_count})")
                            yield {"type": "content", "content": "\n\n---\n*Refining answer based on new information...*\n\n"}
                        
                        # Reset for the new message
                        accumulated_text = ""
                        last_message_count = current_message_count
                    
                    # Ensure we are tracking the count correctly even if we didn't yield above
                    # e.g. first loop iteration
                    last_message_count = max(last_message_count, current_message_count)
                    
                    text = extract_text_from_content(getattr(latest_message, "content", None))
                    if not text:
                        continue

                    if text.startswith(accumulated_text):
                        new_text = text[len(accumulated_text):]
                    else:
                        # Should rarely happen now due to reset, but safe fallback
                        new_text = text

                    accumulated_text = text
                    if new_text:
                        logger.info(f"[Session {session_id}] Yielding chunk: {len(new_text)} chars")
                        yield {"type": "content", "content": new_text}
                    else:
                        logger.info(f"[Session {session_id}] No new text to yield")
                
                logger.info(f"[Session {session_id}] Stream loop completed. Total chunks: {chunk_count}, Total text: {len(accumulated_text)} chars")

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
