"""
FastAPI dependencies for document ownership verification
"""

from typing import Optional, List, Union
from fastapi import Depends, HTTPException, status, Path, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_session
from app.core.user_context import UserContext, get_authenticated_user_context
from app.core.document_ownership import (
    DocumentOwnershipVerifier,
    DocumentAccessController,
    verify_document_ownership,
    require_document_ownership
)
from app.db.models import Document, Bookmark
from app.utils.logging import get_logger

logger = get_logger(__name__)


async def get_document_ownership_verifier(
    session: AsyncSession = Depends(get_session)
) -> DocumentOwnershipVerifier:
    """Dependency to get document ownership verifier"""
    return DocumentOwnershipVerifier(session)


async def get_document_access_controller(
    session: AsyncSession = Depends(get_session)
) -> DocumentAccessController:
    """Dependency to get document access controller"""
    return DocumentAccessController(session)


async def verify_document_ownership_dependency(
    document_id: int = Path(..., description="Document ID"),
    document_type: str = Query("document", description="Type of document (document or bookmark)"),
    user_context: UserContext = Depends(get_authenticated_user_context),
    session: AsyncSession = Depends(get_session)
) -> bool:
    """
    FastAPI dependency to verify document ownership.
    Returns True if the document is owned by the authenticated user.
    """
    if not user_context.is_authenticated:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required"
        )
    
    return await verify_document_ownership(
        session, document_id, user_context.firebase_uid, document_type
    )


async def require_document_ownership_dependency(
    document_id: int = Path(..., description="Document ID"),
    document_type: str = Query("document", description="Type of document (document or bookmark)"),
    user_context: UserContext = Depends(get_authenticated_user_context),
    session: AsyncSession = Depends(get_session)
) -> None:
    """
    FastAPI dependency to require document ownership.
    Raises HTTPException if the document is not owned by the authenticated user.
    """
    if not user_context.is_authenticated:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required"
        )
    
    await require_document_ownership(
        session, document_id, user_context.firebase_uid, document_type
    )


async def get_user_document_count_dependency(
    document_type: str = Query("document", description="Type of document (document or bookmark)"),
    status_filter: Optional[str] = Query(None, description="Filter by status"),
    user_context: UserContext = Depends(get_authenticated_user_context),
    session: AsyncSession = Depends(get_session)
) -> int:
    """
    FastAPI dependency to get user document count.
    Returns the count of documents owned by the authenticated user.
    """
    if not user_context.is_authenticated:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required"
        )
    
    from app.core.document_ownership import get_user_document_count
    
    return await get_user_document_count(
        session, user_context.firebase_uid, document_type, status_filter
    )


async def get_user_documents_dependency(
    document_type: str = Query("document", description="Type of document (document or bookmark)"),
    limit: int = Query(50, ge=1, le=100, description="Maximum number of documents to return"),
    offset: int = Query(0, ge=0, description="Number of documents to skip"),
    status_filter: Optional[str] = Query(None, description="Filter by status"),
    user_context: UserContext = Depends(get_authenticated_user_context),
    session: AsyncSession = Depends(get_session)
) -> List[Union[Document, Bookmark]]:
    """
    FastAPI dependency to get user documents.
    Returns documents owned by the authenticated user.
    """
    if not user_context.is_authenticated:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required"
        )
    
    controller = DocumentAccessController(session)
    return await controller.get_user_documents_with_ownership_check(
        user_context.firebase_uid, document_type, limit, offset, status_filter
    )


# Specific document type dependencies
async def verify_document_ownership_dependency(
    document_id: int = Path(..., description="Document ID"),
    user_context: UserContext = Depends(get_authenticated_user_context),
    session: AsyncSession = Depends(get_session)
) -> None:
    """FastAPI dependency to verify document ownership (Document type)"""
    await require_document_ownership_dependency(document_id, "document", user_context, session)


async def verify_bookmark_ownership_dependency(
    bookmark_id: int = Path(..., description="Bookmark ID"),
    user_context: UserContext = Depends(get_authenticated_user_context),
    session: AsyncSession = Depends(get_session)
) -> None:
    """FastAPI dependency to verify bookmark ownership (Bookmark type)"""
    await require_document_ownership_dependency(bookmark_id, "bookmark", user_context, session)


# Utility dependencies for common operations
async def get_user_documents_dependency(
    limit: int = Query(50, ge=1, le=100, description="Maximum number of documents to return"),
    offset: int = Query(0, ge=0, description="Number of documents to skip"),
    status_filter: Optional[str] = Query(None, description="Filter by status"),
    user_context: UserContext = Depends(get_authenticated_user_context),
    session: AsyncSession = Depends(get_session)
) -> List[Document]:
    """FastAPI dependency to get user documents (Document type)"""
    documents = await get_user_documents_dependency(
        "document", limit, offset, status_filter, user_context, session
    )
    return [doc for doc in documents if isinstance(doc, Document)]


async def get_user_bookmarks_dependency(
    limit: int = Query(50, ge=1, le=100, description="Maximum number of bookmarks to return"),
    offset: int = Query(0, ge=0, description="Number of bookmarks to skip"),
    status_filter: Optional[str] = Query(None, description="Filter by processing status"),
    user_context: UserContext = Depends(get_authenticated_user_context),
    session: AsyncSession = Depends(get_session)
) -> List[Bookmark]:
    """FastAPI dependency to get user bookmarks (Bookmark type)"""
    bookmarks = await get_user_documents_dependency(
        "bookmark", limit, offset, status_filter, user_context, session
    )
    return [bookmark for bookmark in bookmarks if isinstance(bookmark, Bookmark)]
