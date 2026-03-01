"""
X.com (Twitter) API Service for fetching tweets and replies.
"""

import httpx
import re
import logging
from typing import Optional, List, Dict, Any
from app.core.config import settings

logger = logging.getLogger(__name__)

class XApiService:
    """Service to interact with X.com API v2"""

    def __init__(self):
        self.bearer_token = settings.X_BEARER_TOKEN
        self.base_url = "https://api.twitter.com/2"
        self.headers = {
            "Authorization": f"Bearer {self.bearer_token}",
            "User-Agent": "v2TweetLookupPython"
        }

    def extract_tweet_id(self, url: str) -> Optional[str]:
        """Extract tweet ID from URL"""
        # Supports x.com and twitter.com, with or without status/
        patterns = [
            r"status/(\d+)",
            r"x\.com/.+/(\d+)",
            r"twitter\.com/.+/(\d+)"
        ]
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return None

    async def get_tweet_details(self, tweet_id: str) -> Optional[Dict[str, Any]]:
        """Fetch details for a single tweet"""
        if not self.bearer_token:
            logger.error("X_BEARER_TOKEN not configured")
            return None

        url = f"{self.base_url}/tweets/{tweet_id}"
        params = {
            "tweet.fields": "author_id,conversation_id,created_at,public_metrics,text,attachments",
            "expansions": "author_id,attachments.media_keys",
            "user.fields": "name,username",
            "media.fields": "url,preview_image_url,type,alt_text"
        }

        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(url, headers=self.headers, params=params)
                response.raise_for_status()
                return response.json()
            except Exception as e:
                logger.error(f"Error fetching tweet {tweet_id}: {e}")
                return None

    async def get_replies(self, conversation_id: str, min_likes: int = 5) -> List[Dict[str, Any]]:
        """Search for replies in a conversation with minimum likes"""
        if not self.bearer_token:
            return []

        url = f"{self.base_url}/tweets/search/recent"
        # Query: conversation_id:ID -is:retweet
        # We fetch up to max_results and filter by min_likes locally
        # since min_likes/min_faves operator is not supported by standard API tiers.
        query = f"conversation_id:{conversation_id} -is:retweet"
        params = {
            "query": query,
            "tweet.fields": "author_id,created_at,public_metrics,text",
            "expansions": "author_id",
            "user.fields": "name,username",
            "max_results": 100
        }

        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(url, headers=self.headers, params=params)
                if response.status_code == 404:
                    return []
                response.raise_for_status()
                data = response.json()
                
                # Combine tweets with user info
                results = []
                tweets = data.get("data", [])
                users = {u["id"]: u for u in data.get("includes", {}).get("users", [])}
                
                for tweet in tweets:
                    likes = tweet["public_metrics"]["like_count"]
                    if likes >= min_likes:
                        author = users.get(tweet["author_id"], {"name": "Unknown", "username": "unknown"})
                        results.append({
                            "text": tweet["text"],
                            "author_name": author["name"],
                            "author_handle": author["username"],
                            "likes": likes
                        })
                
                # Sort by likes descending
                results.sort(key=lambda x: x["likes"], reverse=True)
                return results
            except Exception as e:
                logger.error(f"Error searching replies for conversation {conversation_id}: {e}")
                return []

    def get_media_urls(self, tweet_response: Dict[str, Any]) -> List[str]:
        """Extract image URLs from the Twitter API response includes.media array"""
        media_urls = []
        includes = tweet_response.get("includes", {})
        media_list = includes.get("media", [])
        
        for media in media_list:
            media_type = media.get("type", "")
            if media_type == "photo":
                # For photos, 'url' contains the full image URL
                url = media.get("url", "")
                if url:
                    media_urls.append(url)
            elif media_type in ("video", "animated_gif"):
                # For videos/GIFs, use the preview_image_url (thumbnail)
                preview = media.get("preview_image_url", "")
                if preview:
                    media_urls.append(preview)
        
        return media_urls

    def format_to_article(self, focal_tweet: Dict[str, Any], replies: List[Dict[str, Any]]) -> str:
        """Format the tweet data into an HTML article"""
        tweet_data = focal_tweet.get("data", {})
        includes = focal_tweet.get("includes", {})
        user = includes.get("users", [{}, {}])[0] if includes.get("users") else {}
        
        author_name = user.get("name", "Unknown")
        author_handle = user.get("username", "unknown")
        
        # Extract media URLs
        media_urls = self.get_media_urls(focal_tweet)
        
        html = [
            f'<article class="icognition-x-extraction">',
            f'<h1>X.com Thread ({1 + len(replies)} tweets)</h1>',
            f'<section class="focal-tweet-container">',
            f'<p><strong>Focal Tweet (by {author_name} @{author_handle}):</strong></p>',
            f'<p>{tweet_data.get("text", "")}</p>',
        ]
        
        # Add images if present
        if media_urls:
            html.append('<div class="tweet-media">')
            for img_url in media_urls:
                html.append(f'<img src="{img_url}" alt="Tweet image" />')
            html.append('</div>')
        
        html.append('</section>')
        html.append('<section class="replies-container">')
        html.append('<h2>Replies (Filtered by likes)</h2>')
        
        for reply in replies:
            html.append(f'<div class="reply-item">')
            html.append(f'<p><strong>Reply from {reply["author_name"]} @{reply["author_handle"]} ({reply["likes"]} likes):</strong></p>')
            html.append(f'<p>{reply["text"]}</p>')
            html.append(f'</div>')
            
        html.append('</section>')
        html.append('</article>')
        
        return "\n".join(html)

def get_x_api_service() -> XApiService:
    return XApiService()
