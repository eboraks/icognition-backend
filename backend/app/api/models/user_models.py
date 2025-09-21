"""
User management API request and response models
"""

from typing import Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field, EmailStr


class UserProfileResponse(BaseModel):
    """User profile response model"""
    
    id: int
    firebase_uid: str
    email: Optional[str] = None
    display_name: Optional[str] = None
    photo_url: Optional[str] = None
    is_active: bool
    is_verified: bool
    first_login: Optional[datetime] = None
    last_login: Optional[datetime] = None
    last_active: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    preferences: Optional[Dict[str, Any]] = None


class UserProfileUpdateRequest(BaseModel):
    """User profile update request model"""
    
    email: Optional[EmailStr] = None
    display_name: Optional[str] = Field(None, max_length=255)
    photo_url: Optional[str] = Field(None, max_length=500)
    preferences: Optional[Dict[str, Any]] = None


class UserActivityResponse(BaseModel):
    """User activity response model"""
    
    user_id: int
    firebase_uid: str
    last_active: Optional[datetime] = None
    last_login: Optional[datetime] = None
    first_login: Optional[datetime] = None
    total_bookmarks: int = 0
    processed_bookmarks: int = 0
    pending_bookmarks: int = 0


class UserStatsResponse(BaseModel):
    """User statistics response model"""
    
    user_id: int
    firebase_uid: str
    total_bookmarks: int
    processed_bookmarks: int
    pending_bookmarks: int
    last_bookmark_date: Optional[datetime] = None
    account_age_days: Optional[int] = None


class UserListResponse(BaseModel):
    """User list response model (for admin purposes)"""
    
    users: list[UserProfileResponse]
    total: int
    page: int
    page_size: int
    has_next: bool
    has_previous: bool
