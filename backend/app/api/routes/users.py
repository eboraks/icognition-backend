"""
User management API routes
"""

from fastapi import APIRouter

router = APIRouter(prefix="/users", tags=["users"])

# All user endpoints have been removed as they are not part of core functionality
# Removed endpoints:
# - /profile (GET, PUT)
# - /activity (GET)
# - /stats (GET)
# - /refresh-activity (POST)
# - /account (DELETE)
# - /admin/list (GET)