"""
WebSocket routes for real-time communication with Chrome extension
"""

from typing import Dict, Set
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, status
from fastapi.websockets import WebSocketState
import json
import asyncio
from datetime import datetime

from app.utils.logging import get_logger
from app.core.config import settings

logger = get_logger(__name__)

router = APIRouter(tags=["websocket"])


class ConnectionManager:
    """Manage WebSocket connections for users grouped by channel."""

    DEFAULT_CHANNEL = "default"

    def __init__(self):
        # Map user_id -> channel -> set[WebSocket]
        self.active_connections: Dict[str, Dict[str, Set[WebSocket]]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, user_id: str, channel: str | None = None):
        """Accept and register a new WebSocket connection."""

        await websocket.accept()

        channel_name = channel or self.DEFAULT_CHANNEL

        async with self._lock:
            user_channels = self.active_connections.setdefault(user_id, {})
            connections = user_channels.setdefault(channel_name, set())
            connections.add(websocket)

        logger.info(
            "WebSocket connected for user %s on channel '%s'. Total connections on channel: %s",
            user_id,
            channel_name,
            self.get_connection_count(user_id, channel_name),
        )

    async def disconnect(self, websocket: WebSocket, user_id: str, channel: str | None = None):
        """Unregister a WebSocket connection."""

        channel_name = channel or self.DEFAULT_CHANNEL

        async with self._lock:
            user_channels = self.active_connections.get(user_id)
            if not user_channels:
                return

            connections = user_channels.get(channel_name)
            if connections and websocket in connections:
                connections.discard(websocket)

                if not connections:
                    user_channels.pop(channel_name, None)

            if not user_channels:
                self.active_connections.pop(user_id, None)

        logger.info("WebSocket disconnected for user %s on channel '%s'", user_id, channel_name)

    async def send_personal_message(
        self,
        message: dict,
        user_id: str,
        channel: str | None = None,
    ):
        """Send a message to connections of a specific user and channel.

        If *channel* is not provided, the message is broadcast to all channels for the user.
        """

        if user_id not in self.active_connections:
            logger.warning("No active connections for user %s", user_id)
            return

        async with self._lock:
            if channel:
                target_channels = [self.active_connections[user_id].get(channel, set())]
            else:
                target_channels = list(self.active_connections[user_id].values())

            connections = [conn for channel_conns in target_channels for conn in channel_conns]

        if not connections:
            logger.debug(
                "No active connections for user %s on channel '%s'",
                user_id,
                channel or "*",
            )
            return

        message_json = json.dumps(message)
        disconnected = []

        for connection in connections:
            try:
                if connection.client_state == WebSocketState.CONNECTED:
                    await connection.send_text(message_json)
                else:
                    disconnected.append(connection)
            except Exception as e:
                logger.error("Error sending message to user %s: %s", user_id, e)
                disconnected.append(connection)

        if disconnected:
            async with self._lock:
                user_channels = self.active_connections.get(user_id)
                if not user_channels:
                    return

                for channel_name, channel_conns in list(user_channels.items()):
                    for conn in disconnected:
                        channel_conns.discard(conn)

                    if not channel_conns:
                        user_channels.pop(channel_name, None)

                if not user_channels:
                    self.active_connections.pop(user_id, None)

    def get_connection_count(self, user_id: str, channel: str | None = None) -> int:
        """Get the number of active connections for a user (optionally by channel)."""

        user_channels = self.active_connections.get(user_id, {})
        if channel:
            return len(user_channels.get(channel, set()))
        return sum(len(connections) for connections in user_channels.values())

    def get_total_connections(self) -> int:
        """Get the total number of active connections across all users."""

        return sum(self.get_connection_count(user_id) for user_id in self.active_connections)


# Global connection manager instance
manager = ConnectionManager()


def get_connection_manager() -> ConnectionManager:
    """Get the global connection manager instance"""
    return manager


@router.websocket("/ws/{user_id}/extension")
async def websocket_endpoint(
    websocket: WebSocket,
    user_id: str
):
    """
    WebSocket endpoint for Chrome extension communication.
    
    Supports real-time updates for:
    - Document processing progress
    - Document analysis completion
    - Error notifications
    """
    
    logger.info(f"WebSocket connection attempt from user: {user_id}")
    
    # Accept the connection
    channel_name = "extension"

    await manager.connect(websocket, user_id, channel=channel_name)
    
    try:
        # Send initial connection confirmation
        await websocket.send_json({
            "type": "connected",
            "data": {
                "user_id": user_id,
                "timestamp": datetime.now().isoformat(),
                "message": "WebSocket connection established"
            }
        })
        
        # Keep connection alive and handle incoming messages
        while True:
            try:
                # Wait for messages from client (with timeout for heartbeat)
                data = await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=60.0  # 60 second timeout
                )
                
                # Parse the message
                try:
                    message = json.loads(data)
                    message_type = message.get("type", "unknown")
                    
                    # Handle ping messages
                    if message_type == "ping":
                        await websocket.send_json({
                            "type": "pong",
                            "data": {"timestamp": datetime.now().isoformat()}
                        })
                        logger.debug(f"Ping received from user {user_id}")
                    
                    else:
                        logger.debug(f"Received message from user {user_id}: {message_type}")
                
                except json.JSONDecodeError:
                    logger.warning(f"Invalid JSON received from user {user_id}")
                    await websocket.send_json({
                        "type": "error",
                        "data": "Invalid message format"
                    })
            
            except asyncio.TimeoutError:
                # Send heartbeat if no message received
                try:
                    await websocket.send_json({
                        "type": "heartbeat",
                        "data": {"timestamp": datetime.now().isoformat()}
                    })
                except Exception as e:
                    logger.error(f"Error sending heartbeat to user {user_id}: {e}")
                    break
            
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected normally for user {user_id}")
    except Exception as e:
        logger.error(f"WebSocket error for user {user_id}: {e}")
    finally:
        await manager.disconnect(websocket, user_id, channel=channel_name)


@router.get("/ws/stats")
async def websocket_stats():
    """Get WebSocket connection statistics (for debugging/monitoring)"""
    return {
        "total_connections": manager.get_total_connections(),
        "active_users": len(manager.active_connections),
        "timestamp": datetime.now().isoformat()
    }


