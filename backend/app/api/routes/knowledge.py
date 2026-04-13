from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.user_context import UserContext, get_authenticated_user_context
from app.db.database import get_session
from app.services.knowledge_service import KnowledgeService
from app.services.graph_service import GraphService
from app.api.models.graph_schemas import (
    SearchResponse, EntityRead, NeighborhoodResponse,
    RelationshipRead, RelationshipSummary, DocumentSummary,
    EntitySummary, SubgraphRequest, DocumentRead,
    ThemeSummary, ThemeListResponse, ReassignRequest,
    ThemeUpdateRequest, ReclusterResponse,
)
from app.services.theme_service import ThemeService
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


# ── Graph exploration endpoints ───────────────────────────────────────────────


@router.get("/graph/discovery", response_model=NeighborhoodResponse)
async def graph_discovery(
    source: Optional[str] = Query(None, description="Filter by document source domain"),
    theme: Optional[int] = Query(None, description="Filter by theme ID"),
    research: Optional[int] = Query(None, description="Filter by research session ID"),
    limit: int = Query(30, ge=1, le=50),
    user_context: UserContext = Depends(get_authenticated_user_context),
    session: AsyncSession = Depends(get_session),
):
    """Return popular + recent entities for the discovery hub landing page."""
    svc = GraphService(session)
    return await svc.get_discovery_graph(
        user_id=user_context.user.id,
        source=source,
        theme_id=theme,
        research_session_id=research,
        limit=limit,
    )


@router.get("/research-sessions")
async def list_research_sessions(
    user_context: UserContext = Depends(get_authenticated_user_context),
    session: AsyncSession = Depends(get_session),
):
    """List all research sessions for the authenticated user."""
    svc = GraphService(session)
    sessions = await svc.get_research_sessions(user_context.user.id)
    return {"research_sessions": sessions}


@router.get("/graph/sources")
async def graph_sources(
    user_context: UserContext = Depends(get_authenticated_user_context),
    session: AsyncSession = Depends(get_session),
):
    """Return document sources grouped by domain with counts."""
    svc = GraphService(session)
    sources = await svc.get_document_sources(user_context.user.id)
    return {"sources": sources}


@router.get("/graph/search", response_model=SearchResponse)
async def graph_search(
    q: str = Query(..., min_length=1),
    result_type: Optional[str] = Query(None, pattern="^(entity|relationship|document)$"),
    entity_type: Optional[str] = None,
    limit: int = Query(20, ge=1, le=100),
    threshold: float = Query(0.3, ge=0.0, le=1.0),
    enrich: bool = Query(False, description="Include KG context for matched entities"),
    user_context: UserContext = Depends(get_authenticated_user_context),
    session: AsyncSession = Depends(get_session),
):
    """Fuzzy search across entities and relationships using pg_trgm."""
    svc = GraphService(session)
    search_result = await svc.search(
        q=q, user_id=user_context.user.id,
        result_type=result_type, entity_type=entity_type,
        limit=limit, threshold=threshold,
    )

    # Optionally enrich with KG context (relationships + documents for matched entities)
    if enrich:
        entity_ids = [
            r["id"] for r in search_result["results"]
            if r["result_type"] == "entity"
        ]
        if entity_ids:
            search_result["kg_context"] = await svc.get_entity_kg_context(entity_ids[:10])

    return search_result


@router.get("/graph/entities/{entity_id}", response_model=EntityRead)
async def graph_get_entity(
    entity_id: int,
    user_context: UserContext = Depends(get_authenticated_user_context),
    session: AsyncSession = Depends(get_session),
):
    """Fetch full entity detail including linked documents."""
    svc = GraphService(session)
    result = await svc.get_entity(entity_id)
    if not result:
        raise HTTPException(status_code=404, detail="Entity not found")
    return result


@router.get("/graph/entities/{entity_id}/neighborhood", response_model=NeighborhoodResponse)
async def graph_get_neighborhood(
    entity_id: int,
    depth: int = Query(1, ge=1, le=2),
    limit: int = Query(50, ge=1, le=100),
    user_context: UserContext = Depends(get_authenticated_user_context),
    session: AsyncSession = Depends(get_session),
):
    """Fetch 1-hop neighborhood of an entity."""
    svc = GraphService(session)
    return await svc.get_neighborhood(entity_id, depth=depth, limit=limit)


@router.get("/graph/entities/{entity_id}/relationships", response_model=list[RelationshipSummary])
async def graph_get_entity_relationships(
    entity_id: int,
    direction: str = Query("both", pattern="^(from|to|both)$"),
    limit: int = Query(50, ge=1, le=100),
    user_context: UserContext = Depends(get_authenticated_user_context),
    session: AsyncSession = Depends(get_session),
):
    """List relationships connected to an entity."""
    svc = GraphService(session)
    return await svc.get_entity_relationships(entity_id, direction=direction, limit=limit)


