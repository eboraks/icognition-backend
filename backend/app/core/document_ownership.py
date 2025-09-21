"""
Document ownership verification utilities
"""

from typing import Optional, List, Dict, Any, Union, Type
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from fastapi import HTTPException, status
import logging

from app.db.models import Document, Bookmark, User
from app.services.base_service import UserIsolatedService, SecurityError
from app.services.user_service import UserService
from app.core.security_config import security_auditor, SecurityLevel
from app.utils.logging import get_logger

logger = get_logger(__name__)


class DocumentOwnershipVerifier:
    """
    Utility class for verifying document ownership and enforcing access control.
    """
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def verify_document_ownership(
        self,
        document_id: int,
        firebase_uid: str,
        document_type: str = "document"
    ) -> bool:
        """
        Verify that a document belongs to the specified user.
        
        Args:
            document_id: ID of the document to verify
            firebase_uid: Firebase UID of the user
            document_type: Type of document ("document" or "bookmark")
        
        Returns:
            True if the document belongs to the user, False otherwise
        """
        try:
            # Get user ID
            user = await UserService.get_user_by_firebase_uid(self.session, firebase_uid)
            if not user:
                logger.warning(f"User not found for Firebase UID: {firebase_uid}")
                return False
            
            # Query the appropriate table
            if document_type.lower() == "bookmark":
                result = await self.session.execute(
                    select(Bookmark).where(
                        and_(
                            Bookmark.id == document_id,
                            Bookmark.user_id == user.id
                        )
                    )
                )
                document = result.scalar_one_or_none()
            else:
                result = await self.session.execute(
                    select(Document).where(
                        and_(
                            Document.id == document_id,
                            Document.user_id == user.id
                        )
                    )
                )
                document = result.scalar_one_or_none()
            
            # Log the verification attempt
            if document:
                security_auditor.log_security_event(
                    "document_ownership_verified",
                    firebase_uid,
                    {
                        "document_id": document_id,
                        "document_type": document_type,
                        "user_id": user.id
                    },
                    SecurityLevel.MEDIUM
                )
                return True
            else:
                security_auditor.log_security_violation(
                    "unauthorized_document_access",
                    firebase_uid,
                    {
                        "document_id": document_id,
                        "document_type": document_type,
                        "user_id": user.id,
                        "reason": "Document not found or not owned by user"
                    },
                    "high"
                )
                return False
                
        except Exception as e:
            logger.error(f"Error verifying document ownership: {e}")
            security_auditor.log_security_violation(
                "document_ownership_verification_error",
                firebase_uid,
                {
                    "document_id": document_id,
                    "document_type": document_type,
                    "error": str(e)
                },
                "medium"
            )
            return False
    
    async def verify_multiple_documents_ownership(
        self,
        document_ids: List[int],
        firebase_uid: str,
        document_type: str = "document"
    ) -> Dict[int, bool]:
        """
        Verify ownership of multiple documents at once.
        
        Args:
            document_ids: List of document IDs to verify
            firebase_uid: Firebase UID of the user
            document_type: Type of documents ("document" or "bookmark")
        
        Returns:
            Dictionary mapping document_id to ownership status
        """
        try:
            # Get user ID
            user = await UserService.get_user_by_firebase_uid(self.session, firebase_uid)
            if not user:
                logger.warning(f"User not found for Firebase UID: {firebase_uid}")
                return {doc_id: False for doc_id in document_ids}
            
            # Query the appropriate table
            if document_type.lower() == "bookmark":
                result = await self.session.execute(
                    select(Bookmark).where(
                        and_(
                            Bookmark.id.in_(document_ids),
                            Bookmark.user_id == user.id
                        )
                    )
                )
                owned_documents = result.scalars().all()
            else:
                result = await self.session.execute(
                    select(Document).where(
                        and_(
                            Document.id.in_(document_ids),
                            Document.user_id == user.id
                        )
                    )
                )
                owned_documents = result.scalars().all()
            
            # Create ownership mapping
            owned_ids = {doc.id for doc in owned_documents}
            ownership_map = {doc_id: doc_id in owned_ids for doc_id in document_ids}
            
            # Log the verification attempt
            security_auditor.log_security_event(
                "multiple_document_ownership_verified",
                firebase_uid,
                {
                    "document_ids": document_ids,
                    "document_type": document_type,
                    "user_id": user.id,
                    "owned_count": len(owned_ids),
                    "total_count": len(document_ids)
                },
                SecurityLevel.MEDIUM
            )
            
            return ownership_map
            
        except Exception as e:
            logger.error(f"Error verifying multiple document ownership: {e}")
            security_auditor.log_security_violation(
                "multiple_document_ownership_verification_error",
                firebase_uid,
                {
                    "document_ids": document_ids,
                    "document_type": document_type,
                    "error": str(e)
                },
                "medium"
            )
            return {doc_id: False for doc_id in document_ids}
    
    async def get_user_document_count(
        self,
        firebase_uid: str,
        document_type: str = "document",
        status_filter: Optional[str] = None
    ) -> int:
        """
        Get the count of documents owned by a user.
        
        Args:
            firebase_uid: Firebase UID of the user
            document_type: Type of documents ("document" or "bookmark")
            status_filter: Optional status filter
        
        Returns:
            Count of documents owned by the user
        """
        try:
            # Get user ID
            user = await UserService.get_user_by_firebase_uid(self.session, firebase_uid)
            if not user:
                return 0
            
            # Build query
            if document_type.lower() == "bookmark":
                query = select(Bookmark).where(Bookmark.user_id == user.id)
                if status_filter:
                    query = query.where(Bookmark.processing_status == status_filter)
            else:
                query = select(Document).where(Document.user_id == user.id)
                if status_filter:
                    query = query.where(Document.status == status_filter)
            
            result = await self.session.execute(query)
            count = len(result.scalars().all())
            
            # Log the count operation
            security_auditor.log_security_event(
                "document_count_retrieved",
                firebase_uid,
                {
                    "document_type": document_type,
                    "status_filter": status_filter,
                    "count": count,
                    "user_id": user.id
                },
                SecurityLevel.LOW
            )
            
            return count
            
        except Exception as e:
            logger.error(f"Error getting document count: {e}")
            return 0
    
    async def get_user_document_ids(
        self,
        firebase_uid: str,
        document_type: str = "document",
        limit: int = 100,
        offset: int = 0
    ) -> List[int]:
        """
        Get list of document IDs owned by a user.
        
        Args:
            firebase_uid: Firebase UID of the user
            document_type: Type of documents ("document" or "bookmark")
            limit: Maximum number of IDs to return
            offset: Number of IDs to skip
        
        Returns:
            List of document IDs owned by the user
        """
        try:
            # Get user ID
            user = await UserService.get_user_by_firebase_uid(self.session, firebase_uid)
            if not user:
                return []
            
            # Build query
            if document_type.lower() == "bookmark":
                query = select(Bookmark.id).where(Bookmark.user_id == user.id)
            else:
                query = select(Document.id).where(Document.user_id == user.id)
            
            query = query.limit(limit).offset(offset)
            
            result = await self.session.execute(query)
            document_ids = result.scalars().all()
            
            # Log the operation
            security_auditor.log_security_event(
                "document_ids_retrieved",
                firebase_uid,
                {
                    "document_type": document_type,
                    "limit": limit,
                    "offset": offset,
                    "count": len(document_ids),
                    "user_id": user.id
                },
                SecurityLevel.LOW
            )
            
            return document_ids
            
        except Exception as e:
            logger.error(f"Error getting document IDs: {e}")
            return []


