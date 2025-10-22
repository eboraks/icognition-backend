"""
Document service for managing web page documents
"""

from typing import Optional, List, Dict, Any, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from sqlalchemy.orm import selectinload
import logging
from datetime import datetime

from app.models import Document, User, ContentExtraction, PageType
from app.services.base_service import UserIsolatedService
from app.services.web_fetcher import WebPageFetcher, fetch_web_page
from app.services.user_service import UserService
from app.services.gemini_service import get_gemini_service, GeminiModel, GeminiConfig
from app.utils.logging import get_logger
from bs4 import BeautifulSoup
from app.services.content_validation_service import get_content_validation_service

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
        self.session.add(document)
        await self.session.commit()
        await self.session.refresh(document)
        
        logger.info(f"Created document {document.id} for user {user.id}")
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
                # Extract enhanced metadata and main content from HTML
                async with WebPageFetcher() as fetcher:
                    enhanced_metadata = fetcher.extract_enhanced_metadata(html_content)
                    content_extraction = fetcher.extract_main_content(html_content)
                
                # Update document with fetched content
                document.raw_html = html_content
                # Document fetched successfully
                
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
                # Document fetch failed
                document.document_metadata = {
                    'fetch_error': fetch_metadata.get('error', 'Unknown error'),
                    'fetch_metadata': fetch_metadata
                }
                logger.error(f"Failed to fetch content for document {document.id}: {fetch_metadata}")
            
            await self.session.commit()
            await self.session.refresh(document)
            
        except Exception as e:
            # Handle unexpected errors
            # Document fetch error
            document.document_metadata = {
                'fetch_error': f'Unexpected error: {str(e)}'
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
            # Extract text and metadata from HTML using LLM-first approach
            extracted_text, extraction_metadata = await self._extract_text_from_html(content)
            extracted_title = self._extract_title_from_html(content)
            
            # Use provided title or extracted title or title from extraction
            final_title = title or extraction_metadata.get('title') or extracted_title or "Untitled Document"
            
            document_data = {
                "user_id": user.id,
                "url": url,
                "title": final_title,
                "raw_html": content,
                "content": extracted_text,
                "content_source": "html",
                "extracted_content": extraction_metadata,  # Store full extraction as JSONB
                # Document processed
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
                # Document processed
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

    async def _extract_text_from_html(self, html_content: str) -> Tuple[str, Optional[Dict]]:
        """Extract clean text from HTML content using LLM-first approach"""
        try:
            # Try LLM extraction first
            extraction_result = await self._extract_content_with_llm(html_content)
            
            if extraction_result and extraction_result.extraction_confidence >= 0.5:
                logger.info(f"LLM extraction successful: {extraction_result.page_type}, confidence: {extraction_result.extraction_confidence}")
                # Return content and full extraction metadata
                return extraction_result.content, extraction_result.model_dump()
            else:
                logger.warning(f"LLM extraction low confidence or failed, falling back to BeautifulSoup")
                content = self._extract_text_with_beautifulsoup(html_content)
                return content, {"extraction_method": "beautifulsoup", "extraction_confidence": 0.0, "page_type": "other"}
                
        except Exception as e:
            logger.error(f"Error in LLM extraction, falling back to BeautifulSoup: {str(e)}")
            content = self._extract_text_with_beautifulsoup(html_content)
            return content, {"extraction_method": "beautifulsoup_fallback", "extraction_confidence": 0.0, "error": str(e), "page_type": "other"}

    def _extract_text_with_beautifulsoup(self, html_content: str) -> str:
        """Extract clean text from HTML content using BeautifulSoup"""
        try:
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
            logger.error(f"Error extracting text from HTML with BeautifulSoup: {str(e)}")
            # Fallback: return the HTML content as-is
            return html_content

    async def _extract_content_with_llm(self, html_content: str) -> Optional[ContentExtraction]:
        """Extract content from HTML using Gemini Flash Lite LLM"""
        try:
            # Create extraction prompt
            prompt = f"""Analyze this HTML page and extract its core content intelligently.

1. Identify the page type from these exact options:
   - blog_post: Personal or company blog articles
   - news_article: News stories and journalistic content
   - product_page: Product listings, e-commerce pages
   - documentation: Technical docs, API docs, help pages
   - landing_page: Marketing pages, homepage, promotional content
   - social_media: Social media posts, tweets, updates
   - forum_post: Discussion forum posts and threads
   - wiki: Wikipedia-style informational pages
   - other: Any other type of content
   - not_clear: When page type cannot be determined or content is confusing

2. Extract ONLY the main content, excluding:
   - Navigation menus, sidebars, footers, headers
   - Advertisements and promotional content
   - Related articles/products lists
   - Comments sections (unless page type is forum_post/social_media)
   - Cookie notices, popups, banners
   - Social media share buttons

3. For social_media: Include post content, author, tags, images
4. For product_page: Include name, description, price, key features
5. For news_article/blog_post: Include article text, author, publication date
6. For documentation: Include the main topic and content

If the page is confusing (e.g., landing page with no clear content), use page_type "not_clear" and explain why extraction isn't possible in extraction_notes.

HTML Content:
{html_content}

Return structured data with high confidence (0.7-1.0) only if you can clearly identify and extract meaningful content. Use medium confidence (0.4-0.7) if content is present but unclear. Use low confidence (0.0-0.4) if extraction failed or page has no clear content.

Return your response as JSON in this exact format, if the fields are not present, return an empty string.
{{
  "page_type": "one_of_the_types_above",
  "title": "extracted_title",
  "content": "main_content_text",
  "author": "author_name_or_empty_string",
  "publication_date": "date_or_empty_string", 
  "tags": ["tag1", "tag2"],
  "metadata": {{}},
  "extraction_confidence": 0.8,
  "extraction_notes": "any_notes_or_empty_string"
}}"""

            # Initialize Gemini service
            gemini_service = get_gemini_service()
            
            # Configure for structured output
            config = GeminiConfig(
                temperature=0.0,
                response_mime_type="application/json"
            )
            
            # Get response from Gemini AI
            response = await gemini_service.generate_content(
                prompt=prompt,
                model=GeminiModel.FLASH_LITE,
                config=config
            )
            
            # Parse the structured response
            import json
            try:
                response_data = json.loads(response['content'])
                extraction_result = ContentExtraction(**response_data)
                logger.info(f"LLM extraction completed: page_type={extraction_result.page_type}, confidence={extraction_result.extraction_confidence}")
                return extraction_result
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse JSON response from LLM: {e}")
                return None
            
        except Exception as e:
            logger.error(f"Error in LLM content extraction: {str(e)}")
            return None

    def _extract_title_from_html(self, html_content: str) -> str:
        """Extract title from HTML content"""
        try:
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
                # Extract enhanced metadata and main content from HTML
                async with WebPageFetcher() as fetcher:
                    enhanced_metadata = fetcher.extract_enhanced_metadata(html_content)
                    content_extraction = fetcher.extract_main_content(html_content)
                
                # Update document with fetched content
                document.raw_html = html_content
                # Document fetched successfully
                
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
                # Document fetch failed
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
            # Document fetch error
            if document.document_metadata is None:
                document.document_metadata = {}
            document.document_metadata['fetch_error'] = f'Unexpected error: {str(e)}'
            await self.session.commit()
            await self.session.refresh(document)
            logger.error(f"Unexpected error fetching content for document {document.id}: {str(e)}")
        
        return document

    async def get_user_documents(
        self,
        user_id: str,
        page: int = 1,
        page_size: int = 20
    ) -> Tuple[List[Document], int]:
        """Get paginated list of user documents"""
        
        user = await UserService.get_user_by_firebase_uid(self.session, user_id)
        if not user:
            return [], 0
        
        # Build query
        query = select(Document).where(Document.user_id == user.id)
        
        # Status filtering removed (status field no longer exists)
        
        # Get total count
        count_query = select(func.count(Document.id)).where(Document.user_id == user.id)
        
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
        user_id: str,
        document_id: str  # Changed from int to str for UUID
    ) -> Optional[Document]:
        """Get a specific document by ID for a user"""
        
        query = select(Document).where(
            and_(Document.id == document_id, Document.user_id == user_id)
        )
        
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def update_document(
        self,
        user_id: str,
        document_id: str,  # Changed from int to str for UUID
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
        
        user = await UserService.get_user_by_firebase_uid(self.session, user_id)
        if not user:
            return []
        
        query = select(Document).where(
            Document.user_id == user.id
        ).order_by(Document.created_at.desc())
        
        result = await self.session.execute(query)
        return result.scalars().all()

    async def count_user_documents(
        self,
        user_id: str
    ) -> int:
        """Count user documents"""
        
        user = await UserService.get_user_by_firebase_uid(self.session, user_id)
        if not user:
            return 0
        
        query = select(func.count(Document.id)).where(Document.user_id == user.id)
        
        # Status filtering removed (status field no longer exists)
        
        result = await self.session.execute(query)
        return result.scalar()
    
    async def _validate_document_content(self, document: Document) -> None:
        """Validate document content"""
        try:
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
