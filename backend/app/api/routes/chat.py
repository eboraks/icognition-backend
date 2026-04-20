from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from typing import List, Optional
from app.services.chat_session_service import ChatSessionService, get_chat_session_service
from app.core.user_context import UserContext, get_authenticated_user_context
from app.models import ChatSession, ChatMessage
from pydantic import BaseModel
from app.api.routes.websocket import manager
from app.services.chat_agent_service import get_chat_agent_service, ChatAgentService
from app.db.database import get_session, async_session
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
import json
import logging
import uuid
import asyncio
# format_chat_message removed — frontend renders markdown via marked.js

logger = logging.getLogger(__name__)

class WebSocketMessage(BaseModel):
    type: str  # e.g., "stream_chunk", "end_stream", "error"
    content: str = ""
    message_id: str | None = None # Optional for tracking streamed messages

router = APIRouter(
    prefix="/api/v1/chat",
    tags=["chat"],
    responses={404: {"description": "Not found"}},
)

class ChatSessionCreate(BaseModel):
    title: str
    scope_type: str
    scope_id: int | None = None

@router.post("/sessions", response_model=ChatSession)
async def create_chat_session(
    session_data: ChatSessionCreate,
    user_context: UserContext = Depends(get_authenticated_user_context),
    chat_session_service: ChatSessionService = Depends(get_chat_session_service),
):
    """
    Create a new chat session or return an existing one for the same scope.
    """
    # Check if a session already exists for this scope if it's a document/collection
    if session_data.scope_id:
        existing_session = await chat_session_service.get_session_by_scope(
            user_id=user_context.user.id,
            scope_type=session_data.scope_type,
            scope_id=session_data.scope_id
        )
        if existing_session:
            logger.info(f"Reusing existing chat session {existing_session.id} for scope {session_data.scope_type}:{session_data.scope_id}")
            return existing_session

    session = await chat_session_service.create_chat_session(
        user_id=user_context.user.id,
        title=session_data.title,
        scope_type=session_data.scope_type,
        scope_id=session_data.scope_id,
    )
    return session

@router.get("/sessions", response_model=List[ChatSession])
async def get_user_sessions(
    user_context: UserContext = Depends(get_authenticated_user_context),
    chat_session_service: ChatSessionService = Depends(get_chat_session_service),
):
    """
    Get all chat sessions for the authenticated user.
    """
    try:
        return await chat_session_service.get_user_sessions(user_id=user_context.user.id)
    except Exception as e:
        from app.core.config import settings
        if settings.DISABLE_AUTH:
            logger.warning(f"Database error in get_user_sessions (No-Auth mode): {e}")
            return []
        raise