@router.get("/graph/entities/{entity_id}/documents", response_model=list[DocumentSummary])
async def graph_get_entity_documents(
    entity_id: int,
    limit: int = Query(50, ge=1, le=100),
    user_context: UserContext = Depends(get_authenticated_user_context),
    session: AsyncSession = Depends(get_session),
):
    """List documents an entity appears in."""
    svc = GraphService(session)
    return await svc.get_entity_documents(entity_id, limit=limit)


@router.get("/graph/relationships/{relationship_id}", response_model=RelationshipRead)
async def graph_get_relationship(
    relationship_id: int,
    user_context: UserContext = Depends(get_authenticated_user_context),
    session: AsyncSession = Depends(get_session),
):
    """Fetch full relationship detail."""
    svc = GraphService(session)
    result = await svc.get_relationship(relationship_id)
    if not result:
        raise HTTPException(status_code=404, detail="Relationship not found")
    return result


@router.post("/graph/subgraph", response_model=NeighborhoodResponse)
async def graph_get_subgraph(
    request: SubgraphRequest,
    user_context: UserContext = Depends(get_authenticated_user_context),
    session: AsyncSession = Depends(get_session),
):
    """Batch-fetch a subgraph for multiple entity IDs."""
    svc = GraphService(session)
    return await svc.get_subgraph(request.entity_ids, request.include_relationships)


@router.get("/graph/documents/{document_id}", response_model=DocumentRead)
async def graph_get_document(
    document_id: int,
    user_context: UserContext = Depends(get_authenticated_user_context),
    session: AsyncSession = Depends(get_session),
):
    """Fetch full document detail including ai_markdown_content."""
    svc = GraphService(session)
    result = await svc.get_document(document_id)
    if not result:
        raise HTTPException(status_code=404, detail="Document not found")
    return result


@router.get("/graph/documents/{document_id}/subgraph", response_model=NeighborhoodResponse)
async def graph_get_document_subgraph(
    document_id: int,
    user_context: UserContext = Depends(get_authenticated_user_context),
    session: AsyncSession = Depends(get_session),
):
    """Fetch full subgraph for a document."""
    svc = GraphService(session)
    return await svc.get_document_subgraph(document_id)


# ── Theme endpoints ──────────────────────────────────

@router.get("/themes", response_model=ThemeListResponse)
async def list_themes(
    user_context: UserContext = Depends(get_authenticated_user_context),
    session: AsyncSession = Depends(get_session),
):
    """List all active themes for the authenticated user."""
    svc = ThemeService(session)
    themes = await svc.get_themes(user_context.user.id)
    return {"themes": themes}


@router.get("/themes/{theme_id}/documents", response_model=list[DocumentSummary])
async def get_theme_documents(
    theme_id: int,
    user_context: UserContext = Depends(get_authenticated_user_context),
    session: AsyncSession = Depends(get_session),
):
    """Get documents belonging to a theme."""
    svc = ThemeService(session)
    return await svc.get_theme_documents(theme_id, user_context.user.id)


@router.post("/themes/{theme_id}/reassign")
async def reassign_document_theme(
    theme_id: int,
    request: ReassignRequest,
    user_context: UserContext = Depends(get_authenticated_user_context),
    session: AsyncSession = Depends(get_session),
):
    """Move a document from this theme to another."""
    svc = ThemeService(session)
    success = await svc.reassign_document(
        document_id=request.document_id,
        from_theme_id=theme_id,
        to_theme_id=request.to_theme_id,
        user_id=user_context.user.id,
    )
    if not success:
        raise HTTPException(status_code=400, detail="Reassignment failed")
    return {"ok": True}


@router.post("/themes/recluster", response_model=ReclusterResponse)
async def recluster_themes(
    user_context: UserContext = Depends(get_authenticated_user_context),
    session: AsyncSession = Depends(get_session),
):
    """Trigger full theme re-clustering for the authenticated user."""
    svc = ThemeService(session)
    return await svc.recluster_themes(user_context.user.id)


@router.put("/themes/{theme_id}")
async def update_theme(
    theme_id: int,
    request: ThemeUpdateRequest,
    user_context: UserContext = Depends(get_authenticated_user_context),
    session: AsyncSession = Depends(get_session),
):
    """Rename or recolor a theme."""
    svc = ThemeService(session)
    success = await svc.update_theme(
        theme_id=theme_id,
        user_id=user_context.user.id,
        label=request.label,
        color=request.color,
    )
    if not success:
        raise HTTPException(status_code=404, detail="Theme not found")
    return {"ok": True}

