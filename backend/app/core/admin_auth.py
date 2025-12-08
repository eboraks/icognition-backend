"""
Admin authorization utilities
"""

from fastapi import HTTPException, status, Depends
from app.core.user_context import get_authenticated_user_context, UserContext
from app.utils.logging import get_logger

logger = get_logger(__name__)


async def require_admin(
    user_context: UserContext = Depends(get_authenticated_user_context)
) -> UserContext:
    """
    FastAPI dependency to require admin role (sysadmin)
    
    Args:
        user_context: Authenticated user context
        
    Returns:
        User context if user is admin
        
    Raises:
        HTTPException: 403 if user is not admin
    """
    if not user_context.is_authenticated:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required"
        )
    
    if not user_context.user or user_context.user.role != "sysadmin":
        logger.warning(f"Non-admin user {user_context.user_id} attempted to access admin endpoint")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required. Only users with 'sysadmin' role can access this endpoint."
        )
    
    return user_context

