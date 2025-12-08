"""
Web page fetching service for retrieving HTML content from URLs
"""

import asyncio
from typing import Optional, Dict, Any, Tuple
from urllib.parse import urljoin, urlparse
import httpx
from bs4 import BeautifulSoup, NavigableString, Tag
import logging

from app.utils.logging import get_logger
from app.utils.text_utils import extract_text_from_html

logger = get_logger(__name__)


class WebPageFetcher:
    """Service for fetching web page content"""
    
    ALLOWED_BLOCK_TAGS = {
        'p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'ul', 'ol', 'li', 'blockquote'
    }
    ALLOWED_INLINE_TAGS = {'strong', 'em', 'b', 'i', 'u', 'a', 'code'}
    SELF_CLOSING_TAGS = {'br'}
    TEXT_CONTAINER_TAGS = {'p', 'li', 'blockquote', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6'}
    
    # URL patterns for problematic domains that require special handling
    PROBLEMATIC_DOMAINS = {
        'js_required': [
            'x.com', 'twitter.com',  # X/Twitter requires JavaScript
            'facebook.com', 'fb.com',  # Facebook requires JavaScript
            'instagram.com',  # Instagram requires JavaScript
            'linkedin.com',  # LinkedIn requires JavaScript
        ],
        'paywall': [
            'nytimes.com', 'wsj.com', 'washingtonpost.com',  # News paywalls
            'medium.com',  # Medium paywall
        ],
        'login_required': [
            'yahoo.com',  # Yahoo requires login for some content
            'reddit.com',  # Some Reddit content requires login
        ],
        'dynamic_content': [
            'youtube.com', 'youtu.be',  # Video platform
            'tiktok.com',  # Video platform
        ]
    }
    
    def __init__(self, timeout: int = 30, max_redirects: int = 5):
        self.timeout = timeout
        self.max_redirects = max_redirects
        self.client = None
    
    @staticmethod
    def _get_browser_headers() -> Dict[str, str]:
        """Get realistic browser headers to avoid bot detection"""
        return {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br, zstd',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Cache-Control': 'max-age=0',
        }
    
    @staticmethod
    def _detect_page_type(url: str) -> Dict[str, Any]:
        """
        Detect page type and potential issues based on URL
        
        Returns:
            Dictionary with page_type, issues, and warnings
        """
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        
        # Remove www. prefix for matching
        if domain.startswith('www.'):
            domain = domain[4:]
        
        detection = {
            'page_type': 'standard',
            'issues': [],
            'warnings': [],
            'requires_js': False,
            'has_paywall': False,
            'requires_login': False,
            'is_dynamic': False
        }
        
        # Check for JavaScript-required sites
        for js_domain in WebPageFetcher.PROBLEMATIC_DOMAINS['js_required']:
            if js_domain in domain:
                detection['page_type'] = 'js_required'
                detection['requires_js'] = True
                detection['warnings'].append(f'Domain {domain} requires JavaScript to render content. Static HTML extraction may fail.')
                break
        
        # Check for paywall sites
        for paywall_domain in WebPageFetcher.PROBLEMATIC_DOMAINS['paywall']:
            if paywall_domain in domain:
                detection['has_paywall'] = True
                detection['warnings'].append(f'Domain {domain} may have paywall restrictions.')
                break
        
        # Check for login-required sites
        for login_domain in WebPageFetcher.PROBLEMATIC_DOMAINS['login_required']:
            if login_domain in domain:
                detection['requires_login'] = True
                detection['warnings'].append(f'Domain {domain} may require login to access content.')
                break
        
        # Check for dynamic content sites
        for dynamic_domain in WebPageFetcher.PROBLEMATIC_DOMAINS['dynamic_content']:
            if dynamic_domain in domain:
                detection['is_dynamic'] = True
                detection['warnings'].append(f'Domain {domain} serves dynamic/video content that may not be extractable via static HTML.')
                break
        
        # Compile issues list
        if detection['requires_js']:
            detection['issues'].append('javascript_required')
        if detection['has_paywall']:
            detection['issues'].append('paywall')
        if detection['requires_login']:
            detection['issues'].append('login_required')
        if detection['is_dynamic']:
            detection['issues'].append('dynamic_content')
        
        return detection
    
    async def __aenter__(self):
        """Async context manager entry"""
        self.client = httpx.AsyncClient(
            timeout=self.timeout,
            follow_redirects=True,
            max_redirects=self.max_redirects,
            headers=self._get_browser_headers()
        )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        if self.client:
            await self.client.aclose()
    
    async def fetch_page(self, url: str) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
        """
        Fetch web page content from URL
        
        Args:
            url: URL to fetch
            
        Returns:
            Tuple of (success, html_content, metadata)
        """
        try:
            logger.info(f"Fetching page: {url}")
            
            # Detect page type and potential issues
            page_detection = self._detect_page_type(url)
            
            # Log warnings for problematic domains
            if page_detection['warnings']:
                for warning in page_detection['warnings']:
                    logger.warning(f"URL detection warning for {url}: {warning}")
            
            response = await self.client.get(url)
            response.raise_for_status()
            
            # Get content type
            content_type = response.headers.get('content-type', '').lower()
            
            # Check if it's HTML content
            if 'text/html' not in content_type:
                logger.warning(f"Non-HTML content type: {content_type}")
                return False, None, {
                    'error': 'Non-HTML content',
                    'content_type': content_type,
                    'status_code': response.status_code,
                    'page_detection': page_detection
                }
            
            # Get HTML content
            html_content = response.text
            
            # Check for JavaScript placeholder content
            js_placeholders = [
                'javascript is not available',
                'please enable javascript',
                'javascript is disabled',
                'enable javascript to continue',
                'noscript',
            ]
            html_lower = html_content.lower()
            has_js_placeholder = any(placeholder in html_lower for placeholder in js_placeholders)
            
            if has_js_placeholder and page_detection['requires_js']:
                logger.warning(f"Detected JavaScript placeholder content for {url}. Content extraction will likely fail.")
                page_detection['issues'].append('js_placeholder_detected')
            
            # Basic validation
            if len(html_content.strip()) < 100:
                logger.warning(f"Page content too short: {len(html_content)} characters")
                return False, None, {
                    'error': 'Content too short',
                    'content_length': len(html_content),
                    'status_code': response.status_code,
                    'page_detection': page_detection
                }
            
            # Extract basic metadata
            metadata = {
                'status_code': response.status_code,
                'content_type': content_type,
                'content_length': len(html_content),
                'final_url': str(response.url),
                'headers': dict(response.headers),
                'page_detection': page_detection
            }
            
            logger.info(f"Successfully fetched page: {url} ({len(html_content)} chars)")
            if page_detection['warnings']:
                logger.info(f"Page detection warnings: {', '.join(page_detection['warnings'])}")
            
            return True, html_content, metadata
            
        except httpx.TimeoutException:
            logger.error(f"Timeout fetching page: {url}")
            return False, None, {'error': 'Request timeout'}
            
        except httpx.TooManyRedirects:
            logger.error(f"Too many redirects for page: {url}")
            return False, None, {'error': 'Too many redirects'}
            
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error fetching page: {url} - {e.response.status_code}")
            return False, None, {
                'error': f'HTTP {e.response.status_code}',
                'status_code': e.response.status_code
            }
            
        except httpx.RequestError as e:
            logger.error(f"Request error fetching page: {url} - {str(e)}")
            return False, None, {'error': f'Request error: {str(e)}'}
            
        except Exception as e:
            logger.error(f"Unexpected error fetching page: {url} - {str(e)}")
            return False, None, {'error': f'Unexpected error: {str(e)}'}
    
    async def validate_url(self, url: str) -> Tuple[bool, Optional[str]]:
        """
        Validate URL format and accessibility
        
        Args:
            url: URL to validate
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            # Parse URL
            parsed = urlparse(url)
            
            # Check scheme
            if parsed.scheme not in ['http', 'https']:
                return False, f"Invalid scheme: {parsed.scheme}"
            
            # Check netloc
            if not parsed.netloc:
                return False, "Missing domain"
            
            # Check for basic URL structure
            if not parsed.path and not parsed.query and not parsed.fragment:
                return False, "Invalid URL structure"
            
            return True, None
            
        except Exception as e:
            return False, f"URL validation error: {str(e)}"
    
    def extract_basic_metadata(self, html_content: str) -> Dict[str, Any]:
        """
        Extract basic metadata from HTML content
        
        Args:
            html_content: Raw HTML content
            
        Returns:
            Dictionary of extracted metadata
        """
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            
            metadata = {}
            
            # Extract title
            title_tag = soup.find('title')
            if title_tag:
                metadata['title'] = title_tag.get_text().strip()
            
            # Extract meta description
            meta_desc = soup.find('meta', attrs={'name': 'description'})
            if meta_desc:
                metadata['description'] = meta_desc.get('content', '').strip()
            
            # Extract meta keywords
            meta_keywords = soup.find('meta', attrs={'name': 'keywords'})
            if meta_keywords:
                keywords = meta_keywords.get('content', '').strip()
                if keywords:
                    metadata['keywords'] = [k.strip() for k in keywords.split(',')]
            
            # Extract author
            meta_author = soup.find('meta', attrs={'name': 'author'})
            if meta_author:
                metadata['author'] = meta_author.get('content', '').strip()
            
            # Extract Open Graph title
            og_title = soup.find('meta', attrs={'property': 'og:title'})
            if og_title and not metadata.get('title'):
                metadata['title'] = og_title.get('content', '').strip()
            
            # Extract Open Graph description
            og_desc = soup.find('meta', attrs={'property': 'og:description'})
            if og_desc and not metadata.get('description'):
                metadata['description'] = og_desc.get('content', '').strip()
            
            return metadata
            
        except Exception as e:
            logger.error(f"Error extracting metadata: {str(e)}")
            return {}
    
    def extract_main_content(self, html_content: str) -> Dict[str, Any]:
        """
        Extract main content from HTML using multiple strategies
        
        Args:
            html_content: Raw HTML content
            
        Returns:
            Dictionary with extracted content and metadata
        """
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Remove unwanted elements
            self._remove_unwanted_elements(soup)
            
            # Try multiple content extraction strategies
            content_strategies = [
                self._extract_by_article_tag,
                self._extract_by_content_selectors,
                self._extract_by_text_density,
                self._extract_by_main_tag,
                self._extract_by_body_fallback
            ]
            
            best_element = None
            best_score = 0
            
            for strategy in content_strategies:
                try:
                    element, score = strategy(soup)
                    if element and score > best_score:
                        best_element = element
                        best_score = score
                except Exception as e:
                    logger.debug(f"Content extraction strategy failed: {str(e)}")
                    continue
            
            if not best_element:
                # Fallback to body content
                best_element = soup.find('body') or soup
            
            # Build sanitized HTML fragment
            sanitized_html = self._sanitize_html_fragment(best_element)
            plain_text = extract_text_from_html(sanitized_html)
            
            return {
                'content': sanitized_html,
                'content_text': plain_text,
                'content_length': len(plain_text),
                'extraction_score': best_score,
                'word_count': len(plain_text.split())
            }
            
        except Exception as e:
            logger.error(f"Error extracting main content: {str(e)}")
            return {
                'content': '',
                'content_length': 0,
                'extraction_score': 0,
                'word_count': 0
            }
    
    def _remove_unwanted_elements(self, soup: BeautifulSoup) -> None:
        """Remove unwanted HTML elements"""
        unwanted_selectors = [
            'script', 'style', 'nav', 'header', 'footer', 'aside',
            '.advertisement', '.ads', '.ad', '.sidebar', '.navigation',
            '.menu', '.footer', '.header', '.social', '.share',
            '.comments', '.comment', '.related', '.recommended',
            '.newsletter', '.subscribe', '.cookie', '.privacy',
            '[role="banner"]', '[role="navigation"]', '[role="complementary"]'
        ]
        
        for selector in unwanted_selectors:
            for element in soup.select(selector):
                element.decompose()
    
    def _extract_by_article_tag(self, soup: BeautifulSoup) -> Tuple[Optional[Tag], int]:
        """Extract content using article tag"""
        article = soup.find('article')
        if article:
            return article, 90  # High score for semantic HTML
        return None, 0
    
    def _extract_by_content_selectors(self, soup: BeautifulSoup) -> Tuple[Optional[Tag], int]:
        """Extract content using common content selectors"""
        content_selectors = [
            '.content', '.main-content', '.post-content', '.entry-content',
            '.article-content', '.story-content', '.text-content',
            '#content', '#main-content', '#post-content', '#entry-content',
            '.post', '.entry', '.story', '.article-body'
        ]
        
        for selector in content_selectors:
            element = soup.select_one(selector)
            if element:
                text_preview = element.get_text(separator='\n', strip=True)
                if len(text_preview) > 200:  # Minimum content length
                    return element, 80
        return None, 0
    
    def _extract_by_text_density(self, soup: BeautifulSoup) -> Tuple[Optional[Tag], int]:
        """Extract content by analyzing text density"""
        # Find elements with high text density
        elements = soup.find_all(['div', 'section', 'main'])
        
        best_element = None
        best_density = 0
        
        for element in elements:
            text_content = element.get_text(strip=True)
            html_content = str(element)
            
            if len(text_content) > 100:  # Minimum text length
                # Calculate text density (text length / HTML length)
                density = len(text_content) / len(html_content) if len(html_content) > 0 else 0
                
                if density > best_density:
                    best_density = density
                    best_element = element
        
        if best_element and best_density > 0.1:  # Minimum density threshold
            return best_element, int(best_density * 100)
        
        return None, 0
    
    def _extract_by_main_tag(self, soup: BeautifulSoup) -> Tuple[Optional[Tag], int]:
        """Extract content using main tag"""
        main = soup.find('main')
        if main:
            return main, 85
        return None, 0
    
    def _extract_by_body_fallback(self, soup: BeautifulSoup) -> Tuple[Optional[Tag], int]:
        """Fallback to body content"""
        body = soup.find('body')
        if body:
            return body, 50
        return None, 0
    
    def _sanitize_html_fragment(self, element: Optional[Tag]) -> str:
        """Create a sanitized HTML fragment keeping only allowed tags."""
        if not element:
            return ""
        
        sanitized_soup = BeautifulSoup('', 'html.parser')
        container = sanitized_soup.new_tag('div')
        sanitized_soup.append(container)
        
        def append_node(node, parent):
            if isinstance(node, NavigableString):
                text_value = str(node).strip()
                if not text_value:
                    return
                
                parent_name = getattr(parent, 'name', None)
                if parent_name in self.TEXT_CONTAINER_TAGS or parent_name in self.ALLOWED_INLINE_TAGS:
                    parent.append(text_value)
                else:
                    paragraph = sanitized_soup.new_tag('p')
                    paragraph.append(text_value)
                    parent.append(paragraph)
                return
            
            if not isinstance(node, Tag):
                return
            
            tag_name = node.name.lower()
            
            if tag_name in self.ALLOWED_BLOCK_TAGS or tag_name in self.ALLOWED_INLINE_TAGS:
                new_tag = sanitized_soup.new_tag(tag_name)
                
                if tag_name == 'a' and node.has_attr('href'):
                    new_tag['href'] = node['href']
                
                parent.append(new_tag)
                for child in node.children:
                    append_node(child, new_tag)
            elif tag_name in self.SELF_CLOSING_TAGS:
                parent.append(sanitized_soup.new_tag(tag_name))
            else:
                for child in node.children:
                    append_node(child, parent)
        
        for child in element.children:
            append_node(child, container)
        
        return container.decode_contents().strip()
    
    def extract_enhanced_metadata(self, html_content: str) -> Dict[str, Any]:
        """
        Extract enhanced metadata including publication dates and structured data
        
        Args:
            html_content: Raw HTML content
            
        Returns:
            Dictionary of enhanced metadata
        """
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            
            metadata = self.extract_basic_metadata(html_content)
            
            # Extract publication date
            pub_date = self._extract_publication_date(soup)
            if pub_date:
                metadata['publication_date'] = pub_date
            
            # Extract structured data (JSON-LD)
            structured_data = self._extract_structured_data(soup)
            if structured_data:
                metadata['structured_data'] = structured_data
            
            # Extract additional meta tags
            additional_meta = self._extract_additional_meta(soup)
            metadata.update(additional_meta)
            
            return metadata
            
        except Exception as e:
            logger.error(f"Error extracting enhanced metadata: {str(e)}")
            return metadata
    
    def _extract_publication_date(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract publication date from various meta tags"""
        date_selectors = [
            'meta[property="article:published_time"]',
            'meta[name="article:published_time"]',
            'meta[property="og:article:published_time"]',
            'meta[name="date"]',
            'meta[name="pubdate"]',
            'meta[name="publication_date"]',
            'time[datetime]'
        ]
        
        for selector in date_selectors:
            element = soup.select_one(selector)
            if element:
                date_value = element.get('content') or element.get('datetime')
                if date_value:
                    return date_value
        
        return None
    
    def _extract_structured_data(self, soup: BeautifulSoup) -> Optional[Dict]:
        """Extract JSON-LD structured data"""
        json_scripts = soup.find_all('script', type='application/ld+json')
        
        for script in json_scripts:
            try:
                import json
                data = json.loads(script.string)
                if isinstance(data, dict):
                    return data
                elif isinstance(data, list) and data:
                    return data[0]  # Return first item
            except (json.JSONDecodeError, AttributeError):
                continue
        
        return None
    
    def _extract_additional_meta(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """Extract additional meta information"""
        additional = {}
        
        # Extract canonical URL
        canonical = soup.find('link', rel='canonical')
        if canonical:
            additional['canonical_url'] = canonical.get('href')
        
        # Extract language
        html_tag = soup.find('html')
        if html_tag:
            lang = html_tag.get('lang')
            if lang:
                additional['language'] = lang
        
        # Extract viewport
        viewport = soup.find('meta', attrs={'name': 'viewport'})
        if viewport:
            additional['viewport'] = viewport.get('content')
        
        return additional


async def fetch_web_page(url: str, timeout: int = 30) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
    """
    Convenience function to fetch a web page
    
    Args:
        url: URL to fetch
        timeout: Request timeout in seconds
        
    Returns:
        Tuple of (success, html_content, metadata)
    """
    async with WebPageFetcher(timeout=timeout) as fetcher:
        return await fetcher.fetch_page(url)
