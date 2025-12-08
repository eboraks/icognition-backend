"""
Document service for managing web page documents
"""

from typing import Optional, List, Dict, Any, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from sqlalchemy.orm import selectinload
import logging
import html
from datetime import datetime

from app.models import Document, User, ContentExtraction, PageType, Entity, EntityDocument
from app.services.base_service import UserIsolatedService
from app.services.web_fetcher import WebPageFetcher, fetch_web_page
from app.services.user_service import UserService
from app.services.gemini_service import get_gemini_service, GeminiModel, GeminiConfig
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
                
                # Store page detection info if available
                if fetch_metadata.get('page_detection'):
                    page_detection = fetch_metadata['page_detection']
                    document.document_metadata['page_detection'] = page_detection
                    
                    # Log warnings if any
                    if page_detection.get('warnings'):
                        for warning in page_detection['warnings']:
                            logger.warning(f"Page detection warning for document {document.id}: {warning}")
                    
                    # If page requires JS and we detected placeholder content, mark it
                    if page_detection.get('issues'):
                        logger.info(f"Document {document.id} has detected issues: {', '.join(page_detection['issues'])}")
                
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
            # Extract text and metadata from HTML using BeautifulSoup-first approach
            extracted_text, extraction_metadata = await self._extract_text_from_html(content)
            
            # Use provided title or extracted title from metadata
            final_title = title or extraction_metadata.get('title') or "Untitled Document"
            
            document_data = {
                "user_id": user.id,
                "url": url,
                "title": final_title,
                "raw_html": content,  # Content is already sanitized from bookmark
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
                "raw_html": wrapped_html,  # Content is already sanitized from bookmark
                "content": content,  # Content is already sanitized from bookmark
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
        """Extract clean text from HTML content using BeautifulSoup-first approach with LLM fallback"""
        try:
            # 1. Try BeautifulSoup extraction first
            extraction_result = self._extract_content_with_beautifulsoup(html_content)
            
            # 2. If confidence >= 0.7, use it
            if extraction_result.extraction_confidence >= 0.7:
                logger.info(f"BeautifulSoup extraction successful with confidence {extraction_result.extraction_confidence}")
                return extraction_result.content, extraction_result.model_dump()
            
            # 3. Otherwise, use LLM
            logger.info(f"BeautifulSoup confidence too low ({extraction_result.extraction_confidence}), using LLM")
            llm_result = await self._extract_content_with_llm(html_content)
            
            if llm_result and llm_result.extraction_confidence >= 0.5:
                logger.info(f"LLM extraction successful with confidence {llm_result.extraction_confidence}")
                return llm_result.content, llm_result.model_dump()
            
            # 4. Final fallback: return BeautifulSoup result anyway
            logger.warning("LLM extraction also failed, using BeautifulSoup result")
            return extraction_result.content, extraction_result.model_dump()
                
        except Exception as e:
            logger.error(f"Error in content extraction, falling back to basic BeautifulSoup: {str(e)}")
            # Ultimate fallback: basic text extraction
            content = self._extract_text_with_beautifulsoup(html_content)
            return content, {"extraction_method": "beautifulsoup_fallback", "extraction_confidence": 0.0, "error": str(e), "page_type": "other"}

    def _extract_text_with_beautifulsoup(self, html_content: str) -> str:
        """Basic text extraction fallback method"""
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

    def _extract_content_with_beautifulsoup(self, html_content: str) -> ContentExtraction:
        """Extract structured content from HTML using BeautifulSoup with intelligent parsing"""
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Find main content container
            main_container = self._find_main_content_container(soup)
            
            # Extract all fields
            title = self._extract_title_from_html(soup)
            author = self._extract_author_from_html(soup)
            publication_date = self._extract_date_from_html(soup)
            page_type = self._extract_page_type_from_html(soup, "")
            image_url = self._extract_image_url_from_html(soup)
            tags = self._extract_tags_from_html(soup)
            metadata = self._extract_metadata_from_html(soup)
            content = self._extract_content_text(soup, main_container, page_type)
            
            # Calculate confidence
            confidence = self._calculate_extraction_confidence(
                content, title, author, publication_date, image_url, tags, page_type
            )
            
            return ContentExtraction(
                page_type=page_type,
                title=title,
                content=content,
                author=author,
                publication_date=publication_date,
                tags=tags,
                metadata=metadata,
                extraction_confidence=confidence,
                extraction_notes="BeautifulSoup extraction",
                image_url=image_url
            )
            
        except Exception as e:
            logger.error(f"Error in BeautifulSoup content extraction: {str(e)}")
            # Return minimal extraction on error
            return ContentExtraction(
                page_type="other",
                title="",
                content="",
                author="",
                publication_date="",
                tags=[],
                metadata={},
                extraction_confidence=0.0,
                extraction_notes=f"BeautifulSoup extraction failed: {str(e)}",
                image_url=""
            )

    def _find_main_content_container(self, soup: BeautifulSoup):
        """Find the main content container using semantic HTML5 and common patterns"""
        # PRIORITY 2: Enhanced selectors with WordPress/Elementor support
        # Priority order: specific content containers > semantic HTML > generic patterns
        selectors = [
            'article',
            'main',
            # WordPress/Elementor/Page Builder specific (high priority)
            '.jupiterx-post-content',
            '.elementor-widget-text-editor',
            '.entry-content',
            '.post-content',
            '.article-content',
            '.article-body',
            '.story-content',
            # Gutenberg blocks
            '.wp-block-post-content',
            # Divi builder
            '.et_pb_post_content',
            # Generic semantic containers (exclude nav/sidebar)
            'div[id="main"]:not([id*="sidebar"])',
            'div[id="content"]:not([id*="sidebar"])',
            'div[id*="main-content"]',
            'div[id*="article"]',
            'div[id*="post-"]:not([id*="related"]):not([id*="nav"])',
            'div[id*="entry"]',
            # Class-based selectors (more specific to avoid sidebars)
            'div[class*="main-content"]:not([class*="sidebar"])',
            'div[class*="post-content"]:not([class*="sidebar"])',
            'div[class*="article-content"]:not([class*="sidebar"])',
            'div[class*="entry-content"]:not([class*="sidebar"])',
            # Less specific fallbacks
            'div[id*="main"]',
            'div[class*="main"]',
            'div[id*="content"]',
            'div[class*="content"]',
            'div[id*="body"]',
            'div[class*="body"]'
        ]
        
        for selector in selectors:
            try:
                container = soup.select_one(selector)
                if container:
                    # Verify container has meaningful content (not just navigation)
                    text_content = container.get_text(strip=True)
                    if len(text_content) > 100:  # Minimum content threshold
                        logger.debug(f"Found main content container using selector: {selector}")
                        return container
            except Exception as e:
                logger.debug(f"Error with selector {selector}: {str(e)}")
                continue
        
        # Fallback to body if nothing found
        logger.debug("No specific content container found, falling back to body")
        return soup.find('body') or soup

    def _extract_title_from_html(self, soup: BeautifulSoup) -> str:
        """Extract title using multiple strategies, preserving link text and title attributes"""
        # Priority order
        selectors = [
            'meta[property="og:title"]',
            'meta[name="twitter:title"]',
            'meta[name="title"]',
            'h1',
            'title'
        ]
        
        for selector in selectors:
            element = soup.select_one(selector)
            if element:
                if element.name == 'meta':
                    title = element.get('content', '').strip()
                else:
                    # For title/h1 elements, preserve link text and title attributes
                    # get_text() already preserves link text, but we want to ensure
                    # we also capture title attributes from links if link text is empty
                    links = element.find_all('a', recursive=True)
                    if links:
                        # Build title preserving all text including link text
                        # get_text() will include link text, but we also want to preserve
                        # title attributes from links that might have no visible text
                        title = element.get_text(separator=' ', strip=True)
                        
                        # If any link has a title attribute but no text, append it
                        for link in links:
                            link_text = link.get_text(strip=True)
                            link_title_attr = link.get('title', '').strip()
                            if not link_text and link_title_attr:
                                # Link has no text but has title attribute, append it
                                if link_title_attr not in title:
                                    title = f"{title} {link_title_attr}".strip()
                    else:
                        # No links, use standard text extraction
                        title = element.get_text(separator=' ', strip=True)
                
                if title and len(title) > 0:
                    return title
        
        return ""

    def _extract_author_from_html(self, soup: BeautifulSoup) -> str:
        """Extract author using multiple strategies"""
        # Priority order
        selectors = [
            'meta[name="author"]',
            'meta[property="article:author"]',
            'a[rel="author"]',
            'span[itemprop="author"]',
            '[class*="author"]',
            '[id*="author"]',
            '[class*="byline"]',
            '[class*="writer"]'
        ]
        
        for selector in selectors:
            element = soup.select_one(selector)
            if element:
                if element.name == 'meta':
                    author = element.get('content', '').strip()
                else:
                    author = element.get_text().strip()
                
                if author and len(author) > 0:
                    return author
        
        return ""

    def _extract_date_from_html(self, soup: BeautifulSoup) -> str:
        """Extract publication date using multiple strategies"""
        # Priority order
        selectors = [
            'meta[property="article:published_time"]',
            'time[datetime]',
            'time[pubdate]',
            'meta[itemprop="datePublished"]',
            '[class*="date"]',
            '[id*="date"]',
            '[class*="published"]',
            '[class*="timestamp"]'
        ]
        
        for selector in selectors:
            element = soup.select_one(selector)
            if element:
                if element.name == 'meta':
                    date = element.get('content', '').strip()
                elif element.name == 'time':
                    date = element.get('datetime', '').strip() or element.get_text().strip()
                else:
                    date = element.get_text().strip()
                
                if date and len(date) > 0:
                    return date
        
        return ""

    def _extract_page_type_from_html(self, soup: BeautifulSoup, url: str) -> str:
        """Detect page type from HTML and URL patterns"""
        # Check Open Graph type first
        og_type = soup.select_one('meta[property="og:type"]')
        if og_type:
            og_value = og_type.get('content', '').lower()
            if og_value == 'article':
                # Distinguish between news and blog based on site
                site_name = self._extract_site_name(soup)
                if any(news_site in site_name.lower() for news_site in ['news', 'cnn', 'bbc', 'reuters', 'yahoo', 'finance']):
                    return "news_article"
                else:
                    return "blog_post"
            elif og_value == 'website':
                return "landing_page"
            elif og_value == 'product':
                return "product_page"
        
        # Check URL patterns
        if '/wiki/' in url.lower():
            return "wiki"
        elif '/docs/' in url.lower() or '/documentation/' in url.lower():
            return "documentation"
        elif 'reddit.com' in url.lower():
            return "social_media"
        elif 'medium.com' in url.lower():
            return "blog_post"
        
        # Check site name heuristics
        site_name = self._extract_site_name(soup)
        if any(social_site in site_name.lower() for social_site in ['reddit', 'twitter', 'facebook', 'instagram']):
            return "social_media"
        elif any(doc_site in site_name.lower() for doc_site in ['docs', 'documentation', 'api', 'guide']):
            return "documentation"
        
        return "other"

    def _extract_site_name(self, soup: BeautifulSoup) -> str:
        """Extract site name from HTML"""
        selectors = [
            'meta[property="og:site_name"]',
            'meta[name="application-name"]'
        ]
        
        for selector in selectors:
            element = soup.select_one(selector)
            if element:
                site_name = element.get('content', '').strip()
                if site_name:
                    return site_name
        
        return ""

    def _extract_image_url_from_html(self, soup: BeautifulSoup) -> str:
        """Extract primary image URL"""
        # Priority order
        selectors = [
            'meta[property="og:image"]',
            'meta[name="twitter:image"]',
            'img'
        ]
        
        for selector in selectors:
            element = soup.select_one(selector)
            if element:
                if element.name == 'meta':
                    image_url = element.get('content', '').strip()
                else:
                    image_url = element.get('src', '').strip()
                
                if image_url and len(image_url) > 0:
                    return image_url
        
        return ""

    def _extract_tags_from_html(self, soup: BeautifulSoup) -> list[str]:
        """Extract tags/keywords from HTML"""
        tags = []
        
        # Meta keywords
        keywords_meta = soup.select_one('meta[name="keywords"]')
        if keywords_meta:
            keywords = keywords_meta.get('content', '')
            if keywords:
                tags.extend([tag.strip() for tag in keywords.split(',') if tag.strip()])
        
        # Article tags
        article_tags = soup.select('meta[property="article:tag"]')
        for tag_meta in article_tags:
            tag = tag_meta.get('content', '').strip()
            if tag:
                tags.append(tag)
        
        # Elements with tag-related classes
        tag_elements = soup.select('[class*="tag"], [class*="label"], [class*="category"]')
        for element in tag_elements:
            tag_text = element.get_text().strip()
            if tag_text and tag_text not in tags:
                tags.append(tag_text)
        
        return tags[:10]  # Limit to 10 tags

    def _extract_metadata_from_html(self, soup: BeautifulSoup) -> dict:
        """Extract additional metadata"""
        metadata = {}
        
        # Site name
        site_name = self._extract_site_name(soup)
        if site_name:
            metadata['site_name'] = site_name
        
        # Description
        desc_selectors = [
            'meta[property="og:description"]',
            'meta[name="description"]',
            'meta[name="twitter:description"]'
        ]
        
        for selector in desc_selectors:
            element = soup.select_one(selector)
            if element:
                description = element.get('content', '').strip()
                if description:
                    metadata['description'] = description
                    break
        
        return metadata

    def _extract_content_text(self, soup: BeautifulSoup, container, page_type: str) -> str:
        """Extract content from the main container, preserving HTML structure wrapped in <article> tags"""
        if not container:
            return ""
        
        # PRIORITY 1: More specific unwanted selectors to avoid removing content
        # Use prefix matches (^=) and specific classes instead of contains (*=)
        unwanted_selectors = [
            'script', 'style', 'nav', 'aside',
            # Only remove actual structural elements, not content metadata
            'header:not(article header):not(main header):not([class*="post-header"]):not([class*="article-header"])',
            'footer:not(article footer):not(main footer):not([class*="post-footer"]):not([class*="article-footer"])',
            '[role="banner"]', '[role="navigation"]', '[role="complementary"]',
            # Use prefix matches to be more specific
            '[class^="nav-"]', '[class^="menu-"]', '[class^="sidebar-"]',
            # Specific ad/promotional classes
            '.advertisement', '.ads', '.ad-banner', '.sponsored', '.promo',
            # Social and newsletter - specific classes only
            '.social-share', '.newsletter-signup', '.subscribe-box',
            # Cookie/privacy notices
            '.cookie-notice', '.privacy-notice', '.cky-consent',
            # Related content sections - use specific classes
            '.related-posts', '.recommended-posts', '.recommended-articles'
        ]
        
        # For forum/social media, keep comments
        if page_type not in ['forum_post', 'social_media']:
            unwanted_selectors.extend(['.comments-section', '.comment-form', '[id^="comment-"]'])
        
        for selector in unwanted_selectors:
            try:
                for element in container.select(selector):
                    element.decompose()
            except Exception as e:
                logger.debug(f"Error removing unwanted selector {selector}: {str(e)}")
                continue
        
        # PRIORITY 3: Extract content elements preserving HTML structure
        # First try semantic tags
        content_elements = container.select('h1, h2, h3, h4, h5, h6, p, ul, ol, blockquote')
        
        # If not enough content found, look for page builder containers (Elementor, Divi, etc.)
        if not content_elements or len(''.join(e.get_text(strip=True) for e in content_elements)) < 200:
            logger.debug("Semantic tags yielded insufficient content, checking page builder containers")
            
            # Look for Elementor/WordPress widgets
            page_builder_widgets = container.select(
                '.elementor-widget-container, .elementor-text-editor, '
                '.et_pb_text, .fl-rich-text, '  # Divi and Beaver Builder
                '.wp-block-paragraph, .entry-content > div'  # Gutenberg and WordPress
            )
            
            additional_content = []
            for widget in page_builder_widgets:
                # Extract content from widget containers
                widget_content = widget.select('p, h1, h2, h3, h4, h5, h6, ul, ol, blockquote')
                additional_content.extend(widget_content)
            
            if additional_content:
                logger.debug(f"Found {len(additional_content)} additional content elements in page builder widgets")
                content_elements = additional_content
        
        # PRIORITY 4: Enhanced fallback - find text-bearing divs
        if not content_elements:
            logger.debug("No content elements found, using enhanced fallback")
            text_parts = []
            seen_texts = set()  # Track seen text to avoid duplicates
            
            # Walk through all text-bearing elements
            for elem in container.find_all(['div', 'section', 'span', 'p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6']):
                # Skip empty elements
                text = elem.get_text(strip=True)
                if len(text) < 20:  # Minimum meaningful content threshold
                    continue
                
                # Avoid duplicates from nested elements
                if text in seen_texts:
                    continue
                
                # Check if this text is not a substring of already captured text
                is_duplicate = False
                for seen in seen_texts:
                    if text in seen or seen in text:
                        # If current text is longer, replace the shorter one
                        if len(text) > len(seen):
                            seen_texts.discard(seen)
                            for i, part in enumerate(text_parts):
                                if seen in part:
                                    text_parts[i] = text
                                    is_duplicate = True
                                    break
                        else:
                            is_duplicate = True
                        break
                
                if not is_duplicate:
                    text_parts.append(text)
                    seen_texts.add(text)
            
            if text_parts:
                # Wrap in article with paragraphs
                paragraphs = ''.join(f'<p>{self._escape_html(text)}</p>' for text in text_parts[:50])  # Limit to 50 parts
                return f"<article>{paragraphs}</article>"
            
            # Ultimate fallback: get all text
            text = container.get_text(strip=True)
            if text:
                return f"<article><p>{self._escape_html(text)}</p></article>"
            return ""
        
        # Create article wrapper
        article = soup.new_tag('article')
        
        # Track processed elements to avoid duplicates (e.g., links inside paragraphs)
        processed_element_ids = set()
        
        # Add each content element to article, preserving structure
        for element in content_elements:
            # Skip if element is already processed (e.g., a link inside a paragraph)
            element_id = id(element)
            if element_id in processed_element_ids:
                continue
            
            # Special handling for standalone links
            if element.name == 'a':
                link_text = element.get_text().strip()
                link_title_attr = element.get('title', '').strip()
                link_href = element.get('href', '').strip()
                
                # Only include links with meaningful text or title attribute
                if not link_text and not link_title_attr:
                    continue
                
                # Check if link is nested inside another content element
                # If so, it will be preserved as part of the parent element
                parent = element.parent
                is_nested = False
                while parent and parent != container:
                    if parent.name in ['p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'li', 'blockquote']:
                        # Link is inside a content element, skip standalone processing
                        is_nested = True
                        break
                    parent = parent.parent
                
                if is_nested:
                    # Link will be preserved as part of parent, skip standalone extraction
                    continue
                
                # Link is standalone, include it
                # Wrap standalone links in a paragraph for better structure
                p_tag = soup.new_tag('p')
                cloned_link = self._clone_element(soup, element)
                if cloned_link:
                    p_tag.append(cloned_link)
                    article.append(p_tag)
                    processed_element_ids.add(element_id)
                continue
            
            # Standard content elements (h1-h6, p, ul, ol, li, blockquote)
            element_text = element.get_text().strip()
            if element_text:
                # Extract the element's HTML string to preserve inner structure
                # This preserves nested tags, lists, links, etc.
                cloned_element = self._clone_element(soup, element)
                if cloned_element:
                    article.append(cloned_element)
                    # Mark this element and all its descendants as processed
                    for descendant in element.descendants:
                        if hasattr(descendant, 'name'):
                            processed_element_ids.add(id(descendant))
        
        # Return the HTML string
        return str(article) if article.contents else ""
    
    def _clone_element(self, soup: BeautifulSoup, element) -> Optional[Any]:
        """Clone an element preserving its structure and attributes"""
        try:
            element_html = str(element)
            temp_soup = BeautifulSoup(element_html, 'html.parser')
            cloned_element = temp_soup.find(element.name)
            return cloned_element
        except Exception as e:
            logger.debug(f"Error cloning element {element.name if hasattr(element, 'name') else 'unknown'}: {str(e)}")
            return None
    
    def _escape_html(self, text: str) -> str:
        """Escape HTML special characters in text"""
        return html.escape(text)

    def _calculate_extraction_confidence(self, content: str, title: str, author: str, 
                                       publication_date: str, image_url: str, 
                                       tags: list, page_type: str) -> float:
        """Calculate weighted confidence score"""
        total_possible = 10  # Total weighted points
        weighted_score = 0
        
        # Content: 3 points
        if content and len(content.strip()) > 100:
            weighted_score += 3
        
        # Title: 3 points  
        if title and len(title.strip()) > 0:
            weighted_score += 3
        
        # Author: 1 point
        if author and author != "":
            weighted_score += 1
        
        # Publication date: 1 point
        if publication_date and publication_date != "":
            weighted_score += 1
        
        # Image URL: 1 point
        if image_url and image_url != "":
            weighted_score += 1
        
        # Tags: 0.5 points (if any exist)
        if tags and len(tags) > 0:
            weighted_score += 0.5
        
        # Page type: 0.5 points (if not "other")
        if page_type and page_type != "other":
            weighted_score += 0.5
        
        return weighted_score / total_possible

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
                
                # Store page detection info if available
                if fetch_metadata.get('page_detection'):
                    page_detection = fetch_metadata['page_detection']
                    document.document_metadata['page_detection'] = page_detection
                    
                    # Log warnings if any
                    if page_detection.get('warnings'):
                        for warning in page_detection['warnings']:
                            logger.warning(f"Page detection warning for document {document.id}: {warning}")
                    
                    # If page requires JS and we detected placeholder content, mark it
                    if page_detection.get('issues'):
                        logger.info(f"Document {document.id} has detected issues: {', '.join(page_detection['issues'])}")
                
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
        document_id: int  # Document ID is now int
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
            .where(Entity.user_id == user.id)
            .order_by(Entity.type, Entity.name, Entity.id)
        )
        
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
