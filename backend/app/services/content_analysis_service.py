"""
Content Analysis Service using LangGraph for robust document processing.
Replaces legacy simple summarization with a multi-agent workflow.
"""

import os
from typing import TypedDict, Optional, Dict, Any, List
from datetime import datetime
from pydantic import BaseModel, Field

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import StateGraph, END
from dotenv import load_dotenv

from app.models import LLMContentExtraction, PageType
from app.db.database import get_session
from app.services.prompt_service import PromptService
from app.services.prompt_utils import PromptType
from app.utils.logging import get_logger

# Load environment variables
load_dotenv()

logger = get_logger(__name__)

# --- State & Schema Definitions ---

class AgentState(TypedDict):
    content: str
    title: Optional[str]
    doc_type: Optional[PageType]
    extraction: Optional[LLMContentExtraction]

class DocTypeResult(BaseModel):
    """Result of document classification."""
    category: PageType = Field(
        description="The category of the document content"
    )
    reasoning: str = Field(description="Brief explanation for the classification")

# --- Service Class ---

class ContentAnalysisService:
    """
    Advanced content analysis service using LangGraph.
    Classifies documents and routes them to specialized extraction agents.
    """
    
    def __init__(self):
        self.api_key = os.getenv("GOOGLE_API_KEY")
        self.llm_model_name = os.getenv("GEMINI_FLASH_MODEL", "gemini-1.5-flash")
        
        if not self.api_key:
            logger.error("GOOGLE_API_KEY not found! Content analysis will fail.")
            
        self.llm = ChatGoogleGenerativeAI(model=self.llm_model_name, google_api_key=self.api_key)
        self.classifier_llm = self.llm.with_structured_output(DocTypeResult)
        self.extraction_llm = self.llm.with_structured_output(LLMContentExtraction)
        
        self.app = self._build_graph()
        logger.info("ContentAnalysisService (LangGraph) initialized")

    async def _get_db_prompt(self, prompt_type: str):
        """Helper to fetch prompts from the database."""
        async for session in get_session():
            service = PromptService(session)
            return await service.get_latest_prompt(prompt_type)
        return None

    # --- Node Functions ---

    async def _classify_doc(self, state: AgentState):
        logger.info("--- CLASSIFYING DOCUMENT ---")
        content = state["content"]
        title = state.get("title", "")
        
        categories = [e.value for e in PageType]
        
        system_prompt = f"You are an expert content classifier. Identify the type of document provided.\nAllowed categories: {', '.join(categories)}."
        user_template = "Title: {title}\n\nContent: {content}"

        # Try to load classifier prompt from DB
        db_prompt = await self._get_db_prompt("content_classifier") # Assuming a prompt type exists or fallback
        # Note: If 'content_classifier' isn't in PromptType enum, we might need to add it or use a default.
        # For now using hardcoded default above, but checking DB if available.
        # Ideally, we should add CLASSIFIER to PromptType enum. 
        # Using a generic fallback logic for now if specific type missing.
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            ("user", user_template)
        ])
        
        try:
             # Truncate content for classification to save tokens
            result = await self.classifier_llm.ainvoke(prompt.format(content=content[:5000], title=title))
            logger.info(f"Classified as: {result.category} ({result.reasoning})")
            return {"doc_type": result.category}
        except Exception as e:
             logger.error(f"Classification failed: {e}")
             # Default to generic if classification fails
             return {"doc_type": PageType.OTHER}

    async def _process_with_db_prompt(self, state: AgentState, prompt_type: str, agent_name: str):
        logger.info(f"--- PROCESSING AS {agent_name.upper()} ---")
        content = state["content"]
        title = state.get("title", "Untitled")
        
        db_prompt = await self._get_db_prompt(prompt_type)
        
        if db_prompt:
            system_prompt = db_prompt.system_prompt or f"You are an expert {agent_name} analyst."
            user_template = db_prompt.user_prompt
            try:
                user_prompt = user_template.format(content=content, title=title)
            except (KeyError, ValueError):
                user_prompt = f"{user_template}\n\nContent: {content}"
            
            prompt = ChatPromptTemplate.from_messages([
                ("system", system_prompt),
                ("user", user_prompt)
            ])
        else:
            # Fallback
            prompt = ChatPromptTemplate.from_messages([
                ("system", f"You are a {agent_name} analyst."),
                ("user", f"Summarize this content and extract key insights: {content}")
            ])
            
        result = await self.extraction_llm.ainvoke(prompt.format())
        result.agent_name = f"{agent_name}Agent"
        return {"extraction": result}

    # Wrapper functions for the graph
    async def _process_news(self, state: AgentState):
        return await self._process_with_db_prompt(state, PromptType.EXTRACT_NEWS.value, "News")

    async def _process_blog(self, state: AgentState):
        return await self._process_with_db_prompt(state, PromptType.EXTRACT_BLOG.value, "Blog")

    async def _process_product_doc(self, state: AgentState):
        return await self._process_with_db_prompt(state, PromptType.EXTRACT_PRODUCT.value, "ProductDoc")

    async def _process_social_media(self, state: AgentState):
        return await self._process_with_db_prompt(state, PromptType.EXTRACT_SOCIAL.value, "SocialMedia")

    async def _process_marketing(self, state: AgentState):
        return await self._process_with_db_prompt(state, PromptType.EXTRACT_MARKETING.value, "Marketing")

    async def _process_book(self, state: AgentState):
        return await self._process_with_db_prompt(state, PromptType.EXTRACT_BOOK.value, "Book")

    async def _process_generic(self, state: AgentState):
        return await self._process_with_db_prompt(state, PromptType.EXTRACT_GENERIC.value, "Generic")

    # --- Graph Building ---

    def _route_by_type(self, state: AgentState):
        doc_type = state["doc_type"]
        
        if doc_type == PageType.NEWS_ARTICLE:
            return "news"
        elif doc_type == PageType.BLOG_POST:
            return "blog"
        elif doc_type == PageType.SOCIAL_MEDIA:
            return "social_media"
        elif doc_type in [PageType.PRODUCT_PAGE, PageType.DOCUMENTATION]:
            return "product_doc"
        elif doc_type == PageType.LANDING_PAGE:
            return "marketing"
        elif doc_type == PageType.OTHER:
            return "generic"
        else:
            return "generic"

    def _build_graph(self):
        workflow = StateGraph(AgentState)

        # Add nodes
        workflow.add_node("classifier", self._classify_doc)
        workflow.add_node("news_processor", self._process_news)
        workflow.add_node("blog_processor", self._process_blog)
        workflow.add_node("social_media_processor", self._process_social_media)
        workflow.add_node("product_doc_processor", self._process_product_doc)
        workflow.add_node("marketing_processor", self._process_marketing)
        workflow.add_node("book_processor", self._process_book)
        workflow.add_node("generic_processor", self._process_generic)

        # Define edges
        workflow.set_entry_point("classifier")
        
        workflow.add_conditional_edges(
            "classifier",
            self._route_by_type,
            {
                "news": "news_processor",
                "blog": "blog_processor",
                "social_media": "social_media_processor",
                "product_doc": "product_doc_processor",
                "marketing": "marketing_processor",
                "book": "book_processor",
                "generic": "generic_processor"
            }
        )

        workflow.add_edge("news_processor", END)
        workflow.add_edge("blog_processor", END)
        workflow.add_edge("social_media_processor", END)
        workflow.add_edge("product_doc_processor", END)
        workflow.add_edge("marketing_processor", END)
        workflow.add_edge("book_processor", END)
        workflow.add_edge("generic_processor", END)

        return workflow.compile()

    # --- Public API ---

    async def analyze_document_content(
        self,
        content: str,
        title: Optional[str] = None,
        url: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Analyze document using the LangGraph workflow.
        
        Returns:
            Dict containing 'summary', 'bullet_points', 'analysis_timestamp', etc.
        """
        if not content or not content.strip():
            raise ValueError("Content cannot be empty")
            
        logger.info(f"Starting LangGraph content analysis for: {title or 'Untitled'}")
        
        inputs = {"content": content, "title": title}
        final_result = None
        
        # Invoke the graph
        try:
             # Use ainvoke for async execution
            result = await self.app.ainvoke(inputs)
            
            if "extraction" in result and result["extraction"]:
                ext = result["extraction"]
                final_result = {
                    "summary": ext.summary,
                    "bullet_points": ext.bullet_points,
                    "agent_name": ext.agent_name,
                    "analysis_timestamp": datetime.utcnow(),
                    "content_length": len(content),
                    "title": title,
                    "url": url
                }
            else:
                # Fallback if something went wrong in the graph
                logger.warning("Graph completed but no extraction found.")
                final_result = {
                    "summary": "Analysis failed to produce structured output.",
                    "bullet_points": [],
                    "analysis_timestamp": datetime.utcnow()
                }
                
        except Exception as e:
            logger.error(f"Error in LangGraph execution: {e}")
            raise

        logger.info(f"Analysis completed successfully by {final_result.get('agent_name', 'Unknown')}")
        return final_result

# Global service instance
_content_analysis_service: Optional[ContentAnalysisService] = None

def get_content_analysis_service() -> ContentAnalysisService:
    """Get the global content analysis service instance"""
    global _content_analysis_service
    if _content_analysis_service is None:
        _content_analysis_service = ContentAnalysisService()
    return _content_analysis_service

def initialize_content_analysis_service() -> ContentAnalysisService:
    """Initialize the global content analysis service instance"""
    global _content_analysis_service
    _content_analysis_service = ContentAnalysisService()
    return _content_analysis_service