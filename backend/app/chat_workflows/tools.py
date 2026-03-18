from typing import Optional
from urllib.parse import urlparse
from bs4 import BeautifulSoup
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_
from langchain_core.tools import Tool, tool
from langchain_google_community import GoogleSearchAPIWrapper
from app.core.config import settings
from app.models import Entity, EntityDocument, EntityRelationship
from app.services.document_service import DocumentService
from app.utils.logging import get_logger

logger = get_logger(__name__)

def strip_html_and_clean(text: str) -> str:
    """
    Strip HTML tags and clean up text for better readability.
    This helps prevent raw HTML from appearing in chat responses.
    """
    try:
        if not text:
            return ""
        soup = BeautifulSoup(text, "html.parser")
        cleaned = soup.get_text(separator=" ", strip=True)
        return " ".join(cleaned.split())
    except Exception as e:
        logger.warning(f"Error stripping HTML: {e}, returning original text")
        return text

def create_retrieve_documents_tool(user_id: str, scope_type: str, scope_id: Optional[int], db_session: AsyncSession):
    """
    Create a context-aware document retrieval tool for a specific chat session.
    """
    @tool
    async def retrieve_documents_tool(query: str) -> str:
        """
        Retrieves relevant documents from the user's library to answer a question.
        Use this tool when the user asks questions that might be answered by documents in their library.
        
        Args:
            query: The search query or question to find relevant documents for.
        
        Returns:
            A formatted string with relevant document titles and content snippets.
        """
        try:
            document_service = DocumentService(db_session)
            
            # Get relevant documents with matching chunks using vector search
            documents_with_chunks = await document_service.get_relevant_documents_with_chunks_for_chat(
                user_id=user_id,
                query=query,
                scope_type=scope_type,
                scope_id=scope_id,
                limit=5,
                similarity_threshold=0.55,
                chunks_per_document=5
            )
            
            if not documents_with_chunks:
                return f"No relevant documents found in your library for the query: '{query}'"
            
            result_parts = [f"Found {len(documents_with_chunks)} relevant document(s):"]
            
            for i, doc_data in enumerate(documents_with_chunks, 1):
                doc = doc_data['document']
                chunks = doc_data['chunks']
                best_score = doc_data['best_score']
                
                result_parts.append(f"\\n{i}. **{doc.title}**")
                if doc.url:
                    result_parts.append(f"   URL: {doc.url}")
                
                if chunks:
                    result_parts.append(f"   Matching Content (similarity: {best_score:.2f}):")
                    for j, chunk in enumerate(chunks, 1):
                        chunk_text = strip_html_and_clean(chunk['text'])
                        if len(chunk_text) > 1500:
                            chunk_text = chunk_text[:1500] + "... [chunk truncated]"
                        result_parts.append(f"   [{j}] {chunk_text}")
                        result_parts.append("")
                
                if doc.content:
                    cleaned_content = strip_html_and_clean(doc.content)
                    if len(cleaned_content) < 3000 or len(chunks) < 2:
                        if len(cleaned_content) > 2000:
                            cleaned_content = cleaned_content[:2000] + "... [content truncated]"
                        result_parts.append(f"   Full Document Content: {cleaned_content}")
                else:
                    result_parts.append("   [No full content available]")
            
            return "\\n".join(result_parts)
        except Exception as e:
            logger.error(f"Error retrieving documents: {e}", exc_info=True)
            return f"Error retrieving documents: {str(e)}"
    
    return retrieve_documents_tool