class DocumentAccessController:
    """
    Controller for enforcing document access control in API endpoints.
    """
    
    def __init__(self, session: AsyncSession):
        self.session = session
        self.verifier = DocumentOwnershipVerifier(session)
    
    async def require_document_ownership(
        self,
        document_id: int,
        firebase_uid: str,
        document_type: str = "document"
    ) -> None:
        """
        Require document ownership, raise HTTPException if not owned.
        
        Args:
            document_id: ID of the document
            firebase_uid: Firebase UID of the user
            document_type: Type of document ("document" or "bookmark")
        
        Raises:
            HTTPException: 404 if document not found, 403 if not owned
        """
        is_owned = await self.verifier.verify_document_ownership(
            document_id, firebase_uid, document_type
        )
        
        if not is_owned:
            # Check if document exists at all
            if document_type.lower() == "bookmark":
                result = await self.session.execute(
                    select(Bookmark).where(Bookmark.id == document_id)
                )
                document_exists = result.scalar_one_or_none() is not None
            else:
                result = await self.session.execute(
                    select(Document).where(Document.id == document_id)
                )
                document_exists = result.scalar_one_or_none() is not None
            
            if not document_exists:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"{document_type.capitalize()} not found"
                )
            else:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Access denied: {document_type.capitalize()} not owned by user"
                )
    
    async def require_multiple_documents_ownership(
        self,
        document_ids: List[int],
        firebase_uid: str,
        document_type: str = "document"
    ) -> List[int]:
        """
        Require ownership of multiple documents, return list of owned document IDs.
        
        Args:
            document_ids: List of document IDs
            firebase_uid: Firebase UID of the user
            document_type: Type of documents ("document" or "bookmark")
        
        Returns:
            List of document IDs that are owned by the user
        
        Raises:
            HTTPException: 403 if no documents are owned
        """
        ownership_map = await self.verifier.verify_multiple_documents_ownership(
            document_ids, firebase_uid, document_type
        )
        
        owned_ids = [doc_id for doc_id, is_owned in ownership_map.items() if is_owned]
        
        if not owned_ids:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied: No {document_type}s owned by user"
            )
        
        return owned_ids
    
    async def get_user_documents_with_ownership_check(
        self,
        firebase_uid: str,
        document_type: str = "document",
        limit: int = 50,
        offset: int = 0,
        status_filter: Optional[str] = None
    ) -> List[Union[Document, Bookmark]]:
        """
        Get user documents with ownership verification.
        
        Args:
            firebase_uid: Firebase UID of the user
            document_type: Type of documents ("document" or "bookmark")
            limit: Maximum number of documents to return
            offset: Number of documents to skip
            status_filter: Optional status filter
        
        Returns:
            List of documents owned by the user
        """
        try:
            # Get user ID
            user = await UserService.get_user_by_firebase_uid(self.session, firebase_uid)
            if not user:
                return []
            
            # Build query
            if document_type.lower() == "bookmark":
                query = select(Bookmark).where(Bookmark.user_id == user.id)
                if status_filter:
                    query = query.where(Bookmark.processing_status == status_filter)
            else:
                query = select(Document).where(Document.user_id == user.id)
                if status_filter:
                    query = query.where(Document.status == status_filter)
            
            query = query.limit(limit).offset(offset)
            
            result = await self.session.execute(query)
            documents = result.scalars().all()
            
            # Log the operation
            security_auditor.log_security_event(
                "user_documents_retrieved",
                firebase_uid,
                {
                    "document_type": document_type,
                    "limit": limit,
                    "offset": offset,
                    "status_filter": status_filter,
                    "count": len(documents),
                    "user_id": user.id
                },
                SecurityLevel.LOW
            )
            
            return documents
            
        except Exception as e:
            logger.error(f"Error getting user documents: {e}")
            return []


# Utility functions for easy access
async def verify_document_ownership(
    session: AsyncSession,
    document_id: int,
    firebase_uid: str,
    document_type: str = "document"
) -> bool:
    """Convenience function to verify document ownership"""
    verifier = DocumentOwnershipVerifier(session)
    return await verifier.verify_document_ownership(document_id, firebase_uid, document_type)


async def require_document_ownership(
    session: AsyncSession,
    document_id: int,
    firebase_uid: str,
    document_type: str = "document"
) -> None:
    """Convenience function to require document ownership"""
    controller = DocumentAccessController(session)
    await controller.require_document_ownership(document_id, firebase_uid, document_type)


async def get_user_document_count(
    session: AsyncSession,
    firebase_uid: str,
    document_type: str = "document",
    status_filter: Optional[str] = None
) -> int:
    """Convenience function to get user document count"""
    verifier = DocumentOwnershipVerifier(session)
    return await verifier.get_user_document_count(firebase_uid, document_type, status_filter)
