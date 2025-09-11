"""
Web page fetching service for retrieving HTML content from URLs
"""

import asyncio
from typing import Optional, Dict, Any, Tuple
from urllib.parse import urljoin, urlparse
import httpx
from bs4 import BeautifulSoup
import logging

from app.utils.logging import get_logger

logger = get_logger(__name__)


class WebPageFetcher:
    """Service for fetching web page content"""
    
    def __init__(self, timeout: int = 30, max_redirects: int = 5):
        self.timeout = timeout
        self.max_redirects = max_redirects
        self.client = None
    
    async def __aenter__(self):
        """Async context manager entry"""
        self.client = httpx.AsyncClient(
            timeout=self.timeout,
            follow_redirects=True,
            max_redirects=self.max_redirects,
            headers={
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
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
                    'status_code': response.status_code
                }
            
            # Get HTML content
            html_content = response.text
            
            # Basic validation
            if len(html_content.strip()) < 100:
                logger.warning(f"Page content too short: {len(html_content)} characters")
                return False, None, {
                    'error': 'Content too short',
                    'content_length': len(html_content),
                    'status_code': response.status_code
                }
            
            # Extract basic metadata
            metadata = {
                'status_code': response.status_code,
                'content_type': content_type,
                'content_length': len(html_content),
                'final_url': str(response.url),
                'headers': dict(response.headers)
            }
            
            logger.info(f"Successfully fetched page: {url} ({len(html_content)} chars)")
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
            
            best_content = None
            best_score = 0
            
            for strategy in content_strategies:
                try:
                    content, score = strategy(soup)
                    if content and score > best_score:
                        best_content = content
                        best_score = score
                except Exception as e:
                    logger.debug(f"Content extraction strategy failed: {str(e)}")
                    continue
            
            if not best_content:
                # Fallback to body content
                best_content = soup.find('body')
                if best_content:
                    best_content = best_content.get_text(separator='\n', strip=True)
                else:
                    best_content = soup.get_text(separator='\n', strip=True)
            
            # Clean and process the content
            cleaned_content = self._clean_text_content(best_content)
            
            return {
                'content': cleaned_content,
                'content_length': len(cleaned_content),
                'extraction_score': best_score,
                'word_count': len(cleaned_content.split())
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
    
    def _extract_by_article_tag(self, soup: BeautifulSoup) -> Tuple[Optional[str], int]:
        """Extract content using article tag"""
        article = soup.find('article')
        if article:
            content = article.get_text(separator='\n', strip=True)
            return content, 90  # High score for semantic HTML
        return None, 0
    
    def _extract_by_content_selectors(self, soup: BeautifulSoup) -> Tuple[Optional[str], int]:
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
                content = element.get_text(separator='\n', strip=True)
                if len(content) > 200:  # Minimum content length
                    return content, 80
        return None, 0
    
    def _extract_by_text_density(self, soup: BeautifulSoup) -> Tuple[Optional[str], int]:
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
            content = best_element.get_text(separator='\n', strip=True)
            return content, int(best_density * 100)
        
        return None, 0
    
    def _extract_by_main_tag(self, soup: BeautifulSoup) -> Tuple[Optional[str], int]:
        """Extract content using main tag"""
        main = soup.find('main')
        if main:
            content = main.get_text(separator='\n', strip=True)
            return content, 85
        return None, 0
    
    def _extract_by_body_fallback(self, soup: BeautifulSoup) -> Tuple[Optional[str], int]:
        """Fallback to body content"""
        body = soup.find('body')
        if body:
            content = body.get_text(separator='\n', strip=True)
            return content, 50
        return None, 0
    
    def _clean_text_content(self, content: str) -> str:
        """Clean and normalize text content"""
        if not content:
            return ""
        
        # Split into lines and clean each line
        lines = content.split('\n')
        cleaned_lines = []
        
        for line in lines:
            line = line.strip()
            # Skip empty lines and very short lines
            if line and len(line) > 3:
                cleaned_lines.append(line)
        
        # Join lines and normalize whitespace
        cleaned_content = '\n'.join(cleaned_lines)
        
        # Remove excessive whitespace
        import re
        cleaned_content = re.sub(r'\n\s*\n', '\n\n', cleaned_content)
        cleaned_content = re.sub(r'[ \t]+', ' ', cleaned_content)
        
        return cleaned_content.strip()
    
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
