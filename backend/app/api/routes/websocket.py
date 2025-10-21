"""
WebSocket routes for real-time communication with Chrome extension
"""

from typing import Dict, Set
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, status
from fastapi.websockets import WebSocketState
import json
import asyncio
from datetime import datetime

from app.log import get_logger
from app.core.config import settings

logger = get_logger(__name__)

router = APIRouter(tags=["websocket"])


class ConnectionManager:
    """Manage WebSocket connections for users"""
    
    def __init__(self):
        # Map user_id to set of active connections
        self.active_connections: Dict[str, Set[WebSocket]] = {}
        self._lock = asyncio.Lock()
    
    async def connect(self, websocket: WebSocket, user_id: str):
        """Accept and register a new WebSocket connection"""
        await websocket.accept()
        
        async with self._lock:
            if user_id not in self.active_connections:
                self.active_connections[user_id] = set()
            self.active_connections[user_id].add(websocket)
        
        logger.info(f"WebSocket connected for user {user_id}. Total connections: {len(self.active_connections[user_id])}")
    
    async def disconnect(self, websocket: WebSocket, user_id: str):
        """Unregister a WebSocket connection"""
        async with self._lock:
            if user_id in self.active_connections:
                self.active_connections[user_id].discard(websocket)
                
                # Clean up empty sets
                if not self.active_connections[user_id]:
                    del self.active_connections[user_id]
        
        logger.info(f"WebSocket disconnected for user {user_id}")
    
    async def send_personal_message(self, message: dict, user_id: str):
        """Send a message to all connections of a specific user"""
        if user_id not in self.active_connections:
            logger.warning(f"No active connections for user {user_id}")
            return
        
        # Get a copy of connections to avoid modification during iteration
        async with self._lock:
            connections = list(self.active_connections.get(user_id, []))
        
        message_json = json.dumps(message)
        disconnected = []
        
        for connection in connections:
            try:
                if connection.client_state == WebSocketState.CONNECTED:
                    await connection.send_text(message_json)
                else:
                    disconnected.append(connection)
            except Exception as e:
                logger.error(f"Error sending message to user {user_id}: {e}")
                disconnected.append(connection)
        
        # Clean up disconnected connections
        if disconnected:
            async with self._lock:
                if user_id in self.active_connections:
                    for conn in disconnected:
                        self.active_connections[user_id].discard(conn)
                    
                    if not self.active_connections[user_id]:
                        del self.active_connections[user_id]
    
    def get_connection_count(self, user_id: str) -> int:
        """Get the number of active connections for a user"""
        return len(self.active_connections.get(user_id, set()))
    
    def get_total_connections(self) -> int:
        """Get the total number of active connections across all users"""
        return sum(len(connections) for connections in self.active_connections.values())


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
    await manager.connect(websocket, user_id)
    
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
        await manager.disconnect(websocket, user_id)


@router.get("/ws/stats")
async def websocket_stats():
    """Get WebSocket connection statistics (for debugging/monitoring)"""
    return {
        "total_connections": manager.get_total_connections(),
        "active_users": len(manager.active_connections),
        "timestamp": datetime.now().isoformat()
    }


