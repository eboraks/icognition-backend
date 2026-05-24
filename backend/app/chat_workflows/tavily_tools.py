"""
Tavily search and extract tools for the research agent.

Tavily provides a single API for both ranked search results and clean
content extraction, optimized for LLM consumption.
"""

import asyncio
from typing import Optional

from langchain_core.tools import tool
from tavily import TavilyClient

from app.core.config import settings
from app.utils.logging import get_logger

logger = get_logger(__name__)


def _get_client() -> Optional[TavilyClient]:
    if not settings.TAVILY_API_KEY:
        return None
    return TavilyClient(api_key=settings.TAVILY_API_KEY)


def get_tavily_search_tool():
    """
    Returns a Tavily search tool, or None if TAVILY_API_KEY is not configured.
    """
    client = _get_client()
    if client is None:
        logger.warning("TAVILY_API_KEY not set; tavily_search tool disabled")
        return None

    @tool
    async def tavily_search(query: str, topic: str = "general") -> str:
        """
        Search the web using Tavily for high-quality, ranked results.

        Args:
            query: Search query string.
            topic: "general" for broad search or "news" for fresh news articles.

        Returns:
            Formatted search results with titles, URLs, and snippets.
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
            results = response.get("results", [])
            if not results:
                return f"No Tavily results found for: {query}"

            # Format each result as a markdown link so the model can paste the
            # citation verbatim into its answer. The leading instruction is the
            # contract — bare [N] references won't render and the user will see
            # numbers without sources (the bug this format prevents).
            formatted = [
                "CITATION CONTRACT: When you use any of these results, cite "
                "them inline as the full markdown link [Title](URL) shown "
                "below. Never use bare [N] references — they won't render.",
                "",
            ]
            for r in results:
                title = (r.get("title") or "Untitled").strip().replace("]", ")").replace("[", "(")
                url = r.get("url") or ""
                snippet = (r.get("content") or "")[:400]
                formatted.append(f"- [{title}]({url})\n  {snippet}")

            return "\n".join(formatted)
        except Exception as e:
            logger.error(f"Tavily search failed for '{query}': {e}")
            return f"Error performing Tavily search: {str(e)}"

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
