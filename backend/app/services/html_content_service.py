"""
Service for parsing HTML content and extracting metadata and structure.
Unified logic for both URL-fetched and raw HTML content.
"""

from typing import Optional, Dict, List, Any, Tuple
from bs4 import BeautifulSoup, Tag, NavigableString
import logging
from datetime import datetime
import re

from app.models import ContentExtraction
from app.utils.logging import get_logger
from app.utils.text_utils import extract_text_from_html

from app.utils.logging import get_logger
from app.utils.text_utils import extract_text_from_html
from app.services.gemini_service import get_gemini_service, GeminiModel, GeminiConfig
import json

logger = get_logger(__name__)


class HtmlContentService:
    """Service for parsing HTML content and extracting metadata"""
    
    ALLOWED_BLOCK_TAGS = {
        'p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'ul', 'ol', 'li', 'blockquote', 'pre', 'code'
    }
    ALLOWED_INLINE_TAGS = {'strong', 'em', 'b', 'i', 'u', 'a', 'span', 'br'}
    SELF_CLOSING_TAGS = {'br', 'hr', 'img'}
    TEXT_CONTAINER_TAGS = {'p', 'li', 'blockquote', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6'}

    async def extract_content(self, html_content: str, url: str = "") -> ContentExtraction:
        """
        Extract structured content and metadata from HTML.
        
        Args:
            html_content: Raw HTML string
            url: Source URL (used for page type detection)
            
        Returns:
            ContentExtraction object with parsed data
        """
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Find main content container
            main_container = self._find_main_content_container(soup)
            
            # Extract all fields
            title = self._extract_title(soup)
            author = self._extract_author(soup)
            publication_date = self._extract_date(soup)
            page_type = self._extract_page_type(soup, url)
            image_url = self._extract_image_url(soup)
            tags = self._extract_tags(soup)
            metadata = self._extract_metadata(soup)
            content = self._extract_content_text(soup, main_container, page_type)
            
            # Calculate confidence
            confidence = self._calculate_extraction_confidence(
                content, title, author, publication_date, image_url, tags, page_type
            )
            

            
            # If confidence is low, try LLM extraction
            if confidence < 0.6:
                logger.info(f"BeautifulSoup extraction confidence low ({confidence}), attempting LLM extraction")
                llm_result = await self._extract_with_llm(html_content)
                if llm_result and llm_result.extraction_confidence > confidence:
                    logger.info(f"LLM extraction successful with better confidence: {llm_result.extraction_confidence}")
                    return llm_result
            
            return ContentExtraction(
                page_type=page_type,
                title=title,
                content=content,
                author=author,
                publication_date=publication_date,
                tags=tags,
                metadata=metadata,
                extraction_confidence=confidence,
                extraction_notes="HtmlContentService extraction",
                image_url=image_url
            )
            
        except Exception as e:
            logger.error(f"Error in HTML content extraction: {str(e)}")
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
                extraction_notes=f"Extraction failed: {str(e)}",
                image_url=""
            )

    def _extract_title(self, soup: BeautifulSoup) -> str:
        """Extract title prioritizing OpenGraph tags"""
        # Improved priority order: OG > Twitter > Meta Title > H1 > Title tag
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
                    # For title/h1 elements, separate logic to handle children
                    title = element.get_text(separator=' ', strip=True)
                
                if title and len(title) > 0:
                    return title
        return ""

    def _extract_author(self, soup: BeautifulSoup) -> str:
        """Extract author using multiple strategies"""
        selectors = [
            'meta[name="author"]',
            'meta[property="article:author"]',
            'meta[property="og:article:author"]',
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
                    author = element.get_text(strip=True)
                
                if author and len(author) > 0:
                    return author
        return ""

    def _extract_date(self, soup: BeautifulSoup) -> str:
        """Extract publication date using multiple strategies"""
        selectors = [
            'meta[property="article:published_time"]',
            'meta[name="article:published_time"]',
            'meta[property="og:article:published_time"]',
            'meta[itemprop="datePublished"]',
            'time[datetime]',
            'time[pubdate]',
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

    def _extract_image_url(self, soup: BeautifulSoup) -> str:
        """Extract primary image URL prioritizing OpenGraph"""
        selectors = [
            'meta[property="og:image"]',
            'meta[name="twitter:image"]',
            'link[rel="image_src"]',
            'meta[itemprop="image"]'
        ]
        
        for selector in selectors:
            element = soup.select_one(selector)
            if element:
                if element.name == 'meta':
                    image_url = element.get('content', '').strip()
                elif element.name == 'link':
                    image_url = element.get('href', '').strip()
                else:
                    continue

                if image_url:
                    return image_url
        
        # Fallback: Find the first large image in body
        # This is a bit risky/heuristic, might be better to skip if no meta tags
        return ""

    def _extract_metadata(self, soup: BeautifulSoup) -> dict:
        """Extract additional metadata like description and site name"""
        metadata = {}
        
        # Site name
        site_name_selectors = [
            'meta[property="og:site_name"]',
            'meta[name="application-name"]'
        ]
        for selector in site_name_selectors:
            element = soup.select_one(selector)
            if element:
                site_name = element.get('content', '').strip()
                if site_name:
                    metadata['site_name'] = site_name
                    break
        
        # Description
        desc_selectors = [
            'meta[property="og:description"]',
            'meta[name="twitter:description"]',
            'meta[name="description"]'
        ]
        for selector in desc_selectors:
            element = soup.select_one(selector)
            if element:
                description = element.get('content', '').strip()
                if description:
                    metadata['description'] = description
                    break
        
        return metadata

    def _extract_tags(self, soup: BeautifulSoup) -> List[str]:
        """Extract tags/keywords"""
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
        
        return tags[:10]

    def _extract_page_type(self, soup: BeautifulSoup, url: str) -> str:
        """Detect page type from HTML and URL patterns"""
        # Check Open Graph type first
        og_type = soup.select_one('meta[property="og:type"]')
        if og_type:
            og_value = og_type.get('content', '').lower()
            if og_value == 'article':
                # Distinguish between news and blog based on site
                site_name = self._extract_metadata(soup).get('site_name', '')
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
        elif 'twitter.com' in url.lower() or 'x.com' in url.lower() or 'reddit.com' in url.lower() or ('substack.com' in url.lower() and '/note/' in url.lower()):
            return "social_media"
        elif 'medium.com' in url.lower():
            return "blog_post"
        
        return "other"

    def _find_main_content_container(self, soup: BeautifulSoup):
        """Find the main content container using semantic HTML5 and common patterns"""
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
                        return container
            except Exception:
                continue
        
        # Fallback to body if nothing found
        return soup.find('body') or soup

    def _extract_content_text(self, soup: BeautifulSoup, container, page_type: str) -> str:
        """Extract content from the main container, preserving HTML structure wrapped in tags"""
        if not container:
            return ""
        
        # Create a copy to avoid modifying the original soup if needed elsewhere
        import copy
        # We work on the container directly, but be careful not to destroy it if it's the soup itself
        # Ideally we clone it, but BeautifulSoup cloning can be slow. 
        # For now, we assume we can modify the soup as this is the last step.
        
        # Try JSON-LD first for known dynamic/schema-heavy platforms (like Substack Notes)
        # It's much cleaner than trying to parse JS-rendered DOM if it exists.
        json_ld_scripts = soup.find_all('script', type='application/ld+json')
        for script in json_ld_scripts:
            try:
                data = json.loads(script.string)
                # Handle both single objects and lists of objects
                if isinstance(data, dict):
                    objects = [data]
                elif isinstance(data, list):
                    objects = data
                else:
                    objects = []
                    
                for obj in objects:
                    if obj.get('@type') in ['SocialMediaPosting', 'DiscussionForumPosting'] or (obj.get('@type') in ['Article', 'NewsArticle', 'BlogPosting'] and page_type == 'social_media'):
                        text = obj.get('text') or obj.get('articleBody') or obj.get('description')
                        if text and len(text) > 50:
                            # Convert plain text with newlines to simple HTML paragraphs
                            paragraphs = text.split('\n\n')
                            html_text = ''.join(f'<p>{p.strip()}</p>' for p in paragraphs if p.strip())
                            if len(html_text) > 100:
                                return f"<article>{html_text}</article>"
            except Exception as e:
                logger.debug(f"JSON-LD parsing error: {e}")
                continue
        
        # Remove unwanted elements
        unwanted_selectors = [
            'script', 'style', 'nav', 'aside', 'noscript', 'iframe',
            'header:not(article header):not(main header)',
            'footer:not(article footer):not(main footer)',
            '[role="banner"]', '[role="navigation"]', '[role="complementary"]',
            '[class*="nav-"]', '[class*="menu-"]', '[class*="sidebar-"]',
            '.advertisement', '.ads', '.ad-banner', '.sponsored', '.promo',
            '.social-share', '.newsletter-signup', '.subscribe-box',
            '.cookie-notice', '.privacy-notice', '.cky-consent',
            '.related-posts', '.recommended-posts', '.recommended-articles'
        ]
        
        if page_type not in ['forum_post', 'social_media']:
            unwanted_selectors.extend(['.comments-section', '.comment-form', '[id^="comment-"]'])
        
        for selector in unwanted_selectors:
            for element in container.select(selector):
                element.decompose()
        
        # Extract content elements
        content_elements = container.select('h1, h2, h3, h4, h5, h6, p, ul, ol, blockquote, pre, code, img, picture, figure, figcaption')
        
        # Determine extraction length to decide on fallbacks
        extracted_text_len = len(''.join(e.get_text(strip=True) for e in content_elements)) if content_elements else 0

        # Fallback 2: Text accumulation if no semantic tags and JSON-LD failed
        if not content_elements or extracted_text_len < 200:
             text_parts = []
             seen_texts = set()
             for elem in container.find_all(['div', 'section', 'span', 'p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6']):
                 text = elem.get_text(strip=True)
                 if len(text) < 20: continue
                 if text in seen_texts: continue
                 
                 # Simple de-duplication
                 if not any(text in seen for seen in seen_texts):
                     text_parts.append(text)
                     seen_texts.add(text)
             
             if text_parts:
                 return f"<article>{''.join(f'<p>{p}</p>' for p in text_parts)}</article>"

        # Construct new article
        new_article = soup.new_tag('article')
        for element in content_elements:
            new_article.append(element)
            
        return str(new_article)

    def _calculate_extraction_confidence(
        self, content: str, title: str, author: str, 
        publication_date: str, image_url: str, tags: List[str], page_type: str
    ) -> float:
        """Calculate confidence score of extraction (0.0 to 1.0)"""
        score = 0.0
        
        # Content length check
        if len(content) > 500:
            score += 0.4
        elif len(content) > 100:
            score += 0.2
            
        # Metadata checks
        if title: score += 0.2
        if author: score += 0.1
        if publication_date: score += 0.1
        if tags: score += 0.1
        if image_url: score += 0.1
        
        return min(score, 1.0)

    async def _extract_with_llm(self, html_content: str) -> Optional[ContentExtraction]:
        """Extract content from HTML using Gemini Flash Lite LLM"""
        try:
            # Truncate content if too long for context window (approx 100k chars)
            # Flash Lite has large context but let's be safe and efficient
            truncated_content = html_content[:150000]
            
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
{truncated_content}

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
  "extraction_notes": "any_notes_or_empty_string",
  "image_url": "extracted_image_url_or_empty_string"
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
            try:
                response_data = json.loads(response['content'])
                
                # Ensure all fields are present for ContentExtraction
                if 'image_url' not in response_data:
                    response_data['image_url'] = ""
                if 'metadata' not in response_data:
                    response_data['metadata'] = {}
                if 'tags' not in response_data:
                    response_data['tags'] = []
                
                extraction_result = ContentExtraction(**response_data)
                # Mark as LLM extracted
                extraction_result.extraction_notes = f"LLM Extraction. {extraction_result.extraction_notes}"
                
                return extraction_result
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse JSON response from LLM: {e}")
                return None
            
        except Exception as e:
            logger.error(f"Error in LLM content extraction: {str(e)}")
            return None
