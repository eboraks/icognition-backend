from fastapi import APIRouter, Depends, HTTPException
from typing import Optional
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.user_context import UserContext, get_authenticated_user_context
from app.db.database import get_session
from app.services.knowledge_service import KnowledgeService
import logging

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/knowledge",
    tags=["knowledge"],
    responses={404: {"description": "Not found"}},
)


class ContextualMessageRequest(BaseModel):
    entity_id: Optional[int] = None
    document_id: Optional[int] = None


class ActionRequest(BaseModel):
    action_id: str
    entity_id: Optional[int] = None
    document_id: Optional[int] = None


@router.get("/filter-tree")
async def get_filter_tree(
    user_context: UserContext = Depends(get_authenticated_user_context),
    session: AsyncSession = Depends(get_session),
):
    """
    Get the complete filter tree structure for the authenticated user.
    Returns entities grouped by type, with documents nested under each entity.
    """
    try:
        knowledge_service = KnowledgeService(session)
        tree_data = await knowledge_service.get_filter_tree(user_context.user.id)
        return tree_data
    except Exception as e:
        logger.error(f"Error getting filter tree: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/contextual-message")
async def get_contextual_message(
    request: ContextualMessageRequest,
    user_context: UserContext = Depends(get_authenticated_user_context),
    session: AsyncSession = Depends(get_session),
):
    """
    Generate a contextual message and suggested actions based on selected filter.
    """
    try:
        knowledge_service = KnowledgeService(session)
        result = await knowledge_service.get_contextual_message(
            user_context.user.id,
            entity_id=request.entity_id,
            document_id=request.document_id,
        )
        return result
    except ValueError as e:
        logger.error(f"Error generating contextual message: {e}", exc_info=True)
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error generating contextual message: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/entity/{entity_id}/relationships")
async def get_entity_relationships(
    entity_id: int,
    user_context: UserContext = Depends(get_authenticated_user_context),
    session: AsyncSession = Depends(get_session),
):
    """
    Get all relationships for a specific entity (as source or target).
    Returns the entity details plus a list of directed relationships.
    """
    try:
        knowledge_service = KnowledgeService(session)
        result = await knowledge_service.get_entity_relationships(entity_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error getting entity relationships: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/action")
async def handle_action(
    request: ActionRequest,
    user_context: UserContext = Depends(get_authenticated_user_context),
    session: AsyncSession = Depends(get_session),
):
    """
    Handle a user action (e.g., clicking a suggested button).
    Returns a response message and any additional data.
    """
    try:
        knowledge_service = KnowledgeService(session)
        result = await knowledge_service.handle_action(
            user_context.user.id,
            action_id=request.action_id,
            entity_id=request.entity_id,
            document_id=request.document_id,
        )
        return result
    except ValueError as e:
        logger.error(f"Error handling action: {e}", exc_info=True)
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error handling action: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

