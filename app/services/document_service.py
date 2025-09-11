"""
Document service for managing web page documents
"""

from typing import Optional, List, Dict, Any, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from sqlalchemy.orm import selectinload
import logging

from app.db.models import Document, User
from app.services.base_service import UserIsolatedService
from app.services.web_fetcher import WebPageFetcher, fetch_web_page
from app.services.user_service import UserService
from app.utils.logging import get_logger

logger = get_logger(__name__)


class DocumentService(UserIsolatedService[Document]):
    """Service for managing user documents with data isolation"""

    def __init__(self, session: AsyncSession):
        super().__init__(Document)
        self.session = session

    async def create_document(
        self,
        firebase_uid: str,
        url: Optional[str] = None,
        title: str = "Untitled",
        raw_html: Optional[str] = None,
        content_source: str = "url",
        **kwargs
    ) -> Document:
        """Create a new document for a user"""
        
        # Get or create user
        user = await UserService.get_or_create_user(self.session, firebase_uid)
        
        # Create document
        document_data = {
            "user_id": user.id,
            "url": url,
            "title": title,
            "raw_html": raw_html or "",
            "content_source": content_source,
            "status": "pending",
            **kwargs
        }
        
        document = Document(**document_data)
        self.session.add(document)
        await self.session.commit()
        await self.session.refresh(document)
        
        logger.info(f"Created document {document.id} for user {user.id}")
        return document

    async def create_document_from_url(
        self,
        firebase_uid: str,
        url: str,
        title: Optional[str] = None
    ) -> Document:
        """Create a new document by fetching content from URL"""
        
        # Get or create user
        user = await UserService.get_or_create_user(self.session, firebase_uid)
        
        # Update status to fetching
        document_data = {
            "user_id": user.id,
            "url": url,
            "title": title or "Fetching...",
            "raw_html": "",
            "content_source": "url",
            "status": "fetching"
        }
        
        document = Document(**document_data)
        self.session.add(document)
        await self.session.commit()
        await self.session.refresh(document)
        
        try:
            # Fetch web page content
            success, html_content, fetch_metadata = await fetch_web_page(url)
            
            if success and html_content:
                # Extract enhanced metadata and main content from HTML
                from app.services.web_fetcher import WebPageFetcher
                async with WebPageFetcher() as fetcher:
                    enhanced_metadata = fetcher.extract_enhanced_metadata(html_content)
                    content_extraction = fetcher.extract_main_content(html_content)
                
                # Update document with fetched content
                document.raw_html = html_content
                document.status = "fetched"
                
                # Update title if not provided or if extracted title is better
                if not title and enhanced_metadata.get('title'):
                    document.title = enhanced_metadata['title']
                
                # Store main content
                if content_extraction.get('content'):
                    document.content = content_extraction['content']
                
                # Store extracted metadata
                document.document_metadata = {
                    'fetch_metadata': fetch_metadata,
                    'extracted_metadata': enhanced_metadata,
                    'content_extraction': content_extraction
                }
                
                # Store extracted fields
                if enhanced_metadata.get('author'):
                    document.author = enhanced_metadata['author']
                if enhanced_metadata.get('description'):
                    document.description = enhanced_metadata['description']
                if enhanced_metadata.get('keywords'):
                    document.keywords = enhanced_metadata['keywords']
                if enhanced_metadata.get('publication_date'):
                    # Parse publication date if it's a string
                    try:
                        from datetime import datetime
                        if isinstance(enhanced_metadata['publication_date'], str):
                            # Try to parse ISO format first
                            document.publication_date = datetime.fromisoformat(
                                enhanced_metadata['publication_date'].replace('Z', '+00:00')
                            )
                    except (ValueError, TypeError):
                        logger.warning(f"Could not parse publication date: {enhanced_metadata['publication_date']}")
                
                logger.info(f"Successfully fetched content for document {document.id}")
                
                # Validate extracted content
                await self._validate_document_content(document)
                
            else:
                # Fetch failed
                document.status = "fetch_failed"
                document.document_metadata = {
                    'fetch_error': fetch_metadata.get('error', 'Unknown error'),
                    'fetch_metadata': fetch_metadata
                }
                logger.error(f"Failed to fetch content for document {document.id}: {fetch_metadata}")
            
            await self.session.commit()
            await self.session.refresh(document)
            
        except Exception as e:
            # Handle unexpected errors
            document.status = "fetch_error"
            document.document_metadata = {
                'fetch_error': f'Unexpected error: {str(e)}'
            }
            await self.session.commit()
            await self.session.refresh(document)
            logger.error(f"Unexpected error fetching content for document {document.id}: {str(e)}")
        
        return document

    async def create_document_from_content(
        self,
        firebase_uid: str,
        content: str,
        content_type: str,
        title: Optional[str] = None,
        url: Optional[str] = None
    ) -> Document:
        """Create a new document from direct content (HTML or text)"""
        
        # Get or create user
        user = await UserService.get_or_create_user(self.session, firebase_uid)
        
        # Process content based on type
        if content_type == "html":
            # Extract text and title from HTML
            extracted_text = self._extract_text_from_html(content)
            extracted_title = self._extract_title_from_html(content)
            
            # Use provided title or extracted title
            final_title = title or extracted_title or "Untitled Document"
            
            document_data = {
                "user_id": user.id,
                "url": url,
                "title": final_title,
                "raw_html": content,
                "content": extracted_text,
                "content_source": "html",
                "status": "processed"
            }
            
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
                "status": "processed"
            }
        
        else:
            raise ValueError(f"Unsupported content_type: {content_type}")
        
        # Create document
        document = Document(**document_data)
        self.session.add(document)
        await self.session.commit()
        await self.session.refresh(document)
        
        logger.info(f"Created document {document.id} from {content_type} content for user {user.id}")
        
        # Validate content
        await self._validate_document_content(document)
        await self.session.commit()
        await self.session.refresh(document)
        
        # Trigger embedding generation for direct content
        try:
            from app.services.embedding_service import get_embedding_service
            embedding_service = get_embedding_service()
            
            # Generate embedding for the document
            embedding_success = await embedding_service.update_document_embedding(
                session=self.session,
                document_id=document.id,
                user_id=user.id,
                force_regenerate=False
            )
            
            if embedding_success:
                logger.info(f"Successfully generated embedding for direct content document {document.id}")
            else:
                logger.warning(f"Failed to generate embedding for direct content document {document.id}")
                
        except Exception as e:
            logger.error(f"Error generating embedding for direct content document {document.id}: {str(e)}")
            # Don't fail the document creation if embedding generation fails
        
        return document

    def _extract_text_from_html(self, html_content: str) -> str:
        """Extract clean text from HTML content"""
        try:
            from bs4 import BeautifulSoup
            
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Remove script and style elements
            for script in soup(["script", "style"]):
                script.extract()
            
            # Get text
            text = soup.get_text()
            
            # Clean up whitespace
            lines = (line.strip() for line in text.splitlines())
            chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
            text = '\n'.join(chunk for chunk in chunks if chunk)
            
            return text
            
        except Exception as e:
            logger.error(f"Error extracting text from HTML: {str(e)}")
            # Fallback: return the HTML content as-is
            return html_content

    def _extract_title_from_html(self, html_content: str) -> str:
        """Extract title from HTML content"""
        try:
            from bs4 import BeautifulSoup
            
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Try to find title tag first
            title_tag = soup.find('title')
            if title_tag and title_tag.string:
                return title_tag.string.strip()
            
            # Fallback to h1 tag
            h1_tag = soup.find('h1')
            if h1_tag:
                return h1_tag.get_text().strip()
            
            # Fallback to h2 tag
            h2_tag = soup.find('h2')
            if h2_tag:
                return h2_tag.get_text().strip()
            
            return "Untitled Document"
            
        except Exception as e:
            logger.error(f"Error extracting title from HTML: {str(e)}")
            return "Untitled Document"

    async def fetch_and_update_document(
        self,
        firebase_uid: str,
        document_id: int
    ) -> Optional[Document]:
        """Fetch content for an existing document"""
        
        document = await self.get_document_by_id(firebase_uid, document_id)
        if not document:
            return None
        
        # Update status to fetching
        document.status = "fetching"
        await self.session.commit()
        
        try:
            # Fetch web page content
            success, html_content, fetch_metadata = await fetch_web_page(document.url)
            
            if success and html_content:
                # Extract enhanced metadata and main content from HTML
                from app.services.web_fetcher import WebPageFetcher
                async with WebPageFetcher() as fetcher:
                    enhanced_metadata = fetcher.extract_enhanced_metadata(html_content)
                    content_extraction = fetcher.extract_main_content(html_content)
                
                # Update document with fetched content
                document.raw_html = html_content
                document.status = "fetched"
                
                # Update title if extracted title is better
                if enhanced_metadata.get('title') and len(enhanced_metadata['title']) > len(document.title):
                    document.title = enhanced_metadata['title']
                
                # Store main content
                if content_extraction.get('content'):
                    document.content = content_extraction['content']
                
                # Store extracted metadata
                if document.document_metadata is None:
                    document.document_metadata = {}
                document.document_metadata.update({
                    'fetch_metadata': fetch_metadata,
                    'extracted_metadata': enhanced_metadata,
                    'content_extraction': content_extraction
                })
                
                # Store extracted fields
                if enhanced_metadata.get('author'):
                    document.author = enhanced_metadata['author']
                if enhanced_metadata.get('description'):
                    document.description = enhanced_metadata['description']
                if enhanced_metadata.get('keywords'):
                    document.keywords = enhanced_metadata['keywords']
                if enhanced_metadata.get('publication_date'):
                    # Parse publication date if it's a string
                    try:
                        from datetime import datetime
                        if isinstance(enhanced_metadata['publication_date'], str):
                            # Try to parse ISO format first
                            document.publication_date = datetime.fromisoformat(
                                enhanced_metadata['publication_date'].replace('Z', '+00:00')
                            )
                    except (ValueError, TypeError):
                        logger.warning(f"Could not parse publication date: {enhanced_metadata['publication_date']}")
                
                logger.info(f"Successfully fetched content for document {document.id}")
                
                # Validate extracted content
                await self._validate_document_content(document)
                
            else:
                # Fetch failed
                document.status = "fetch_failed"
                if document.document_metadata is None:
                    document.document_metadata = {}
                document.document_metadata.update({
                    'fetch_error': fetch_metadata.get('error', 'Unknown error'),
                    'fetch_metadata': fetch_metadata
                })
                logger.error(f"Failed to fetch content for document {document.id}: {fetch_metadata}")
            
            await self.session.commit()
            await self.session.refresh(document)
            
        except Exception as e:
            # Handle unexpected errors
            document.status = "fetch_error"
            if document.document_metadata is None:
                document.document_metadata = {}
            document.document_metadata['fetch_error'] = f'Unexpected error: {str(e)}'
            await self.session.commit()
            await self.session.refresh(document)
            logger.error(f"Unexpected error fetching content for document {document.id}: {str(e)}")
        
        return document

    async def get_user_documents(
        self,
        firebase_uid: str,
        page: int = 1,
        page_size: int = 20,
        status: Optional[str] = None
    ) -> Tuple[List[Document], int]:
        """Get paginated list of user documents"""
        
        user = await self._get_user_by_firebase_uid(firebase_uid)
        
        # Build query
        query = select(Document).where(Document.user_id == user.id)
        
        if status:
            query = query.where(Document.status == status)
        
        # Get total count
        count_query = select(func.count(Document.id)).where(Document.user_id == user.id)
        if status:
            count_query = count_query.where(Document.status == status)
        
        total_result = await self.session.execute(count_query)
        total = total_result.scalar()
        
        # Apply pagination
        offset = (page - 1) * page_size
        query = query.offset(offset).limit(page_size).order_by(Document.created_at.desc())
        
        result = await self.session.execute(query)
        documents = result.scalars().all()
        
        return documents, total

    async def get_document_by_id(
        self,
        firebase_uid: str,
        document_id: int
    ) -> Optional[Document]:
        """Get a specific document by ID for a user"""
        
        user = await self._get_user_by_firebase_uid(firebase_uid)
        
        query = select(Document).where(
            and_(Document.id == document_id, Document.user_id == user.id)
        )
        
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def update_document(
        self,
        firebase_uid: str,
        document_id: int,
        **update_data
    ) -> Optional[Document]:
        """Update document metadata"""
        
        document = await self.get_document_by_id(firebase_uid, document_id)
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
        firebase_uid: str,
        document_id: int
    ) -> bool:
        """Delete a document"""
        
        document = await self.get_document_by_id(firebase_uid, document_id)
        if not document:
            return False
        
        await self.session.delete(document)
        await self.session.commit()
        
        logger.info(f"Deleted document {document_id} for user")
        return True

    async def get_documents_by_url(
        self,
        firebase_uid: str,
        url: str
    ) -> List[Document]:
        """Get all documents for a specific URL"""
        
        user = await self._get_user_by_firebase_uid(firebase_uid)
        
        query = select(Document).where(
            and_(Document.user_id == user.id, Document.url == url)
        ).order_by(Document.created_at.desc())
        
        result = await self.session.execute(query)
        return result.scalars().all()

    async def update_document_status(
        self,
        firebase_uid: str,
        document_id: int,
        status: str,
        **metadata_updates
    ) -> Optional[Document]:
        """Update document processing status"""
        
        document = await self.get_document_by_id(firebase_uid, document_id)
        if not document:
            return None
        
        document.status = status
        
        # Update metadata if provided
        if metadata_updates:
            if document.document_metadata is None:
                document.document_metadata = {}
            document.document_metadata.update(metadata_updates)
        
        await self.session.commit()
        await self.session.refresh(document)
        
        logger.info(f"Updated document {document_id} status to {status}")
        return document

    async def get_documents_by_status(
        self,
        firebase_uid: str,
        status: str
    ) -> List[Document]:
        """Get all documents with a specific status"""
        
        user = await self._get_user_by_firebase_uid(firebase_uid)
        
        query = select(Document).where(
            and_(Document.user_id == user.id, Document.status == status)
        ).order_by(Document.created_at.desc())
        
        result = await self.session.execute(query)
        return result.scalars().all()

    async def count_user_documents(
        self,
        firebase_uid: str,
        status: Optional[str] = None
    ) -> int:
        """Count user documents, optionally filtered by status"""
        
        user = await self._get_user_by_firebase_uid(firebase_uid)
        
        query = select(func.count(Document.id)).where(Document.user_id == user.id)
        
        if status:
            query = query.where(Document.status == status)
        
        result = await self.session.execute(query)
        return result.scalar()
    
    async def _validate_document_content(self, document: Document) -> None:
        """Validate document content and update status accordingly"""
        try:
            from app.services.content_validation_service import get_content_validation_service
            
            if not document.content:
                logger.warning(f"Document {document.id} has no content to validate")
                return
            
            validation_service = get_content_validation_service()
            
            validation_report = await validation_service.validate_content(
                content=document.content,
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
            
            # Update document status based on validation
            if validation_report.is_valid:
                if document.status == "fetched":
                    document.status = "validated"
                logger.info(f"Document {document.id} content validation passed (score: {validation_report.overall_score:.2f})")
            else:
                document.status = "validation_failed"
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
