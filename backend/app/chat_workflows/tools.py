from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from langchain_core.tools import Tool, tool
from langchain_google_community import GoogleSearchAPIWrapper
from app.core.config import settings
from app.services.document_service import DocumentService
from app.utils.logging import get_logger

logger = get_logger(__name__)

def strip_html_and_clean(text: str) -> str:
    """
    Strip HTML tags and clean up text for better readability.
    This helps prevent raw HTML from appearing in chat responses.
    """
    try:
        from bs4 import BeautifulSoup
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

    def search_with_metadata(query: str) -> str:
        """Wrapper to include titles and links in search results."""
        try:
            results = search.results(query, num_results=5)
            if not results:
                return f"No Google search results found for: {query}"
            
            formatted = []
            for i, r in enumerate(results, 1):
                title = r.get("title", "No Title")
                link = r.get("link", "No Link")
                snippet = r.get("snippet", "No Snippet")
                formatted.append(f"[{i}] {title}\nURL: {link}\nSnippet: {snippet}\n")
            
            return "\\n---\\n".join(formatted)
        except Exception as e:
            return f"Error performing search: {str(e)}"

    return Tool(
        name="google_search_tool",
        description="Searches Google for recent results to validate or augment document context.",
        func=search_with_metadata,
    )
