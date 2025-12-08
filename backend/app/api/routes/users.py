"""
User management API routes
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.user_context import get_authenticated_user_context, UserContext
from app.db.database import get_session
from app.api.models.user_models import UserProfileResponse
from app.models import User
from app.utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/users", tags=["users"])


@router.get("/profile", response_model=UserProfileResponse)
async def get_user_profile(
    user_context: UserContext = Depends(get_authenticated_user_context),
    session: AsyncSession = Depends(get_session)
):
    """
    Get current user's profile information
    """
    if not user_context.user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found"
        )
    
    # Refresh user from database to ensure we have the latest data including role
    try:
        result = await session.execute(
            select(User).where(User.id == user_context.user_id)
        )
        user = result.scalar_one_or_none()
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found in database"
            )
        
        return UserProfileResponse(
            id=user.id,
            firebase_uid=user.id,  # User.id is the Firebase UID
            email=user.email,
            display_name=user.display_name,
            photo_url=user.photo_url,
            is_active=user.is_active,
            is_verified=user.is_verified,
            role=user.role,
            first_login=user.first_login,
            last_login=user.last_login,
            last_active=user.last_active,
            created_at=user.created_at,
            updated_at=user.updated_at,
            preferences=user.preferences
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching user profile: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch user profile"
        )