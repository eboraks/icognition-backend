"""
Authentication middleware for FastAPI using Firebase ID tokens.
"""

from typing import Optional, Dict, Any
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.core.firebase_auth import firebase_auth
from app.log import get_logger

logger = get_logger(__name__)

# HTTP Bearer token security scheme
security = HTTPBearer(auto_error=False)

async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> Dict[str, Any]:
    """
    FastAPI dependency to get the current authenticated user from Firebase ID token.
    
    Args:
        credentials: HTTP Bearer token credentials
        
    Returns:
        Dict containing user information from decoded Firebase token
        
    Raises:
        HTTPException: If authentication fails
    """
    if not credentials:
        logger.warning("No authorization header provided")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Verify the Firebase ID token
    try:
        decoded_token = await firebase_auth.verify_id_token(credentials.credentials)
        return decoded_token
    except HTTPException:
        # Re-raise HTTPExceptions from firebase_auth
        raise
    except Exception as e:
        logger.error(f"Unexpected error in authentication: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication failed"
        )

async def get_current_user_uid(
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> str:
    """
    FastAPI dependency to get the current user's UID.
    
    Args:
        current_user: Current user data from get_current_user
        
    Returns:
        Firebase user UID
    """
    return current_user["uid"]

async def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> Optional[Dict[str, Any]]:
    """
    FastAPI dependency to get the current user if authenticated, None otherwise.
    This is useful for endpoints that work for both authenticated and unauthenticated users.
    
    Args:
        credentials: HTTP Bearer token credentials
        
    Returns:
        Dict containing user information or None if not authenticated
    """
    if not credentials:
        return None
    
    try:
        decoded_token = await firebase_auth.verify_id_token(credentials.credentials)
        return decoded_token
    except HTTPException:
        # Return None for invalid tokens instead of raising exception
        logger.info("Invalid token provided for optional authentication")
        return None
    except Exception as e:
        logger.warning(f"Error in optional authentication: {e}")
        return None

async def verify_user_access(
    resource_user_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> bool:
    """
    Verify that the current user has access to a resource belonging to a specific user.
    
    Args:
        resource_user_id: The user ID that owns the resource
        current_user: Current authenticated user
        
    Returns:
        True if access is allowed
        
    Raises:
        HTTPException: If access is denied
    """
    current_user_id = current_user["uid"]
    
    if current_user_id != resource_user_id:
        logger.warning(f"User {current_user_id} attempted to access resource belonging to {resource_user_id}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: You can only access your own resources"
        )
    
    return True

async def extract_token_from_websocket(websocket_query_params: dict) -> str:
    """
    Extract Firebase ID token from WebSocket query parameters.
    
    Args:
        websocket_query_params: WebSocket query parameters dict
        
    Returns:
        Firebase ID token
        
    Raises:
        HTTPException: If token is missing or invalid
    """
    token = websocket_query_params.get("token")
    if not token:
        logger.warning("No token provided in WebSocket connection")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token required for WebSocket connection"
        )
    
    return token

async def verify_websocket_auth(
    token: str
) -> Dict[str, Any]:
    """
    Verify Firebase ID token for WebSocket connections.
    
    Args:
        token: Firebase ID token
        
    Returns:
        Dict containing user information from decoded Firebase token
        
    Raises:
        HTTPException: If authentication fails
    """
    try:
        decoded_token = await firebase_auth.verify_id_token(token)
        logger.info(f"WebSocket authentication successful for user: {decoded_token.get('uid')}")
        return decoded_token
    except HTTPException:
        # Re-raise HTTPExceptions from firebase_auth
        raise
    except Exception as e:
        logger.error(f"WebSocket authentication error: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="WebSocket authentication failed"
        )
