"""
Tavily search and extract tools for the research agent.

Tavily provides a single API for both ranked search results and clean
content extraction, optimized for LLM consumption.
"""

import asyncio
import hashlib
import re
from typing import Any, Optional, Tuple
from urllib.parse import urlparse

from langchain_core.tools import tool
from tavily import TavilyClient

from app.core.config import settings
from app.utils.logging import get_logger

logger = get_logger(__name__)


def _get_client() -> Optional[TavilyClient]:
    if not settings.TAVILY_API_KEY:
        return None
    return TavilyClient(api_key=settings.TAVILY_API_KEY)


def _domain_of(url: str) -> str:
    """Extract a short hostname for the citation chip label (e.g. 'en.wikipedia.org')."""
    try:
        host = urlparse(url).hostname or ""
        return host[4:] if host.startswith("www.") else host
    except Exception:
        return ""


def _slugify(text: str, n: int = 24) -> str:
    """Lowercase ASCII slug for use inside a cite ID. Stable across reruns."""
    text = (text or "").lower()
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text[:n] or "q"


def get_tavily_search_tool():
    """
    Returns a Tavily search tool, or None if TAVILY_API_KEY is not configured.

    The tool uses `response_format="content_and_artifact"`. The string content
    is what the LLM sees (with citation markers); the artifact is a dict of
    cite_id → {title, url, domain, snippet} that the route reads off the
    resulting ToolMessage and ships to the client in the `done` event.
    """
    client = _get_client()
    if client is None:
        logger.warning("TAVILY_API_KEY not set; tavily_search tool disabled")
        return None

    @tool(response_format="content_and_artifact")
    async def tavily_search(query: str, topic: str = "general") -> Tuple[str, Any]:
        """
        Search the web using Tavily for high-quality, ranked results.

        Cite each result you use in your answer with the marker tag
        `<source web_id="cite-..."/>` placed immediately after the relevant
        sentence (the chat UI renders these as inline source chips). Do NOT
        inline the URL as markdown — the chip carries the link.

        Args:
            query: Search query string.
            topic: "general" for broad search or "news" for fresh news articles.
        """
        try:
            def _search():
                return client.search(
                    query=query,
                    search_depth="advanced",
                    topic=topic if topic in ("general", "news") else "general",
                    max_results=5,
                    include_answer=False,
                )

            response = await asyncio.to_thread(_search)
            results = response.get("results", []) or []
            if not results:
                return (f"No Tavily results found for: {query}", {})

            # Build a stable cite_id per result so reruns of the same query
            # produce the same IDs — useful for debugging Langfuse traces.
            query_slug = _slugify(query)
            citations: dict = {}

            lines = [
                "CITATION CONTRACT: After each claim you make from a result "
                "below, append the marker `<source web_id=\"cite-...\"/>` "
                "using the cite_id shown for that result. Do NOT inline the "
                "URL or use bare [N] references — the chat UI renders the "
                "marker as an inline source chip with the link.",
                "",
            ]
            for idx, r in enumerate(results, 1):
                url = (r.get("url") or "").strip()
                title = (r.get("title") or "Untitled").strip()
                snippet = (r.get("content") or "")[:400]
                domain = _domain_of(url)
                # cite_id format: cite-<query-slug>-<index>. Stable + readable
                # enough to debug from a trace, but short enough not to spam
                # the prompt.
                cite_id = f"cite-{query_slug}-{idx}"
                citations[cite_id] = {
                    "id": cite_id,
                    "title": title,
                    "url": url,
                    "domain": domain,
                    "snippet": snippet,
                }
                # Keep the human-readable line free of markdown link syntax
                # so the model isn't tempted to inline the URL itself.
                lines.append(
                    f"- cite_id={cite_id} — {title} ({domain})\n  {snippet}"
                )

            return ("\n".join(lines), citations)
        except Exception as e:
            logger.error(f"Tavily search failed for '{query}': {e}")
            return (f"Error performing Tavily search: {str(e)}", {})

    return tavily_search


def get_tavily_extract_tool():
    """
    Returns a Tavily extract tool, or None if TAVILY_API_KEY is not configured.
    """
    client = _get_client()
    if client is None:
        logger.warning("TAVILY_API_KEY not set; tavily_extract tool disabled")
        return None

    @tool
    async def tavily_extract(url: str) -> str:
        """
        Extract clean markdown content from a single URL using Tavily.

        Args:
            url: The URL to extract content from.

        Returns:
            Cleaned markdown content (truncated to ~3000 characters).
        """
        try:
            def _extract():
                return client.extract(urls=[url], extract_depth="advanced")

            response = await asyncio.to_thread(_extract)
            results = response.get("results", [])
            if not results:
                return f"Tavily extract returned no content for: {url}"

            content = results[0].get("raw_content") or results[0].get("content") or ""
            if not content:
                return f"Tavily extract returned empty content for: {url}"

            # Truncate to keep LLM context manageable
            if len(content) > 3000:
                content = content[:3000] + "\n\n[... truncated ...]"

            return content
        except Exception as e:
            logger.error(f"Tavily extract failed for '{url}': {e}")
            return f"Error extracting from {url}: {str(e)}"

    return tavily_extract
