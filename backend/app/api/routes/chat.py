from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from typing import List
from app.services.chat_session_service import ChatSessionService, get_chat_session_service
from app.core.user_context import UserContext, get_authenticated_user_context
from app.models import ChatSession, ChatMessage
from pydantic import BaseModel
from app.api.routes.websocket import manager
from app.services.chat_agent_service import get_chat_agent_service, ChatAgentService
from app.db.database import get_session
from sqlalchemy.ext.asyncio import AsyncSession
import json
import logging

logger = logging.getLogger(__name__)

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
    Create a new chat session.
    """
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
    return await chat_session_service.get_user_sessions(user_id=user_context.user.id)

@router.get("/sessions/{session_id}/messages", response_model=List[ChatMessage])
async def get_session_messages(
    session_id: int,
    user_context: UserContext = Depends(get_authenticated_user_context),
    chat_session_service: ChatSessionService = Depends(get_chat_session_service),
):
    """
    Get all messages for a specific chat session.
    """
    # TODO: Add validation to ensure the user owns the session
    return await chat_session_service.get_session_messages(session_id=session_id, user_id=user_context.user.id)

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
                stream_error = None
                
                try:
                    async for chunk in chat_agent_service.get_stream(session_id, user_message, user_id):
                        if chunk:
                            assistant_response += chunk
                            try:
                                await websocket.send_text(chunk)
                            except Exception as send_error:
                                logger.error(f"Failed to send chunk to websocket: {send_error}", exc_info=True)
                                stream_error = send_error
                                break
                    
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
                        await websocket.send_text(error_msg)
                        
                except Exception as e:
                    logger.error(f"Error during streaming for session {session_id}: {e}", exc_info=True)
                    
                    # Try to save partial response if available
                    if assistant_response:
                        try:
                            await chat_session_service.save_message(session_id, "assistant", assistant_response)
                            logger.info(f"Saved partial assistant response ({len(assistant_response)} chars)")
                        except Exception as save_error:
                            logger.error(f"Failed to save partial assistant response: {save_error}", exc_info=True)
                    
                    # Send error message to client
                    error_msg = f"\n\nError: {str(e)}. Please try again."
                    try:
                        await websocket.send_text(error_msg)
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