@router.get("/sessions/{session_id}/messages", response_model=List[ChatMessage])
async def get_session_messages(
    session_id: int,
    user_context: UserContext = Depends(get_authenticated_user_context),
    chat_session_service: ChatSessionService = Depends(get_chat_session_service),
):
    """
    Get all messages for a specific chat session.
    """
    try:
        return await chat_session_service.get_session_messages(session_id=session_id, user_id=user_context.user.id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Chat session not found")
    except Exception as e:
        from app.core.config import settings
        if settings.DISABLE_AUTH:
            logger.warning(f"Database error in get_session_messages (No-Auth mode): {e}")
            return []
        raise

@router.delete("/sessions/{session_id}", status_code=204)
async def delete_chat_session(
    session_id: int,
    user_context: UserContext = Depends(get_authenticated_user_context),
    chat_session_service: ChatSessionService = Depends(get_chat_session_service),
):
    """
    Delete a chat session.
    """
    success = await chat_session_service.delete_session(session_id=session_id, user_id=user_context.user.id)
    if not success:
        raise HTTPException(status_code=404, detail="Chat session not found")
    return {"ok": True}

class ChatSessionScopeUpdate(BaseModel):
    scope_type: str
    scope_id: int | None = None

@router.put("/sessions/{session_id}/scope", response_model=ChatSession)
async def update_session_scope(
    session_id: int,
    scope_data: ChatSessionScopeUpdate,
    user_context: UserContext = Depends(get_authenticated_user_context),
    chat_session_service: ChatSessionService = Depends(get_chat_session_service),
):
    """
    Update the scope of a chat session.
    """
    session = await chat_session_service.get_session_by_id(session_id, user_context.user.id)
    if not session:
        raise HTTPException(status_code=404, detail="Chat session not found")
    
    session.scope_type = scope_data.scope_type
    session.scope_id = scope_data.scope_id
    
    await chat_session_service.session.commit()
    await chat_session_service.session.refresh(session)
    
    return session


class ChatSessionTitleUpdate(BaseModel):
    title: str

@router.put("/sessions/{session_id}/title", response_model=ChatSession)
async def update_session_title(
    session_id: int,
    title_data: ChatSessionTitleUpdate,
    user_context: UserContext = Depends(get_authenticated_user_context),
    chat_session_service: ChatSessionService = Depends(get_chat_session_service),
):
    """
    Update the title of a chat session.
    """
    session = await chat_session_service.update_session_title(session_id, user_context.user.id, title_data.title)
    if not session:
        raise HTTPException(status_code=404, detail="Chat session not found")
    return session


class ChatMessageCreate(BaseModel):
    content: str


@router.post("/sessions/{session_id}/messages", response_model=ChatMessage)
async def send_chat_message(
    session_id: int,
    message_data: ChatMessageCreate,
    user_context: UserContext = Depends(get_authenticated_user_context),
    chat_session_service: ChatSessionService = Depends(get_chat_session_service),
):
    """
    Send a message to a chat session. Returns the saved user message.
    The AI response will be streamed via the SSE endpoint.
    """
    # Verify session exists and belongs to user
    chat_session = await chat_session_service.get_session_by_id(session_id, user_context.user.id)
    if not chat_session:
        raise HTTPException(status_code=404, detail="Chat session not found")
    
    if not message_data.content or not message_data.content.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")
    
    # Save user message
    try:
        saved_message = await chat_session_service.save_message(session_id, "user", message_data.content)
        logger.info(f"Saved user message to session {session_id}, message_id: {saved_message.id}")
        return saved_message
    except Exception as e:
        logger.error(f"Failed to save user message: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to save message")


@router.get("/sessions/{session_id}/stream")
async def stream_chat_response(
    session_id: int,
    message_id: int,
    skill: Optional[str] = None,
    user_context: UserContext = Depends(get_authenticated_user_context),
    chat_agent_service: ChatAgentService = Depends(get_chat_agent_service),
    chat_session_service: ChatSessionService = Depends(get_chat_session_service),
):
    """
    Stream AI response for a chat message using Server-Sent Events (SSE).
    
    This endpoint streams the AI's response to a user message. The user message
    should be sent first via POST /sessions/{session_id}/messages, and then
    this endpoint should be called with the returned message_id.
    
    The stream sends events in the following format:
    - event: stream_chunk - incremental text chunks
    - event: end_stream - final complete response
    - event: error - error occurred
    """
    # Verify session exists and belongs to user
    chat_session = await chat_session_service.get_session_by_id(session_id, user_context.user.id)
    if not chat_session:
        raise HTTPException(status_code=404, detail="Chat session not found")
    
    # Get the user message to respond to
    messages = await chat_session_service.get_session_messages(session_id, user_context.user.id)
    user_message_obj = next((m for m in messages if m.id == message_id and m.role == "user"), None)
    
    if not user_message_obj:
        raise HTTPException(status_code=404, detail="Message not found")
    
    user_message = user_message_obj.content
    
    async def generate_stream():
        """Generator function that yields SSE events with its own database session"""
        logger.info(f"[Session {session_id}] SSE generate_stream() started for message_id: {message_id}")
        
        # Use a fresh session for the entire duration of the stream to prevent premature closure
        async with async_session() as session:
            local_session_service = ChatSessionService(session)
            assistant_response = ""
            response_message_id = str(uuid.uuid4())
            chunk_count = 0
            
            try:
                # Stream the AI response
                logger.info(f"[Session {session_id}] Starting iteration over chat_agent_service.get_stream()...")
                async for chunk in chat_agent_service.get_stream(session_id, user_message, user_context.user.id, skill_override=skill):
                    chunk_type = chunk.get("type")
                    
                    if chunk_type == "content":
                        content = chunk.get("content")
                        if content:
                            assistant_response += content

                            event_data = {
                                "type": "stream_chunk",
                                "content": assistant_response,
                                "message_id": response_message_id
                            }
                            yield f"event: stream_chunk\ndata: {json.dumps(event_data)}\n\n"
                    
                    elif chunk_type == "status":
                        event_data = {
                            "type": "agent_status",
                            "status_type": chunk.get("status_type"),
                            "content": chunk.get("content"),
                            "message_id": response_message_id
                        }
                        yield f"event: agent_status\ndata: {json.dumps(event_data)}\n\n"
                        
                    elif chunk_type == "chat_context":
                        # Send context IDs for graph filtering
                        context_data = {
                            "type": "chat_context",
                            "entity_ids": chunk.get("entity_ids", []),
                            "document_ids": chunk.get("document_ids", []),
                            "message_id": response_message_id
                        }
                        yield f"event: chat_context\ndata: {json.dumps(context_data)}\n\n"

                    elif chunk_type == "error":
                        # Send error event
                        error_data = {
                            "type": "error",
                            "content": chunk.get("content"),
                            "message_id": response_message_id
                        }
                        yield f"event: error\ndata: {json.dumps(error_data)}\n\n"
                
                logger.info(f"[Session {session_id}] Stream iteration completed. Total chunks: {chunk_count}, Total response: {len(assistant_response)} chars")
                
                # Send end_stream event (raw markdown — frontend renders via marked.js)
                event_data = {
                    "type": "end_stream",
                    "content": assistant_response,
                    "message_id": response_message_id
                }
                yield f"event: end_stream\ndata: {json.dumps(event_data)}\n\n"
                
                # Save assistant response after streaming completes using the fresh session
                if assistant_response:
                    try:
                        logger.info(f"[Session {session_id}] Saving assistant response to database...")
                        await local_session_service.save_message(session_id, "assistant", assistant_response)
                        logger.info(f"[Session {session_id}] Successfully saved assistant response")
                    except Exception as save_error:
                        logger.error(f"[Session {session_id}] Failed to save assistant response: {save_error}", exc_info=True)
                        
            except Exception as e:
                logger.error(f"Error during streaming for session {session_id}: {e}", exc_info=True)
                
                # Try to save partial response if available
                if assistant_response:
                    try:
                        await local_session_service.save_message(session_id, "assistant", assistant_response)
                        logger.info(f"[Session {session_id}] Saved partial assistant response ({len(assistant_response)} chars)")
                    except Exception as save_error:
                        logger.error(f"[Session {session_id}] Failed to save partial assistant response: {save_error}")
                
                # Send error event
                error_data = {
                    "type": "error",
                    "content": f"\n\nError: {str(e)}. Please try again.",
                    "message_id": response_message_id
                }
                yield f"event: error\ndata: {json.dumps(error_data)}\n\n"
    
    return StreamingResponse(
        generate_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable buffering in nginx
        }
    )

