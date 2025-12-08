"""
Admin API endpoints for prompt management
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from typing import List, Optional
from pydantic import BaseModel, field_serializer, ConfigDict
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.admin_auth import require_admin
from app.core.user_context import UserContext
from app.db.database import get_session
from app.services.prompt_service import PromptService
from app.models import Prompt
from app.utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(
    prefix="/api/admin",
    tags=["admin"],
    responses={404: {"description": "Not found"}},
)


# Request/Response Models
class PromptCreate(BaseModel):
    prompt_type: str
    content: str
    description: Optional[str] = None


class PromptUpdate(BaseModel):
    content: str
    description: Optional[str] = None


class PromptResponse(BaseModel):
    id: int
    prompt_type: str
    version: int
    content: str
    description: Optional[str]
    is_active: bool
    created_by: Optional[str]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]
    
    @field_serializer('created_at', 'updated_at')
    def serialize_datetime(self, value: Optional[datetime], _info) -> Optional[str]:
        if value is None:
            return None
        return value.isoformat() if isinstance(value, datetime) else str(value)
    
    model_config = ConfigDict(from_attributes=True)


@router.get("/prompts", response_model=List[PromptResponse])
async def list_prompts(
    prompt_type: Optional[str] = Query(None, description="Filter by prompt type"),
    include_inactive: bool = Query(False, description="Include inactive prompts"),
    limit: Optional[int] = Query(100, ge=1, le=1000, description="Maximum number of results"),
    offset: int = Query(0, ge=0, description="Number of results to skip"),
    user_context: UserContext = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    """
    List all prompts with optional filtering
    """
    prompt_service = PromptService(session)
    prompts = await prompt_service.get_all_prompts(
        prompt_type=prompt_type,
        include_inactive=include_inactive,
        limit=limit,
        offset=offset
    )
    return prompts


@router.get("/prompts/{prompt_type}", response_model=List[PromptResponse])
async def get_prompts_by_type(
    prompt_type: str,
    include_inactive: bool = Query(False, description="Include inactive prompts"),
    user_context: UserContext = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    """
    Get all prompts for a specific type
    """
    prompt_service = PromptService(session)
    prompts = await prompt_service.get_all_prompts(
        prompt_type=prompt_type,
        include_inactive=include_inactive
    )
    return prompts


@router.get("/prompts/{prompt_type}/latest", response_model=PromptResponse)
async def get_latest_prompt(
    prompt_type: str,
    user_context: UserContext = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    """
    Get the latest active prompt for a specific type
    """
    prompt_service = PromptService(session)
    prompt = await prompt_service.get_latest_prompt(prompt_type)
    
    if not prompt:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No active prompt found for type: {prompt_type}"
        )
    
    return prompt


@router.get("/prompts/{prompt_type}/history", response_model=List[PromptResponse])
async def get_prompt_history(
    prompt_type: str,
    user_context: UserContext = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    """
    Get version history for a specific prompt type
    """
    prompt_service = PromptService(session)
    prompts = await prompt_service.get_prompt_history(prompt_type)
    return prompts


@router.post("/prompts", response_model=PromptResponse, status_code=status.HTTP_201_CREATED)
async def create_prompt(
    prompt_data: PromptCreate,
    user_context: UserContext = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    """
    Create a new prompt version
    """
    prompt_service = PromptService(session)
    
    try:
        prompt = await prompt_service.create_prompt(
            prompt_type=prompt_data.prompt_type,
            content=prompt_data.content,
            description=prompt_data.description,
            user_id=user_context.user_id
        )
        return prompt
    except Exception as e:
        logger.error(f"Error creating prompt: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create prompt: {str(e)}"
        )


@router.put("/prompts/{prompt_id}", response_model=PromptResponse)
async def update_prompt(
    prompt_id: int,
    prompt_data: PromptUpdate,
    user_context: UserContext = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    """
    Update a prompt by creating a new version
    """
    prompt_service = PromptService(session)
    
    try:
        prompt = await prompt_service.update_prompt(
            prompt_id=prompt_id,
            content=prompt_data.content,
            description=prompt_data.description
        )
        return prompt
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error updating prompt: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update prompt: {str(e)}"
        )


@router.delete("/prompts/{prompt_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_prompt(
    prompt_id: int,
    user_context: UserContext = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    """
    Soft delete a prompt (set is_active=False)
    """
    prompt_service = PromptService(session)
    
    success = await prompt_service.soft_delete_prompt(prompt_id)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Prompt with id {prompt_id} not found"
        )
    
    return None

