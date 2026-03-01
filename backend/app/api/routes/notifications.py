"""
SSE (Server-Sent Events) routes for real-time notifications to Chrome extension
"""

from typing import Dict, Set
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from app.core.user_context import UserContext, get_authenticated_user_context
from app.utils.logging import get_logger
import json
import asyncio
from datetime import datetime

logger = get_logger(__name__)

router = APIRouter(
    prefix="/api/v1/notifications",
    tags=["notifications"],
)


class SSENotificationManager:
    """Manage SSE connections for users."""
    
    def __init__(self):
        # Map user_id -> set[asyncio.Queue]
        self.active_connections: Dict[str, Set[asyncio.Queue]] = {}
        self._lock = asyncio.Lock()
    
    async def connect(self, user_id: str) -> asyncio.Queue:
        """Register a new SSE connection and return a queue for sending messages."""
        queue = asyncio.Queue()
        
        async with self._lock:
            connections = self.active_connections.setdefault(user_id, set())
            connections.add(queue)
        
        logger.debug(
            "SSE connection registered for user %s. Total connections: %s",
            user_id,
            len(connections),
        )
        return queue
    
    async def disconnect(self, user_id: str, queue: asyncio.Queue):
        """Unregister an SSE connection."""
        async with self._lock:
            connections = self.active_connections.get(user_id)
            if connections and queue in connections:
                connections.discard(queue)
                
                if not connections:
                    self.active_connections.pop(user_id, None)
        
        logger.debug("SSE connection unregistered for user %s", user_id)
    
    async def send_notification(
        self,
        message: dict,
        user_id: str,
    ):
        """Send a notification to all SSE connections for a user."""
        async with self._lock:
            connections = self.active_connections.get(user_id, set()).copy()
        
        if not connections:
            logger.info("No active SSE connections for user %s (attempted to send %s)", user_id, message.get('type'))
            return
        
        logger.info("Sending %s notification to user %s (%d connections)", message.get('type'), user_id, len(connections))
        
        message_json = json.dumps(message)
        disconnected = []
        
        for queue in connections:
            try:
                await queue.put(message_json)
            except Exception as e:
                logger.error("Error sending notification to user %s: %s", user_id, e)
                disconnected.append(queue)
        
        if disconnected:
            async with self._lock:
                connections = self.active_connections.get(user_id)
                if connections:
                    for queue in disconnected:
                        connections.discard(queue)
                    
                    if not connections:
                        self.active_connections.pop(user_id, None)
    
    def get_connection_count(self, user_id: str) -> int:
        """Get the number of active connections for a user."""
        return len(self.active_connections.get(user_id, set()))
    
    def get_total_connections(self) -> int:
        """Get the total number of active connections across all users."""
        return sum(len(connections) for connections in self.active_connections.values())


# Global notification manager instance
_notification_manager: SSENotificationManager | None = None


def get_notification_manager() -> SSENotificationManager:
    """Get the global notification manager instance."""
    global _notification_manager
    if _notification_manager is None:
        _notification_manager = SSENotificationManager()
    return _notification_manager


@router.get("/stream")
async def stream_notifications(
    user_context: UserContext = Depends(get_authenticated_user_context),
):
    """
    SSE endpoint for Chrome extension notifications.
    
    Streams real-time notifications for:
    - Document processing progress
    - Document analysis completion
    - Error notifications
    """
    user_id = user_context.user.id
    manager = get_notification_manager()
    
    logger.debug(f"SSE connection attempt from user: {user_id}")
    
    # Register connection
    queue = await manager.connect(user_id)
    
    async def generate_stream():
        """Generator function that yields SSE events"""
        try:
            # Send initial connection confirmation
            connection_data = {
                "type": "connected",
                "data": {
                    "user_id": user_id,
                    "timestamp": datetime.now().isoformat(),
                    "message": "SSE connection established"
                }
            }
            yield f"event: connected\ndata: {json.dumps(connection_data)}\n\n"
            
            # Keep connection alive and send notifications
            while True:
                try:
                    # Wait for notification with timeout for heartbeat
                    try:
                        message_json = await asyncio.wait_for(queue.get(), timeout=30.0)
                        
                        # Send the notification
                        yield f"data: {message_json}\n\n"
                        
                    except asyncio.TimeoutError:
                        # Send heartbeat to keep connection alive
                        heartbeat_data = {
                            "type": "heartbeat",
                            "data": {
                                "timestamp": datetime.now().isoformat()
                            }
                        }
                        yield f"event: heartbeat\ndata: {json.dumps(heartbeat_data)}\n\n"
                
                except Exception as e:
                    logger.error(f"Error in SSE stream for user {user_id}: {e}")
                    break
        
        except Exception as e:
            logger.error(f"Fatal error in SSE stream for user {user_id}: {e}")
        finally:
            # Unregister connection
            await manager.disconnect(user_id, queue)
            logger.debug(f"SSE connection closed for user {user_id}")
    
    return StreamingResponse(
        generate_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable buffering in nginx
        }
    )


@router.get("/stats")
async def notification_stats():
    """Get SSE connection statistics (for debugging/monitoring)"""
    manager = get_notification_manager()
    return {
        "total_connections": manager.get_total_connections(),
        "active_users": len(manager.active_connections),
        "timestamp": datetime.now().isoformat()
    }