def get_google_search_tool():
    """
    Returns a configured Google Search Tool or None if credentials are missing.
    Results specifically include title, link, and snippet.
    """
    if not settings.GOOGLE_SEARCH_API or not settings.GOOGLE_CSE_ID:
        return None

    search = GoogleSearchAPIWrapper(
        google_api_key=settings.GOOGLE_SEARCH_API,
        google_cse_id=settings.GOOGLE_CSE_ID,
        k=5
    )

    @tool
    async def google_search_tool(query: str) -> str:
        """
        Searches Google for recent results to validate or augment document context.
        Use this tool to verify facts, statistics, dates, or any claims that need external validation.

        Args:
            query: The search query string to look up on Google.

        Returns:
            Formatted search results with titles, URLs, and snippets.
        """
        import asyncio
        try:
            results = await asyncio.to_thread(search.results, query, 5)
            if not results:
                return f"No Google search results found for: {query}"

            formatted = []
            for i, r in enumerate(results, 1):
                title = r.get("title", "No Title")
                link = r.get("link", "No Link")
                snippet = r.get("snippet", "No Snippet")
                formatted.append(f"[{i}] {title}\nURL: {link}\nSnippet: {snippet}")

            return "\n\n---\n\n".join(formatted)
        except Exception as e:
            return f"Error performing search: {str(e)}"

    return google_search_tool


def create_fetch_social_post_tool():
    """
    Create a tool that fetches a social media post or web page for context
    when writing social comments.
    """
    @tool
    async def fetch_social_post_tool(url: str) -> str:
        """
        Fetches the content of a social media post or web page to provide context for writing a comment.
        Use this tool when the user wants to write a comment on a social media post or article and provides a URL.

        Args:
            url: The URL of the social media post or web page to fetch.

        Returns:
            A structured summary of the post including platform, title, description, and content excerpt.
        """
        try:
            import httpx

            parsed = urlparse(url)
            hostname = parsed.hostname or ""

            if "twitter.com" in hostname or "x.com" in hostname:
                platform = "Twitter/X"
            elif "linkedin.com" in hostname:
                platform = "LinkedIn"
            elif "reddit.com" in hostname:
                platform = "Reddit"
            elif "facebook.com" in hostname or "fb.com" in hostname:
                platform = "Facebook"
            else:
                platform = "Web"

            headers = {"User-Agent": "Mozilla/5.0 (compatible; iCognition/1.0)"}
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
                response = await client.get(url, headers=headers)
                response.raise_for_status()
                html = response.text

            soup = BeautifulSoup(html, "html.parser")

            og_title = ""
            og_description = ""
            og_site_name = ""

            og_title_tag = soup.find("meta", property="og:title")
            if og_title_tag:
                og_title = og_title_tag.get("content", "")

            og_desc_tag = soup.find("meta", property="og:description")
            if og_desc_tag:
                og_description = og_desc_tag.get("content", "")

            og_site_tag = soup.find("meta", property="og:site_name")
            if og_site_tag:
                og_site_name = og_site_tag.get("content", "")

            if not og_title:
                title_tag = soup.find("title")
                if title_tag:
                    og_title = title_tag.get_text(strip=True)

            for tag in soup(["script", "style", "nav", "footer", "header"]):
                tag.decompose()

            main_content = soup.get_text(separator=" ", strip=True)
            main_content = " ".join(main_content.split())
            if len(main_content) > 2000:
                main_content = main_content[:2000] + "... [truncated]"

            parts = [f"Platform: {platform}", f"URL: {url}"]
            if og_site_name:
                parts.append(f"Site: {og_site_name}")
            if og_title:
                parts.append(f"Title: {og_title}")
            if og_description:
                parts.append(f"Description: {og_description}")
            if main_content:
                parts.append(f"Content Excerpt: {main_content}")

            return "\n".join(parts)

        except Exception as e:
            logger.error(f"Error fetching social post from {url}: {e}", exc_info=True)
            return f"Error fetching post from {url}: {str(e)}"

    return fetch_social_post_tool


