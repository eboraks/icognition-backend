"""
Document service for managing web page documents
"""

from typing import Optional, List, Dict, Any, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from sqlalchemy.orm import selectinload
import logging
import html
from datetime import datetime, timezone

from app.models import Document, User, ContentExtraction, PageType, Entity, EntityDocument
from app.services.base_service import UserIsolatedService
from app.services.web_fetcher import WebPageFetcher, fetch_web_page
from app.services.html_content_service import HtmlContentService
from app.services.user_service import UserService
from app.services.gemini_service import get_gemini_service, GeminiModel, GeminiConfig
from app.core.config import settings
from app.utils.logging import get_logger
from bs4 import BeautifulSoup
from app.services.content_validation_service import get_content_validation_service
from app.services.embedding_service import get_embedding_service, EmbeddingService
from app.utils.text_utils import extract_text_from_html


logger = get_logger(__name__)


class DocumentService(UserIsolatedService[Document]):
    """Service for managing user documents with data isolation"""

    def __init__(self, session: AsyncSession):
        super().__init__(Document)
        self.session = session

    async def create_document(
        self,
        user_id: str,
        url: Optional[str] = None,
        title: str = "Untitled",
        raw_html: Optional[str] = None,
        content_source: str = "url",
        **kwargs
    ) -> Document:
        """Create a new document for a user"""
        
        # Get or create user
        user = await UserService.get_or_create_user(self.session, user_id)
        
        # Create document
        document_data = {
            "user_id": user.id,
            "url": url,
            "title": title,
            "raw_html": raw_html or "",
            "content_source": content_source,
            **kwargs
        }
        
        document = Document(**document_data)
        try:
            self.session.add(document)
            await self.session.commit()
            await self.session.refresh(document)
            logger.info(f"Created document {document.id} for user {user.id}")
            return document
        except Exception as e:
            raise
        return document

    async def create_document_from_url(
        self,
        user_id: str,
        url: str,
        title: Optional[str] = None
    ) -> Document:
        """Create a new document by fetching content from URL"""
        
        # Get or create user
        user = await UserService.get_or_create_user(self.session, user_id)
        
        # Create document for URL fetching
        document_data = {
            "user_id": user.id,
            "url": url,
            "title": title or "Fetching...",
            "raw_html": "",
            "content_source": "url"
        }
        
        document = Document(**document_data)
        self.session.add(document)
        await self.session.commit()
        await self.session.refresh(document)
        
        try:
            # Fetch web page content
            success, html_content, fetch_metadata = await fetch_web_page(url)
            
            if success and html_content:
                # Use HtmlContentService to parse content
                html_service = HtmlContentService()
                
                # Extract all content and metadata
                extraction_result = await html_service.extract_content(html_content, url)
                
                # Update document with fetched content
                document.raw_html = html_content
                
                # Update title if not provided or if extracted title is better
                if extraction_result.title and (
                    not title 
                    or document.title == "Fetching..."
                    or len(extraction_result.title) > len(document.title)
                ):
                    document.title = extraction_result.title
                
                # Store main content
                if extraction_result.content:
                    document.content = extraction_result.content
                
                # Store author
                if extraction_result.author:
                    document.author = extraction_result.author
                
                # Store description from metadata
                if extraction_result.metadata.get('description'):
                    document.description = extraction_result.metadata['description']
                
                # Store published date
                if extraction_result.publication_date:
                     try:
                        # Try to parse Iso format first if it looks like one, or just store as string if model allows
                        # The model definition says publication_date is DateTime, so we need to parse it.
                        # The extractor returns a string. We should try to parse commonly used formats.
                        # For now, let's try basic ISO parsing if it matches
                        if 'T' in extraction_result.publication_date:
                            document.publication_date = datetime.fromisoformat(
                                extraction_result.publication_date.replace('Z', '+00:00')
                            )
                            # Convert to UTC and remove timezone info for PostgreSQL TIMESTAMP WITHOUT TIME ZONE
                            document.publication_date = document.publication_date.astimezone(timezone.utc).replace(tzinfo=None)
                     except (ValueError, TypeError):
                        logger.warning(f"Could not parse publication date: {extraction_result.publication_date}")

                # Store image URL
                if extraction_result.image_url:
                    document.image_url = extraction_result.image_url

                # Store extracted metadata
                document.document_metadata = {
                    'fetch_metadata': fetch_metadata,
                    'extracted_metadata': extraction_result.metadata,
                    'content_extraction': extraction_result.model_dump()
                }
                
                # Copy tags
                if extraction_result.tags:
                    document.keywords = extraction_result.tags
                
                # Store page detection info if available
                if fetch_metadata.get('page_detection'):
                     # (Keep existing page detection logic from fetch_metadata)
                     page_detection = fetch_metadata['page_detection']
                     # ... (merging with existing logic for page_detection handling)
                     if page_detection.get('content_availability'):
                        content_availability = page_detection['content_availability']
                        document.document_metadata['content_availability'] = {
                            'status': content_availability.get('status', 'unknown'),
                            'content_available': content_availability.get('status') in ['full', 'partial'],
                            'content_status': content_availability.get('status'),
                            'issues': content_availability.get('issues', []),
                            'paywall_detected': content_availability.get('paywall_detected', False),
                            'authentication_required': content_availability.get('authentication_required', False),
                            'content_blocked': content_availability.get('content_blocked', False),
                        }
                
                logger.info(f"Successfully fetched and parsed content for document {document.id}")
                
                # Validate extracted content
                await self._validate_document_content(document)
                
            else:
                # Document fetch failed
                document.document_metadata = {
                    'fetch_error': fetch_metadata.get('error', 'Unknown error'),
                    'fetch_metadata': fetch_metadata,
                    'content_availability': {
                        'status': 'unavailable',
                        'content_available': False,
                        'content_status': 'unavailable',
                        'issues': ['fetch_failed']
                    }
                }
                logger.error(f"Failed to fetch content for document {document.id}: {fetch_metadata}")
            
            await self.session.commit()
            await self.session.refresh(document)
            
        except Exception as e:
            # Handle unexpected errors
            document.document_metadata = {
                'fetch_error': f'Unexpected error: {str(e)}',
                'content_availability': {
                    'status': 'unavailable',
                    'content_available': False,
                    'content_status': 'unavailable',
                    'issues': ['fetch_error']
                }
            }
            await self.session.commit()
            await self.session.refresh(document)
            logger.error(f"Unexpected error fetching content for document {document.id}: {str(e)}")
        
        return document

    async def create_document_from_content(
        self,
        user_id: str,
        content: str,
        content_type: str,
        title: Optional[str] = None,
        url: Optional[str] = None
    ) -> Document:
        """Create a new document from direct content (HTML or text)"""
        
        # Get or create user
        user = await UserService.get_or_create_user(self.session, user_id)
        
        # Process content based on type
        if content_type == "html":
            # Use HtmlContentService for consistent parsing
            html_service = HtmlContentService()
            extraction_result = await html_service.extract_content(content, url or "")
            
            # Use provided title or extracted title
            final_title = title or "Untitled Document"
            if extraction_result.title and (not title or len(extraction_result.title) > len(title)):
                final_title = extraction_result.title
            
            document_data = {
                "user_id": user.id,
                "url": url,
                "title": final_title,
                "raw_html": content,
                "content": extraction_result.content,
                "content_source": "html",
                "extracted_content": extraction_result.model_dump(),
                "author": extraction_result.author,
                "image_url": extraction_result.image_url,
            }
            
            # Additional metadata
            if extraction_result.metadata.get('description'):
                document_data['description'] = extraction_result.metadata['description']
                
            if extraction_result.publication_date:
                try:
                    if 'T' in extraction_result.publication_date:
                        document_data['publication_date'] = datetime.fromisoformat(
                            extraction_result.publication_date.replace('Z', '+00:00')
                        )
                        # Convert to UTC and remove timezone info
                        document_data['publication_date'] = document_data['publication_date'].astimezone(timezone.utc).replace(tzinfo=None)
                except (ValueError, TypeError):
                    pass
            
            if extraction_result.tags:
                document_data['keywords'] = extraction_result.tags
            
        elif content_type == "text":
            # Wrap text content in basic HTML structure
            wrapped_html = f"<html><body><p>{content}</p></body></html>"
            
            # Use provided title or default
            final_title = title or "Untitled Document"
            
            document_data = {
                "user_id": user.id,
                "url": url,
                "title": final_title,
                "raw_html": wrapped_html,
                "content": content,
                "content_source": "text",
            }
        
        else:
            raise ValueError(f"Unsupported content_type: {content_type}")
        
        # Create document
        document = Document(**document_data)
        self.session.add(document)
        await self.session.commit()
        await self.session.refresh(document)
        
        logger.info(f"Created document {document.id} from {content_type} content for user {user.id}")
        
        return document



    async def fetch_and_update_document(
        self,
        user_id: str,
        document_id: str  # Changed from int to str for UUID
    ) -> Optional[Document]:
        """Fetch content for an existing document"""
        
        document = await self.get_document_by_id(user_id, document_id)
        if not document:
            return None
        
        # Document fetching
        await self.session.commit()
        
        try:
            # Fetch web page content
            success, html_content, fetch_metadata = await fetch_web_page(document.url)
            
            if success and html_content:
                # Use HtmlContentService to parse content
                html_service = HtmlContentService()
                
                # Extract all content and metadata
                extraction_result = await html_service.extract_content(html_content, document.url)
                
                # Update document with fetched content
                document.raw_html = html_content
                
                # Update title if extracted title is better
                if extraction_result.title and len(extraction_result.title) > len(document.title):
                    document.title = extraction_result.title
                
                # Store main content
                if extraction_result.content:
                    document.content = extraction_result.content
                
                # Store author
                if extraction_result.author:
                    document.author = extraction_result.author
                
                # Store description
                if extraction_result.metadata.get('description'):
                    document.description = extraction_result.metadata['description']
                
                # Store extracted metadata
                if document.document_metadata is None:
                    document.document_metadata = {}
                document.document_metadata.update({
                    'fetch_metadata': fetch_metadata,
                    'extracted_metadata': extraction_result.metadata,
                    'content_extraction': extraction_result.model_dump()
                })
                
                # Copy tags
                if extraction_result.tags:
                    document.keywords = extraction_result.tags
                
                # Store publication date
                if extraction_result.publication_date:
                     try:
                        if 'T' in extraction_result.publication_date:
                            document.publication_date = datetime.fromisoformat(
                                extraction_result.publication_date.replace('Z', '+00:00')
                            )
                            # Convert to UTC and remove timezone info for PostgreSQL TIMESTAMP WITHOUT TIME ZONE
                            document.publication_date = document.publication_date.astimezone(timezone.utc).replace(tzinfo=None)
                     except (ValueError, TypeError):
                        logger.warning(f"Could not parse publication date: {extraction_result.publication_date}")
                
                # Store image URL
                if extraction_result.image_url:
                    document.image_url = extraction_result.image_url
                
                # Store page detection info if available
                if fetch_metadata.get('page_detection'):
                    page_detection = fetch_metadata['page_detection']
                    document.document_metadata['page_detection'] = page_detection
                    
                    # Store content availability status
                    if page_detection.get('content_availability'):
                        content_availability = page_detection['content_availability']
                        document.document_metadata['content_availability'] = {
                            'status': content_availability.get('status', 'unknown'),
                            'content_available': content_availability.get('status') in ['full', 'partial'],
                            'content_status': content_availability.get('status'),  # 'full', 'partial', or 'unavailable'
                            'issues': content_availability.get('issues', []),
                            'paywall_detected': content_availability.get('paywall_detected', False),
                            'authentication_required': content_availability.get('authentication_required', False),
                            'content_blocked': content_availability.get('content_blocked', False),
                        }
                        logger.info(f"Document {document.id} content availability: {content_availability.get('status')} (issues: {content_availability.get('issues')})")
                    
                    # Log warnings if any
                    if page_detection.get('warnings'):
                        for warning in page_detection['warnings']:
                            logger.warning(f"Page detection warning for document {document.id}: {warning}")
                    
                    # If page requires JS and we detected placeholder content, mark it
                    if page_detection.get('issues'):
                        logger.info(f"Document {document.id} has detected issues: {', '.join(page_detection['issues'])}")
                

                
                logger.info(f"Successfully fetched content for document {document.id}")
                
                # Validate extracted content
                await self._validate_document_content(document)
                
            else:
                # Fetch failed
                # Document fetch failed
                if document.document_metadata is None:
                    document.document_metadata = {}
                document.document_metadata.update({
                    'fetch_error': fetch_metadata.get('error', 'Unknown error'),
                    'fetch_metadata': fetch_metadata,
                    'content_availability': {
                        'status': 'unavailable',
                        'content_available': False,
                        'content_status': 'unavailable',
                        'issues': ['fetch_failed'],
                        'paywall_detected': False,
                        'authentication_required': False,
                        'content_blocked': False,
                    }
                })
                logger.error(f"Failed to fetch content for document {document.id}: {fetch_metadata}")
            
            await self.session.commit()
            await self.session.refresh(document)
            
        except Exception as e:
            # Handle unexpected errors
            # Document fetch error
            if document.document_metadata is None:
                document.document_metadata = {}
            document.document_metadata.update({
                'fetch_error': f'Unexpected error: {str(e)}',
                'content_availability': {
                    'status': 'unavailable',
                    'content_available': False,
                    'content_status': 'unavailable',
                    'issues': ['fetch_error'],
                    'paywall_detected': False,
                    'authentication_required': False,
                    'content_blocked': False,
                }
            })
            await self.session.commit()
            await self.session.refresh(document)
            logger.error(f"Unexpected error fetching content for document {document.id}: {str(e)}")
        
        return document
    
    async def reprocess_document_content(
        self,
        user_id: str,
        document_id: int,
        refetch_from_source: bool = False
    ) -> Optional[Document]:
        """
        Re-run content extraction and embeddings for an existing document.
        """
        document = await self.get_document_by_id(user_id, document_id)
        if not document:
            return None
        
        # Optionally re-fetch the document from its source if requested or if no raw_html exists
        if refetch_from_source or not document.raw_html:
            if document.url:
                updated_document = await self.fetch_and_update_document(
                    user_id=user_id,
                    document_id=str(document_id)
                )
                if updated_document:
                    document = updated_document
            else:
                logger.warning(
                    f"Document {document_id} has no raw_html or URL to refetch from"
                )
        
        if not document.raw_html:
            logger.warning(f"Document {document_id} still lacks raw_html after reprocess attempt")
            return document
        
        fetcher = WebPageFetcher()
        extraction = fetcher.extract_main_content(document.raw_html)
        
        document.content = extraction.get('content', '')
        document.document_metadata = document.document_metadata or {}
        document.document_metadata['content_extraction'] = extraction
        document.updated_at = datetime.utcnow()
        
        await self._validate_document_content(document)
        
        embedding_service: EmbeddingService = get_embedding_service()
        embedding_success = await embedding_service.generate_and_store_document_embeddings(
            session=self.session,
            document=document,
            user_id=user_id,
            force_regenerate=True
        )
        
        if not embedding_success:
            logger.warning(f"Failed to regenerate embeddings for document {document_id}")
        
        await self.session.commit()
        await self.session.refresh(document)
        return document

    async def get_user_documents(
        self,
        user_id: str,
        page: int = 1,
        page_size: int = 20
    ) -> Tuple[List[Document], int]:
        """Get paginated list of user documents"""
        
        # Build query
        query = select(Document)
        count_query = select(func.count(Document.id))
        
        if not settings.DISABLE_AUTH:
            user = await UserService.get_user_by_firebase_uid(self.session, user_id)
            if not user:
                return [], 0
            query = query.where(Document.user_id == user.id)
            count_query = count_query.where(Document.user_id == user.id)
        
        # Status filtering removed (status field no longer exists)
        
        # Get total count
        try:
            total_result = await self.session.execute(count_query)
            total = total_result.scalar()
            
            # Apply pagination
            offset = (page - 1) * page_size
            query = query.offset(offset).limit(page_size).order_by(Document.created_at.desc())
            
            result = await self.session.execute(query)
            documents = result.scalars().all()
            
            return documents, total
        except Exception as e:
            if settings.DISABLE_AUTH:
                logger.warning(f"Database error in get_user_documents (No-Auth mode): {e}")
                return [], 0
            raise

    async def get_document_by_id(
        self,
        user_id: str,
        document_id: int  # Document ID is now int
    ) -> Optional[Document]:
        """Get a specific document by ID for a user"""
        
        query = select(Document).where(Document.id == document_id)
        
        if not settings.DISABLE_AUTH:
            query = query.where(Document.user_id == user_id)
        
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def update_document(
        self,
        user_id: str,
        document_id: int,  # Document ID is now int
        **update_data
    ) -> Optional[Document]:
        """Update document metadata"""
        
        document = await self.get_document_by_id(user_id, document_id)
        if not document:
            return None
        
        # Update fields
        for field, value in update_data.items():
            if hasattr(document, field) and value is not None:
                setattr(document, field, value)
        
        await self.session.commit()
        await self.session.refresh(document)
        
        logger.info(f"Updated document {document_id} for user")
        return document

    async def delete_document(
        self,
        user_id: str,
        document_id: str  # Changed from int to str for UUID
    ) -> bool:
        """Delete a document"""
        
        document = await self.get_document_by_id(user_id, document_id)
        if not document:
            return False
        
        await self.session.delete(document)
        await self.session.commit()
        
        logger.info(f"Deleted document {document_id} for user")
        return True

    async def get_documents_by_url(
        self,
        user_id: str,
        url: str
    ) -> List[Document]:
        """Get all documents for a specific URL"""
        
        user = await UserService.get_user_by_firebase_uid(self.session, user_id)
        if not user:
            return []
        
        query = select(Document).where(
            and_(Document.user_id == user.id, Document.url == url)
        ).order_by(Document.created_at.desc())
        
        result = await self.session.execute(query)
        return result.scalars().all()

    async def update_document_metadata(
        self,
        user_id: str,
        document_id: str,  # Changed from int to str for UUID
        **metadata_updates
    ) -> Optional[Document]:
        """Update document metadata"""
        
        document = await self.get_document_by_id(user_id, document_id)
        if not document:
            return None
        
        # Update metadata if provided
        if metadata_updates:
            if document.document_metadata is None:
                document.document_metadata = {}
            document.document_metadata.update(metadata_updates)
        
        await self.session.commit()
        await self.session.refresh(document)
        
        logger.info(f"Updated document {document_id} metadata")
        return document

    async def get_user_documents_all(
        self,
        user_id: str
    ) -> List[Document]:
        """Get all documents for a user"""
        
        query = select(Document)
        if not settings.DISABLE_AUTH:
            user = await UserService.get_user_by_firebase_uid(self.session, user_id)
            if not user:
                return []
            query = query.where(Document.user_id == user.id)
            
        query = query.order_by(Document.created_at.desc())
        
        try:
            result = await self.session.execute(query)
            return list(result.scalars().all())
        except Exception as e:
            if settings.DISABLE_AUTH:
                logger.warning(f"Database error in get_user_documents_all (No-Auth mode): {e}")
                return []
            raise

    async def get_latest_documents(
        self,
        user_id: str,
        limit: int = 2
    ) -> List[Document]:
        """
        Get the N latest documents, ordered by created_at descending.
        """
        query = select(Document)
        if not settings.DISABLE_AUTH:
            user = await UserService.get_user_by_firebase_uid(self.session, user_id)
            if not user:
                return []
            query = query.where(Document.user_id == user.id)
            
        query = query.order_by(Document.created_at.desc()).limit(limit)
        
        try:
            result = await self.session.execute(query)
            return list(result.scalars().all())
        except Exception as e:
            if settings.DISABLE_AUTH:
                logger.warning(f"Database error in get_latest_documents (No-Auth mode): {e}")
                return []
            raise

    async def count_user_documents(
        self,
        user_id: str
    ) -> int:
        """Count user documents"""
        
        query = select(func.count(Document.id))
        
        if not settings.DISABLE_AUTH:
            user = await UserService.get_user_by_firebase_uid(self.session, user_id)
            if not user:
                return 0
            query = query.where(Document.user_id == user.id)
        
        try:
            result = await self.session.execute(query)
            return result.scalar() or 0
        except Exception as e:
            if settings.DISABLE_AUTH:
                logger.warning(f"Database error in count_user_documents (No-Auth mode): {e}")
                return 0
            raise
    
    async def _validate_document_content(self, document: Document) -> None:
        """Validate document content"""
        try:
            if not document.content:
                logger.warning(f"Document {document.id} has no content to validate")
                return
            
            validation_service = get_content_validation_service()
            
            content_for_validation = extract_text_from_html(document.content)
            if not content_for_validation:
                logger.warning(f"Document {document.id} content is empty after HTML sanitization")
                return
            
            validation_report = await validation_service.validate_content(
                content=content_for_validation,
                title=document.title,
                url=document.url,
                metadata=document.document_metadata
            )
            
            # Update document metadata with validation results
            if document.document_metadata is None:
                document.document_metadata = {}
            
            document.document_metadata['content_validation'] = {
                'is_valid': validation_report.is_valid,
                'overall_score': validation_report.overall_score,
                'validation_level': validation_report.validation_level.value,
                'issues_count': len(validation_report.issues),
                'warnings_count': len(validation_report.warnings),
                'passed_rules': validation_report.passed_rules,
                'failed_rules': validation_report.failed_rules,
                'content_metrics': validation_report.content_metrics,
                'validation_timestamp': validation_report.validation_timestamp.isoformat(),
                'processing_time': validation_report.processing_time
            }
            
            # Document validation completed
            if validation_report.is_valid:
                logger.info(f"Document {document.id} content validation passed (score: {validation_report.overall_score:.2f})")
            else:
                logger.warning(f"Document {document.id} content validation failed (score: {validation_report.overall_score:.2f})")
                
                # Add validation issues to metadata
                document.document_metadata['content_validation']['issues'] = [
                    {
                        'rule_name': issue.rule_name,
                        'severity': issue.severity.value,
                        'message': issue.message,
                        'actual_value': issue.actual_value,
                        'expected_value': issue.expected_value,
                        'suggestion': issue.suggestion
                    }
                    for issue in validation_report.issues
                ]
                
                document.document_metadata['content_validation']['warnings'] = [
                    {
                        'rule_name': warning.rule_name,
                        'severity': warning.severity.value,
                        'message': warning.message,
                        'actual_value': warning.actual_value,
                        'expected_value': warning.expected_value,
                        'suggestion': warning.suggestion
                    }
                    for warning in validation_report.warnings
                ]
            
        except Exception as e:
            logger.error(f"Error validating content for document {document.id}: {str(e)}")
            # Don't fail the entire process if validation fails
            if document.document_metadata is None:
                document.document_metadata = {}
            document.document_metadata['content_validation'] = {
                'error': str(e),
                'validation_timestamp': datetime.now().isoformat()
            }

    async def get_relevant_documents_for_chat(
        self, user_id: str, query: str, scope_type: str, scope_id: Optional[int] = None, limit: int = 5, similarity_threshold: float = 0.6
    ) -> List[Document]:
        """
        Get relevant documents for a chat query using vector search on the Embedding table.
        """
        logger.info(f"Getting relevant documents for user {user_id} with query '{query}'")

        embedding_service: EmbeddingService = get_embedding_service()
        
        # 1. Search the Embedding table for relevant content
        # Use a lower threshold to get more results, then we'll deduplicate by document
        embedding_results = await embedding_service.search_embeddings(
            session=self.session,
            query_text=query,
            user_id=user_id,
            source_types=['document'],  # Only search documents for chat
            limit=limit * 5,  # Get more results to account for multiple chunks per document
            similarity_threshold=similarity_threshold  # Use the provided threshold
        )
        
        if not embedding_results:
            logger.info(f"No matching embeddings found for query '{query}'")
            return []
        
        # 2. Group results by document_id and get the best match per document
        document_scores = {}  # document_id -> best similarity score
        for result in embedding_results:
            doc_id = result['source_id']
            score = result['similarity_score']
            if doc_id not in document_scores or score > document_scores[doc_id]:
                document_scores[doc_id] = score
        
        # 3. Sort documents by similarity score and get top results
        sorted_doc_ids = sorted(document_scores.items(), key=lambda x: x[1], reverse=True)[:limit]
        doc_ids = [doc_id for doc_id, _ in sorted_doc_ids]
        
        if not doc_ids:
            return []
        
        # 4. Fetch the actual Document objects
        stmt = select(Document).where(
            Document.id.in_(doc_ids),
            Document.user_id == user_id
        )
        
        # If scope_type is 'collection', further filter by scope_id
        # TODO: Implement collection filtering when CollectionDocumentLink is available
        if scope_type == 'collection' and scope_id is not None:
            logger.warning("Collection-scoped search is not yet fully implemented.")
        
        results = await self.session.execute(stmt)
        documents = list(results.scalars().all())
        
        # Sort documents by the similarity scores we calculated
        doc_score_map = dict(sorted_doc_ids)
        documents.sort(key=lambda doc: doc_score_map.get(doc.id, 0), reverse=True)
        
        logger.info(f"Found {len(documents)} relevant documents for query '{query}'")
        return documents

    async def get_relevant_documents_with_chunks_for_chat(
        self, 
        user_id: str, 
        query: str, 
        scope_type: str, 
        scope_id: Optional[int] = None, 
        limit: int = 5, 
        similarity_threshold: float = 0.55,
        chunks_per_document: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Get relevant documents for a chat query with their matching chunks.
        Returns documents along with the actual chunk text that matched the query.
        
        Args:
            user_id: User ID
            query: Search query
            scope_type: Scope type ('all_library', 'collection', etc.)
            scope_id: Optional scope ID (e.g., collection ID)
            limit: Maximum number of documents to return
            similarity_threshold: Minimum similarity score (default 0.55 for broader matching)
            chunks_per_document: Maximum number of top chunks to include per document (default 5)
            
        Returns:
            List of dictionaries with structure:
            {
                'document': Document,
                'chunks': [
                    {'text': str, 'similarity_score': float, 'field': str},
                    ...
                ],
                'best_score': float
            }
        """
        logger.info(f"Getting relevant documents with chunks for user {user_id} with query '{query}'")

        embedding_service: EmbeddingService = get_embedding_service()
        
        # 1. Search the Embedding table for relevant content
        # Get more results to account for multiple chunks per document
        embedding_results = await embedding_service.search_embeddings(
            session=self.session,
            query_text=query,
            user_id=user_id,
            source_types=['document'],  # Only search documents for chat
            limit=limit * 10,  # Get more results to have enough chunks per document
            similarity_threshold=similarity_threshold
        )
        
        if not embedding_results:
            logger.info(f"No matching embeddings found for query '{query}'")
            return []
        
        # 2. Group results by document_id and collect chunks
        document_chunks = {}  # document_id -> list of chunks with scores
        document_scores = {}  # document_id -> best similarity score
        
        for result in embedding_results:
            doc_id = result['source_id']
            score = result['similarity_score']
            chunk_data = {
                'text': result['text'],
                'similarity_score': score,
                'field': result.get('field', 'content')
            }
            
            if doc_id not in document_chunks:
                document_chunks[doc_id] = []
                document_scores[doc_id] = score
            
            document_chunks[doc_id].append(chunk_data)
            
            # Update best score if this chunk has a higher score
            if score > document_scores[doc_id]:
                document_scores[doc_id] = score
        
        # 3. Sort chunks within each document by similarity score (descending)
        for doc_id in document_chunks:
            document_chunks[doc_id].sort(key=lambda x: x['similarity_score'], reverse=True)
            # Take only top N chunks per document
            document_chunks[doc_id] = document_chunks[doc_id][:chunks_per_document]
        
        # 4. Sort documents by best similarity score and get top results
        sorted_doc_ids = sorted(document_scores.items(), key=lambda x: x[1], reverse=True)[:limit]
        doc_ids = [doc_id for doc_id, _ in sorted_doc_ids]
        
        if not doc_ids:
            return []
        
        # 5. Fetch the actual Document objects
        stmt = select(Document).where(Document.id.in_(doc_ids))
        if not settings.DISABLE_AUTH:
            stmt = stmt.where(Document.user_id == user_id)
        
        # If scope_type is 'collection', further filter by scope_id
        # TODO: Implement collection filtering when CollectionDocumentLink is available
        if scope_type == 'collection' and scope_id is not None:
            logger.warning("Collection-scoped search is not yet fully implemented.")
        
        results = await self.session.execute(stmt)
        documents = list(results.scalars().all())
        
        # 6. Build result list with documents and their chunks
        doc_map = {doc.id: doc for doc in documents}
        result_list = []
        
        for doc_id, best_score in sorted_doc_ids:
            if doc_id in doc_map:
                result_list.append({
                    'document': doc_map[doc_id],
                    'chunks': document_chunks.get(doc_id, []),
                    'best_score': best_score
                })
        
        logger.info(f"Found {len(result_list)} relevant documents with chunks for query '{query}'")
        return result_list

    async def get_entity_tree(self, user_id: str) -> List[Dict[str, Any]]:
        """
        Build entity tree structure for filtering, grouped by entity type.
        Returns tree in PrimeVue Tree format.
        
        Args:
            user_id: Firebase user ID
            
        Returns:
            List of tree nodes with structure:
            [
                {
                    "key": "location",
                    "label": "Location",
                    "children": [
                        {
                            "key": "entity-location-1",
                            "label": "London",
                            "data": {"entity_id": 1, "document_ids": [1, 2, 3]}
                        }
                    ]
                }
            ]
        """
        # Entity type display name normalization
        ENTITY_TYPE_DISPLAY = {
            'person': 'People',
            'location': 'Location',
            'organization': 'Organization',
            'topic': 'Topic',
            'product': 'Product',
            'company': 'Company',
            'event': 'Event',
            'technology': 'Technology',
            'institution': 'Institution',
        }
        
        # Get user by Firebase UID
        user = await UserService.get_user_by_firebase_uid(self.session, user_id)
        if not user:
            return []
        
        # Query entities with their document relationships
        # Get all entity-document mappings first
        query = (
            select(
                Entity.id,
                Entity.name,
                Entity.type,
                EntityDocument.document_id
            )
            .join(EntityDocument, Entity.id == EntityDocument.entity_id)
            .join(Document, EntityDocument.document_id == Document.id)  # Join with Document to check ownership
        )
        
        if not settings.DISABLE_AUTH:
            # No need to get User object again, we have the ID from existing context check or param
            # But to be safe and consistent with existing code:
            user = await UserService.get_user_by_firebase_uid(self.session, user_id)
            if not user:
                return []
                
            # Filter by documents owned by the user
            query = query.where(Document.user_id == user.id)
            
        query = query.order_by(Entity.type, Entity.name, Entity.id)
        
        result = await self.session.execute(query)
        entity_doc_mappings = result.all()
        
        # Group document_ids by entity
        entity_data_map: Dict[int, Dict[str, Any]] = {}
        for entity_id, entity_name, entity_type, document_id in entity_doc_mappings:
            if entity_id not in entity_data_map:
                entity_data_map[entity_id] = {
                    'id': entity_id,
                    'name': entity_name,
                    'type': entity_type,
                    'document_ids': []
                }
            if document_id:
                entity_data_map[entity_id]['document_ids'].append(document_id)
        
        # Group entities by type
        entities_by_type: Dict[str, List[Dict[str, Any]]] = {}
        for entity_data in entity_data_map.values():
            entity_type_lower = entity_data['type'].lower() if entity_data['type'] else 'other'
            if entity_type_lower not in entities_by_type:
                entities_by_type[entity_type_lower] = []
            
            entities_by_type[entity_type_lower].append({
                'id': entity_data['id'],
                'name': entity_data['name'],
                'document_ids': entity_data['document_ids']
            })
        
        # Build tree structure
        tree = []
        for entity_type_key, entities in entities_by_type.items():
            # Get normalized display name
            display_name = ENTITY_TYPE_DISPLAY.get(entity_type_key, entity_type_key.title())
            
            # Build children nodes (entities)
            children = []
            for entity in entities:
                entity_key = f"entity-{entity_type_key}-{entity['id']}"
                children.append({
                    'key': entity_key,
                    'label': entity['name'],
                    'data': {
                        'entity_id': entity['id'],
                        'document_ids': entity['document_ids']
                    }
                })
            
            # Only add type node if it has children
            if children:
                tree.append({
                    'key': entity_type_key,
                    'label': display_name,
                    'children': children
                })
        
        return tree
