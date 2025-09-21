"""
User management API routes
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timedelta

from app.db.database import get_session
from app.core.user_context import UserContext, get_authenticated_user_context, get_active_user_context
from app.services.user_service import UserService
from app.services.bookmark_service import BookmarkService
from app.api.models.user_models import (
    UserProfileResponse,
    UserProfileUpdateRequest,
    UserActivityResponse,
    UserStatsResponse,
    UserListResponse
)
from app.utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/profile", response_model=UserProfileResponse)
async def get_user_profile(
    user_context: UserContext = Depends(get_authenticated_user_context),
    session: AsyncSession = Depends(get_session)
):
    """Get current user's profile information"""
    try:
        user = user_context.user
        
        return UserProfileResponse(
            id=user.id,
            firebase_uid=user.firebase_uid,
            email=user.email,
            display_name=user.display_name,
            photo_url=user.photo_url,
            is_active=user.is_active,
            is_verified=user.is_verified,
            first_login=user.first_login,
            last_login=user.last_login,
            last_active=user.last_active,
            created_at=user.created_at,
            updated_at=user.updated_at,
            preferences=user.preferences
        )
    except Exception as e:
        logger.error(f"Error getting user profile: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve user profile"
        )


@router.put("/profile", response_model=UserProfileResponse)
async def update_user_profile(
    profile_update: UserProfileUpdateRequest,
    user_context: UserContext = Depends(get_authenticated_user_context),
    session: AsyncSession = Depends(get_session)
):
    """Update current user's profile information"""
    try:
        user = user_context.user
        
        # Update user profile
        success = await UserService.update_user_profile(
            session=session,
            user_id=user.id,
            email=profile_update.email,
            display_name=profile_update.display_name,
            photo_url=profile_update.photo_url,
            preferences=profile_update.preferences
        )
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update user profile"
            )
        
        # Refresh user data
        updated_user = await UserService.get_user_by_firebase_uid(session, user.firebase_uid)
        if not updated_user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found after update"
            )
        
        return UserProfileResponse(
            id=updated_user.id,
            firebase_uid=updated_user.firebase_uid,
            email=updated_user.email,
            display_name=updated_user.display_name,
            photo_url=updated_user.photo_url,
            is_active=updated_user.is_active,
            is_verified=updated_user.is_verified,
            first_login=updated_user.first_login,
            last_login=updated_user.last_login,
            last_active=updated_user.last_active,
            created_at=updated_user.created_at,
            updated_at=updated_user.updated_at,
            preferences=updated_user.preferences
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating user profile: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update user profile"
        )


@router.get("/activity", response_model=UserActivityResponse)
async def get_user_activity(
    user_context: UserContext = Depends(get_authenticated_user_context),
    session: AsyncSession = Depends(get_session)
):
    """Get current user's activity information"""
    try:
        user = user_context.user
        bookmark_service = BookmarkService()
        
        # Get bookmark statistics
        total_bookmarks = await bookmark_service.count_user_bookmarks(session, user.firebase_uid)
        processed_bookmarks = await bookmark_service.count_user_bookmarks(
            session, user.firebase_uid, is_processed=True
        )
        pending_bookmarks = total_bookmarks - processed_bookmarks
        
        return UserActivityResponse(
            user_id=user.id,
            firebase_uid=user.firebase_uid,
            last_active=user.last_active,
            last_login=user.last_login,
            first_login=user.first_login,
            total_bookmarks=total_bookmarks,
            processed_bookmarks=processed_bookmarks,
            pending_bookmarks=pending_bookmarks
        )
    except Exception as e:
        logger.error(f"Error getting user activity: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve user activity"
        )


@router.get("/stats", response_model=UserStatsResponse)
async def get_user_stats(
    user_context: UserContext = Depends(get_authenticated_user_context),
    session: AsyncSession = Depends(get_session)
):
    """Get current user's statistics"""
    try:
        user = user_context.user
        bookmark_service = BookmarkService()
        
        # Get bookmark statistics
        total_bookmarks = await bookmark_service.count_user_bookmarks(session, user.firebase_uid)
        processed_bookmarks = await bookmark_service.count_user_bookmarks(
            session, user.firebase_uid, is_processed=True
        )
        pending_bookmarks = total_bookmarks - processed_bookmarks
        
        # Get last bookmark date
        bookmarks = await bookmark_service.get_user_bookmarks(session, user.firebase_uid, limit=1)
        last_bookmark_date = bookmarks[0].created_at if bookmarks else None
        
        # Calculate account age
        account_age_days = None
        if user.first_login:
            account_age_days = (datetime.utcnow() - user.first_login).days
        
        return UserStatsResponse(
            user_id=user.id,
            firebase_uid=user.firebase_uid,
            total_bookmarks=total_bookmarks,
            processed_bookmarks=processed_bookmarks,
            pending_bookmarks=pending_bookmarks,
            last_bookmark_date=last_bookmark_date,
            account_age_days=account_age_days
        )
    except Exception as e:
        logger.error(f"Error getting user stats: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve user statistics"
        )


@router.post("/refresh-activity")
async def refresh_user_activity(
    user_context: UserContext = Depends(get_authenticated_user_context),
    session: AsyncSession = Depends(get_session)
):
    """Refresh user's last active timestamp"""
    try:
        user = user_context.user
        
        success = await UserService.update_last_active(session, user.id)
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update user activity"
            )
        
        return {"message": "User activity updated successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error refreshing user activity: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to refresh user activity"
        )


@router.delete("/account")
async def deactivate_user_account(
    user_context: UserContext = Depends(get_active_user_context),
    session: AsyncSession = Depends(get_session)
):
    """Deactivate current user's account"""
    try:
        user = user_context.user
        
        success = await UserService.deactivate_user(session, user.id)
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to deactivate user account"
            )
        
        return {"message": "User account deactivated successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deactivating user account: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to deactivate user account"
        )


# Admin endpoints (for future use with proper admin authentication)
@router.get("/admin/list", response_model=UserListResponse)
async def list_users_admin(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=100, description="Number of users per page"),
    active_only: bool = Query(True, description="Show only active users"),
    session: AsyncSession = Depends(get_session)
):
    """
    List all users (admin endpoint).
    Note: This endpoint should be protected with admin authentication in production.
    """
    try:
        # TODO: Add admin authentication check
        # For now, this is a placeholder for future admin functionality
        
        # This would require implementing admin user service
        # For now, return empty list
        return UserListResponse(
            users=[],
            total=0,
            page=page,
            page_size=page_size,
            has_next=False,
            has_previous=False
        )
    except Exception as e:
        logger.error(f"Error listing users: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list users"
        )
