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


def _looks_like_undecoded_compression(text: str, sample_bytes: int = 4096) -> bool:
    """
    Return True when `text` looks like compressed bytes that were decoded as
    UTF-8 with errors='replace'. Symptom: a dense stream of U+FFFD characters
    in the first few KB. Normal HTML almost never exceeds ~0.1% replacement
    chars; compressed bodies decoded as text run well above 30%.
    """
    if not text:
        return False
    sample = text[:sample_bytes]
    if not sample:
        return False
    replacement_ratio = sample.count("\uFFFD") / len(sample)
    return replacement_ratio > 0.05


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
        """
        Get realistic browser headers optimized for content access.
        Uses Windows User-Agent with Google Referer to increase chances of
        accessing content behind paywalls or authentication.
        """
        return {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate, br',
            # Set Referer to Google to trick server into thinking you came from Google
            # This can help bypass paywalls that allow access from search engines
            'Referer': 'https://www.google.com/',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'cross-site',
            'Sec-Fetch-User': '?1',
            'Cache-Control': 'max-age=0',
        }
    
    @staticmethod
    def _get_googlebot_headers() -> Dict[str, str]:
        """
        Get Googlebot headers as fallback option.
        """
        return {
            'User-Agent': 'Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br, zstd',
            'Referer': 'https://www.google.com/',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'cross-site',
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
    
    @staticmethod
    def _detect_content_availability(
        html_content: str, 
        page_detection: Dict[str, Any], 
        has_js_placeholder: bool = False
    ) -> Dict[str, Any]:
        """
        Detect if content is fully available, partially available, or unavailable
        due to paywalls, authentication, or other restrictions.
        
        Args:
            html_content: The fetched HTML content
            page_detection: Page detection metadata from _detect_page_type
            has_js_placeholder: Whether JavaScript placeholder content was detected
            
        Returns:
            Dictionary with content availability status and detected issues
        """
        html_lower = html_content.lower()
        
        # Paywall indicators
        paywall_indicators = [
            'subscribe to continue reading',
            'subscribe now',
            'sign in to continue',
            'create an account to continue',
            'you have reached your article limit',
            'free articles remaining',
            'premium content',
            'members only',
            'paywall',
            'subscription required',
            'unlock this article',
            'become a member',
            'join to read',
            'this article is for subscribers only',
            'please log in to continue',
            'register to read',
        ]
        
        # Authentication/login indicators
        auth_indicators = [
            'please sign in',
            'log in to access',
            'sign in required',
            'authentication required',
            'please log in',
            'login to continue',
            'create account',
            'register to access',
            'you must be logged in',
        ]
        
        # Content blocked/restricted indicators
        blocked_indicators = [
            'access denied',
            'content not available',
            'this content is not available',
            'restricted content',
            'content blocked',
            'unavailable in your region',
            'geographic restrictions',
        ]
        
        # Check for paywall indicators
        paywall_detected = any(indicator in html_lower for indicator in paywall_indicators)
        
        # Check for authentication indicators
        auth_detected = any(indicator in html_lower for indicator in auth_indicators)
        
        # Check for blocked/restricted content
        blocked_detected = any(indicator in html_lower for indicator in blocked_indicators)
        
        # Analyze content length and structure
        # If content is very short, it might be a placeholder
        content_length = len(html_content.strip())
        is_short_content = content_length < 500
        
        # Try to extract text content to check if meaningful content exists
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            # Remove script and style tags
            for script in soup(["script", "style"]):
                script.decompose()
            text_content = soup.get_text(separator=' ', strip=True)
            text_length = len(text_content)
            is_short_text = text_length < 200
        except Exception:
            text_length = 0
            is_short_text = True
        
        # Determine content availability status
        issues = []
        if paywall_detected or page_detection.get('has_paywall'):
            issues.append('paywall')
        if auth_detected or page_detection.get('requires_login'):
            issues.append('authentication_required')
        if blocked_detected:
            issues.append('content_blocked')
        if page_detection.get('requires_js') and has_js_placeholder:
            issues.append('javascript_required')
        
        # Determine status
        if issues:
            # If we have issues but still got some content, it's partial
            if text_length > 200 and not is_short_text:
                content_status = 'partial'
            else:
                content_status = 'unavailable'
        elif is_short_text or is_short_content:
            # Content is too short, likely not meaningful
            content_status = 'partial'
            issues.append('insufficient_content')
        else:
            # Content appears to be available
            content_status = 'full'
        
        return {
            'status': content_status,  # 'full', 'partial', or 'unavailable'
            'issues': issues,
            'paywall_detected': paywall_detected,
            'authentication_required': auth_detected,
            'content_blocked': blocked_detected,
            'content_length': content_length,
            'text_length': text_length,
            'is_short_content': is_short_content,
            'is_short_text': is_short_text,
        }
    
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
    
    async def fetch_page(self, url: str, retry_with_browser: bool = True) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
        """
        Fetch web page content from URL with fallback to browser headers if Googlebot is blocked
        
        Args:
            url: URL to fetch
            retry_with_browser: If True, retry with regular browser headers if Googlebot fails with 403
            
        Returns:
            Tuple of (success, html_content, metadata)
        """
        try:
            logger.info(f"Fetching page: {url} (using Windows browser with Google Referer headers)")
            
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

            if _looks_like_undecoded_compression(html_content):
                encoding_header = response.headers.get('content-encoding', '<none>')
                logger.error(
                    f"Response body for {url} looks like undecoded compressed bytes "
                    f"(content-encoding={encoding_header}). Treating as fetch failure."
                )
                return False, None, {
                    'error': 'Compressed response not decoded',
                    'content_encoding': encoding_header,
                    'status_code': response.status_code,
                    'page_detection': page_detection,
                }

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
            
            # Detect paywall and authentication requirements from HTML content
            content_availability = WebPageFetcher._detect_content_availability(
                html_content, page_detection, has_js_placeholder
            )
            page_detection['content_availability'] = content_availability
            
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
            # If we get 403 and retry is enabled, try with Googlebot headers as fallback
            if e.response.status_code == 403 and retry_with_browser:
                logger.warning(f"Got 403 with browser headers for {url}, retrying with Googlebot headers")
                try:
                    # Close current client
                    await self.client.aclose()
                    # Create new client with Googlebot headers as fallback
                    self.client = httpx.AsyncClient(
                        timeout=self.timeout,
                        follow_redirects=True,
                        max_redirects=self.max_redirects,
                        headers=self._get_googlebot_headers()
                    )
                    # Retry the request
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

                    if _looks_like_undecoded_compression(html_content):
                        encoding_header = response.headers.get('content-encoding', '<none>')
                        logger.error(
                            f"Retry response body for {url} looks like undecoded "
                            f"compressed bytes (content-encoding={encoding_header}). "
                            f"Treating as fetch failure."
                        )
                        return False, None, {
                            'error': 'Compressed response not decoded',
                            'content_encoding': encoding_header,
                            'status_code': response.status_code,
                            'page_detection': page_detection,
                        }

                    # Check for JavaScript placeholder content
                    html_lower = html_content.lower()
                    has_js_placeholder = any(placeholder in html_lower for placeholder in [
                        'javascript is not available',
                        'please enable javascript',
                        'javascript is disabled',
                        'enable javascript to continue',
                        'noscript',
                    ])
                    
                    if has_js_placeholder and page_detection['requires_js']:
                        logger.warning(f"Detected JavaScript placeholder content for {url}. Content extraction will likely fail.")
                        page_detection['issues'].append('js_placeholder_detected')
                    
                    # Detect paywall and authentication requirements from HTML content
                    content_availability = WebPageFetcher._detect_content_availability(
                        html_content, page_detection, has_js_placeholder
                    )
                    page_detection['content_availability'] = content_availability
                    
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
                        'page_detection': page_detection,
                        'retried_with_googlebot': True
                    }
                    
                    logger.info(f"Successfully fetched {url} with Googlebot headers after browser headers were blocked ({len(html_content)} chars)")
                    if page_detection['warnings']:
                        logger.info(f"Page detection warnings: {', '.join(page_detection['warnings'])}")
                    
                    return True, html_content, metadata
                except Exception as retry_error:
                    logger.error(f"HTTP error fetching page with Googlebot headers: {url} - {retry_error}")
                    return False, None, {
                        'error': f'HTTP {e.response.status_code} (Browser headers blocked, Googlebot headers also failed)',
                        'status_code': e.response.status_code,
                        'retry_failed': True
                    }
            else:
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