class ChatSuggestRequest(BaseModel):
    text: str
    session_id: int
    context: Optional[str] = None

@router.post("/sessions/{session_id}/suggest")
async def get_chat_suggestion(
    session_id: int,
    request_data: ChatSuggestRequest,
    user_context: UserContext = Depends(get_authenticated_user_context),
    chat_agent_service: ChatAgentService = Depends(get_chat_agent_service),
):
    """
    Get a Gmail-style ghost text completion suggestion for the current input.
    """
    suggestion = await chat_agent_service.get_suggestion(
        user_id=user_context.user.id,
        session_id=session_id,
        current_text=request_data.text,
        context=request_data.context
    )
    return {"prediction": suggestion}

@router.websocket("/ws/{session_id}/{user_id}")
async def chat_websocket_endpoint(
    websocket: WebSocket,
    session_id: int,
    user_id: str,
    chat_agent_service: ChatAgentService = Depends(get_chat_agent_service)
):
    channel_name = f"chat:{session_id}"
    await manager.connect(websocket, user_id, channel=channel_name)
    logger.info(f"WebSocket connected for session {session_id}, user {user_id}")
    
    # Get a database session for this WebSocket connection
    async_gen = get_session()
    db_session = await async_gen.__anext__()
    
    try:
        chat_session_service = ChatSessionService(db_session)
        
        # Verify session exists and belongs to user
        chat_session = await chat_session_service.get_session_by_id(session_id, user_id)
        if not chat_session:
            logger.error(f"Chat session {session_id} not found for user {user_id}")
            await websocket.send_text(json.dumps({"error": "Chat session not found"}))
            await websocket.close()
            return
        
        while True:
            try:
                data = await websocket.receive_text()
                logger.debug(f"Received message from session {session_id}: {len(data)} bytes")
                
                try:
                    message_data = json.loads(data)
                    user_message = message_data.get('content', '')
                    ws_skill_override = message_data.get('skill', None)

                    if not user_message or not user_message.strip():
                        logger.warning(f"Empty message received from session {session_id}")
                        await websocket.send_text(json.dumps({"error": "Message cannot be empty"}))
                        continue
                except (json.JSONDecodeError, KeyError) as e:
                    logger.error(f"Invalid message format from session {session_id}: {e}")
                    await websocket.send_text(json.dumps({"error": "Invalid message format"}))
                    continue
                
                # Save user message
                try:
                    await chat_session_service.save_message(session_id, "user", user_message)
                    logger.info(f"Saved user message to session {session_id}, length: {len(user_message)}")
                except Exception as e:
                    logger.error(f"Failed to save user message: {e}", exc_info=True)
                    # Continue anyway - don't block the chat flow
                
                # Collect assistant response chunks
                assistant_response = ""
                sent_stream_chunk = False
                stream_error = None
                
                # Generate a unique message_id for this assistant response
                response_message_id = str(uuid.uuid4())

                try:
                    async for chunk in chat_agent_service.get_stream(session_id, user_message, user_id, skill_override=ws_skill_override):
                        chunk_type = chunk.get("type")
                        
                        if chunk_type == "content":
                            content = chunk.get("content")
                            if content:
                                assistant_response += content
                                try:
                                    # Send each chunk wrapped in a structured message
                                    formatted_content = assistant_response
                                    await websocket.send_text(WebSocketMessage(
                                        type="stream_chunk",
                                        content=formatted_content,
                                        message_id=response_message_id
                                    ).json())
                                    sent_stream_chunk = True
                                except Exception as send_error:
                                    logger.error(f"Failed to send chunk to websocket: {send_error}", exc_info=True)
                                    stream_error = send_error
                                    break
                        
                        elif chunk_type == "status":
                            # Send status update
                            try:
                                await websocket.send_text(json.dumps({
                                    "type": "agent_status",
                                    "status_type": chunk.get("status_type"),
                                    "content": chunk.get("content"),
                                    "message_id": response_message_id
                                }))
                            except Exception as e:
                                logger.error(f"Failed to send status to websocket: {e}")
                        
                        elif chunk_type == "error":
                            # Stream error
                            stream_error = chunk.get("content")
                            break
                    
                    # If we never streamed (e.g., model responded at once) but we have content, emit it now
                    if assistant_response and not sent_stream_chunk:
                        formatted_content = assistant_response
                        await websocket.send_text(WebSocketMessage(
                            type="stream_chunk",
                            content=formatted_content,
                            message_id=response_message_id
                        ).json())
                        sent_stream_chunk = True
                    
                    # Send an explicit end_stream message
                    await websocket.send_text(WebSocketMessage(
                        type="end_stream",
                        content=assistant_response,
                        message_id=response_message_id
                    ).json())

                    # Save assistant response after streaming completes
                    if assistant_response:
                        try:
                            await chat_session_service.save_message(session_id, "assistant", assistant_response)
                            logger.info(f"Saved assistant response to session {session_id}, length: {len(assistant_response)}")
                        except Exception as save_error:
                            logger.error(f"Failed to save assistant response: {save_error}", exc_info=True)
                    
                    if stream_error:
                        # Send error message to client
                        error_msg = f"\n\nError: Failed to send response. Please try again."
                        await websocket.send_text(WebSocketMessage(type="error", content=error_msg, message_id=response_message_id).json())
                        
                except Exception as e:
                    logger.error(f"Error during streaming for session {session_id}: {e}", exc_info=True)
                    
                    # Try to save partial response if available
                    if assistant_response:
                        cleaned_partial = assistant_response
                        try:
                            await chat_session_service.save_message(session_id, "assistant", cleaned_partial)
                            logger.info(f"Saved partial assistant response ({len(cleaned_partial)} chars)")
                        except Exception as save_error:
                            logger.error(f"Failed to save partial assistant response: {save_error}", exc_info=True)
                    
                    # Send error message to client
                    error_msg = f"\n\nError: {str(e)}. Please try again."
                    try:
                        await websocket.send_text(WebSocketMessage(type="error", content=error_msg, message_id=response_message_id).json())
                    except Exception:
                        logger.error("Failed to send error message to client", exc_info=True)

            except WebSocketDisconnect:
                logger.info(f"WebSocket disconnected for session {session_id}, user {user_id}")
                break
            except Exception as e:
                logger.error(f"Unexpected error in WebSocket loop for session {session_id}: {e}", exc_info=True)
                try:
                    await websocket.send_text(json.dumps({"error": "An unexpected error occurred"}))
                except Exception:
                    pass
                break

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for session {session_id}, user {user_id}")
        await manager.disconnect(websocket, user_id, channel=channel_name)
    except Exception as e:
        logger.error(f"Fatal error in WebSocket endpoint: {e}", exc_info=True)
        await manager.disconnect(websocket, user_id, channel=channel_name)
    finally:
        # Close the database session
        try:
            await db_session.close()
            logger.info(f"Closed database session for WebSocket session {session_id}")
        except Exception as e:
            logger.error(f"Error closing database session: {e}", exc_info=True)
