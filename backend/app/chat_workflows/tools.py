from typing import Optional
from urllib.parse import urlparse
from bs4 import BeautifulSoup
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_
from langchain_core.tools import Tool, tool
from app.core.config import settings
from app.models_kg import KGNode, KGEdge, KGNodeDocument
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

                result_parts.append(f"\\n{i}. **{doc.title}** (doc_id={doc.id})")
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


# Google CSE tools (get_google_search_tool, create_world_context_tool) were
# removed in Agent_Architecture_May_24. Web search now goes through Tavily —
# see app/chat_workflows/tavily_tools.py (get_tavily_search_tool, get_tavily_extract_tool).


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
            # 1. Find KG nodes matching the query
            node_result = await db_session.execute(
                select(KGNode)
                .where(
                    KGNode.user_id == user_id,
                    KGNode.label.ilike(f"%{query}%"),
                )
                .limit(10)
            )
            nodes = node_result.scalars().all()

            if not nodes:
                return f"No entities found matching '{query}' in your knowledge graph."

            node_ids = [n.id for n in nodes]
            node_map = {n.id: n for n in nodes}

            # 2. Find edges involving these nodes
            edge_result = await db_session.execute(
                select(KGEdge)
                .where(
                    or_(
                        KGEdge.from_node_id.in_(node_ids),
                        KGEdge.to_node_id.in_(node_ids),
                    )
                )
                .limit(50)
            )
            edges = edge_result.scalars().all()

            # 3. Collect all referenced node IDs not yet in node_map
            all_ids = set()
            for e in edges:
                all_ids.add(e.from_node_id)
                all_ids.add(e.to_node_id)
            missing_ids = all_ids - set(node_map.keys())

            if missing_ids:
                extra_result = await db_session.execute(
                    select(KGNode).where(KGNode.id.in_(missing_ids))
                )
                for n in extra_result.scalars().all():
                    node_map[n.id] = n

            # 4. Format output
            parts = [f"Knowledge graph results for '{query}':\n"]

            parts.append("**Entities:**")
            for n in nodes:
                desc = f" — {n.description}" if n.description else ""
                wiki = f" (wikidata:{n.wikidata_id})" if n.wikidata_id else ""
                parts.append(f"  • [{n.raw_type}] {n.label}{desc}{wiki}")

            if edges:
                parts.append("\n**Relationships:**")
                for e in edges:
                    from_n = node_map.get(e.from_node_id)
                    to_n = node_map.get(e.to_node_id)
                    if from_n and to_n:
                        parts.append(f"  • {from_n.label} --[{e.property_label}]--> {to_n.label}")
            else:
                parts.append("\nNo relationships found for these entities.")

            return "\n".join(parts)

        except Exception as e:
            logger.error(f"Error querying knowledge graph: {e}", exc_info=True)
            return f"Error querying knowledge graph: {str(e)}"

    return knowledge_graph_tool