def create_world_context_tool():
    """
    Create a tool that searches for recent news and current events about a topic.
    Returns None if Google Search credentials are not configured.
    """
    if not settings.GOOGLE_SEARCH_API or not settings.GOOGLE_CSE_ID:
        return None

    search = GoogleSearchAPIWrapper(
        google_api_key=settings.GOOGLE_SEARCH_API,
        google_cse_id=settings.GOOGLE_CSE_ID,
        k=5,
    )

    @tool
    async def world_context_tool(topic: str) -> str:
        """
        Searches for recent news and current events related to a topic.
        Use this tool when writing a comment on a post that touches on current events,
        geopolitics, breaking news, or any time-sensitive subject. Call it with the main
        topic extracted from the post to get recent context that enriches your comment.

        Args:
            topic: The topic or entity to search for recent news about
                   (e.g. "Israel Iran ceasefire", "OpenAI GPT-5 release", "US tariffs 2026").

        Returns:
            Recent news headlines, source URLs, and snippets about the topic.
        """
        import asyncio
        try:
            query = f"{topic} latest news"
            results = await asyncio.to_thread(search.results, query, 5)
            if not results:
                return f"No recent news found for: {topic}"

            formatted = []
            for i, r in enumerate(results, 1):
                title = r.get("title", "No Title")
                link = r.get("link", "No Link")
                snippet = r.get("snippet", "No Snippet")
                formatted.append(f"[{i}] {title}\nURL: {link}\nSnippet: {snippet}")

            return f"Recent news about '{topic}':\n\n" + "\n\n---\n\n".join(formatted)
        except Exception as e:
            logger.error(f"Error fetching world context for '{topic}': {e}", exc_info=True)
            return f"Error searching for world context: {str(e)}"

    return world_context_tool


def create_knowledge_graph_tool(user_id: str, db_session: AsyncSession):
    """
    Create a tool that queries the knowledge graph (entities + relationships)
    for entities relevant to the user's documents.
    """

    @tool
    async def knowledge_graph_tool(query: str) -> str:
        """
        Searches the knowledge graph for entities and their relationships extracted from the user's documents.
        Use this tool when the user asks about connections between people, organizations, topics, or concepts
        mentioned across their saved documents.

        Args:
            query: The entity name or topic to look up in the knowledge graph.

        Returns:
            A formatted description of matching entities and their relationships.
        """
        try:
            # 1. Find entities matching the query (name contains query, case-insensitive)
            entity_result = await db_session.execute(
                select(Entity)
                .join(EntityDocument, EntityDocument.entity_id == Entity.id)
                .where(
                    or_(
                        Entity.user_id == user_id,
                        Entity.user_id.is_(None),  # global entities
                    ),
                    Entity.name.ilike(f"%{query}%"),
                )
                .limit(10)
            )
            entities = entity_result.scalars().all()

            if not entities:
                return f"No entities found matching '{query}' in your knowledge graph."

            entity_ids = [e.id for e in entities]
            entity_map = {e.id: e for e in entities}

            # 2. Find relationships involving these entities
            rel_result = await db_session.execute(
                select(EntityRelationship)
                .where(
                    or_(
                        EntityRelationship.from_entity_id.in_(entity_ids),
                        EntityRelationship.to_entity_id.in_(entity_ids),
                    )
                )
                .limit(50)
            )
            relationships = rel_result.scalars().all()

            # 3. Collect all referenced entity IDs not yet in entity_map
            all_ids = set()
            for r in relationships:
                all_ids.add(r.from_entity_id)
                all_ids.add(r.to_entity_id)
            missing_ids = all_ids - set(entity_map.keys())

            if missing_ids:
                extra_result = await db_session.execute(
                    select(Entity).where(Entity.id.in_(missing_ids))
                )
                for e in extra_result.scalars().all():
                    entity_map[e.id] = e

            # 4. Format output
            parts = [f"Knowledge graph results for '{query}':\n"]

            parts.append("**Entities:**")
            for e in entities:
                desc = f" — {e.description}" if e.description else ""
                wiki = f" ({e.wikidata_url})" if e.wikidata_url else ""
                parts.append(f"  • [{e.type}] {e.name}{desc}{wiki}")

            if relationships:
                parts.append("\n**Relationships:**")
                for r in relationships:
                    from_e = entity_map.get(r.from_entity_id)
                    to_e = entity_map.get(r.to_entity_id)
                    if from_e and to_e:
                        parts.append(f"  • {from_e.name} --[{r.relationship_type}]--> {to_e.name}")
            else:
                parts.append("\nNo relationships found for these entities.")

            return "\n".join(parts)

        except Exception as e:
            logger.error(f"Error querying knowledge graph: {e}", exc_info=True)
            return f"Error querying knowledge graph: {str(e)}"

    return knowledge_graph_tool
