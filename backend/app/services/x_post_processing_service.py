import os
import json
import base64
import httpx
from typing import TypedDict, Optional, Dict, Any, List
from datetime import datetime
from pydantic import BaseModel, Field

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import StateGraph, END
from dotenv import load_dotenv

from app.models import LLMContentExtraction
from app.db.database import get_session
from app.services.prompt_service import PromptService
from app.utils.logging import get_logger
from app.utils.langfuse_worker import get_langfuse_handler
from app.services.image_analysis_service import get_image_analysis_service

load_dotenv()
logger = get_logger(__name__)

# --- State & Schema Definitions ---

class XPostState(TypedDict):
    content: str  # Raw HTML/Text content of the tweet
    title: Optional[str]
    url: Optional[str]
    
    focal_tweet: str
    replies: List[str]
    
    image_urls: List[str]  # URLs of images attached to the tweet
    image_descriptions: List[str]  # LLM-generated descriptions of tweet images
    
    post_analysis: Optional[Dict[str, Any]]
    reply_categories: Optional[Dict[str, Any]]
    
    extraction: Optional[LLMContentExtraction]


class XPostAnalysis(BaseModel):
    """Result of analyzing the focal tweet."""
    summary: str = Field(description="A neutral, informative summary of the main tweet (one short paragraph)")
    bias: str = Field(description="Any identified biases in the tweet")
    agenda: str = Field(description="The perceived agenda or intent of the author")
    informativeness: str = Field(description="How informative the tweet is (e.g., highly informative, opinionated, spam)")
    objectivity: str = Field(description="The objectivity of the tweet (e.g., Objective, Subjective (Opinion), Promotional)")

class XReplyCategories(BaseModel):
    """Categorized replies for an X Post"""
    supportive: List[str] = Field(description="Key bullet points summarizing replies that support the focal tweet")
    dissenting: List[str] = Field(description="Key bullet points summarizing replies that disagree or argue against the focal tweet")
    adding_context: List[str] = Field(description="Key bullet points summarizing replies that add new context or information")
    unrelated: List[str] = Field(description="Brief summary of unrelated or spam replies, if any")

# --- Service Class ---

class XPostProcessingService:
    """
    Advanced content analysis service using LangGraph, specifically for X/Twitter posts.
    Breaks down a focal tweet and categorizes its replies.
    """
    
    def __init__(self):
        self.api_key = os.getenv("GOOGLE_API_KEY")
        self.llm_model_name = os.getenv("GEMINI_FLASH_MODEL", "gemini-1.5-flash")
        
        if not self.api_key:
            logger.error("GOOGLE_API_KEY not found! X Post analysis will fail.")
            
        self.llm = ChatGoogleGenerativeAI(model=self.llm_model_name, google_api_key=self.api_key)
        self.analyzer_llm = self.llm.with_structured_output(XPostAnalysis)
        self.categorizer_llm = self.llm.with_structured_output(XReplyCategories)
        self.final_llm = self.llm.with_structured_output(LLMContentExtraction)
        
        self.app = self._build_graph()
        logger.info("XPostProcessingService (LangGraph) initialized")

    async def _get_db_prompt(self, prompt_type: str) -> Optional[str]:
        """Helper to fetch prompts from the database."""
        async for session in get_session():
            service = PromptService(session)
            db_prompt = await service.get_latest_prompt(prompt_type)
            if db_prompt:
                instructions = ""
                if db_prompt.system_prompt:
                    instructions += db_prompt.system_prompt + "\n\n"
                instructions += db_prompt.user_prompt
                return instructions
        return None

    # --- Node Functions ---

    async def _parse_content(self, state: XPostState):
        """Extract the focal tweet and replies from the raw content string"""
        logger.info("--- PARSING X POST CONTENT ---")
        content = state["content"]
        
        focal_tweet = ""
        replies = []
        new_title = state.get("title")
        
        try:
            # Extract author for a better title if the current title is generic like "Home / X"
            import re
            if new_title == "Home / X" or not new_title:
                # Look for "Focal Tweet (by Author Name @handle)"
                match = re.search(r"Focal Tweet \(by (.*?)\):", content)
                if match:
                    new_title = f"X Post by {match.group(1)}"
                else:
                    new_title = "X Post"
                    
            focal_tweet = content
            replies = [] 
        except Exception as e:
            logger.error(f"Error parsing X content: {e}")
            focal_tweet = content
            
        return {
            "focal_tweet": focal_tweet,
            "replies": replies,
            "title": new_title,
            "image_urls": state.get("image_urls", []),
            "image_descriptions": []
        }

    async def _analyze_images(self, state: XPostState):
        """Download tweet images and analyze them with Gemini multimodal"""
        image_urls = state.get("image_urls", [])
        
        if not image_urls:
            logger.info("--- NO IMAGES TO ANALYZE ---")
            return {"image_descriptions": []}
        
        logger.info(f"--- ANALYZING {len(image_urls)} IMAGES ---")
        
        image_service = get_image_analysis_service()
        results_map = await image_service.analyze_images(image_urls)
        
        descriptions = []
        for img_url in image_urls:
            desc = results_map.get(img_url)
            if desc:
                descriptions.append(desc)
            else:
                descriptions.append(f"[Image could not be analyzed: {img_url}]")
        
        return {"image_descriptions": descriptions}

    async def _analyze_post(self, state: XPostState):
        logger.info("--- ANALYZING FOCAL TWEET ---")
        focal_tweet = state.get("focal_tweet", "")
        image_descriptions = state.get("image_descriptions", [])
        
        # Build image context if we have descriptions
        image_context = ""
        if image_descriptions:
            image_context = "\n\nImages attached to this tweet:\n"
            for i, desc in enumerate(image_descriptions, 1):
                image_context += f"Image {i}: {desc}\n"

        system_prompt = "You are an expert social media analyst. Analyze the provided X (Twitter) post." + (
            " The post includes attached images whose descriptions are provided." if image_descriptions else ""
        )
        user_template = "Content:\n{content}" + (
            "\n\nAttached Image Descriptions:\n{image_context}" if image_descriptions else ""
        ) + "\n\nExtract the summary, bias, agenda, informativeness, and objectivity."

        db_prompt = await self._get_db_prompt("x_post_analyzer")
        
        if db_prompt:
            prompt = ChatPromptTemplate.from_template(db_prompt)
        else:
            prompt = ChatPromptTemplate.from_messages([
                ("system", system_prompt),
                ("user", user_template)
            ])
            
        try:
            lf_handler = get_langfuse_handler()
            callbacks = [lf_handler] if lf_handler else []

            chain = prompt | self.analyzer_llm
            invoke_params = {"content": focal_tweet}
            if image_descriptions:
                invoke_params["image_context"] = image_context
            
            result = await chain.ainvoke(
                invoke_params,
                config={"callbacks": callbacks}
            )
            
            # Convert BaseModel to dict
            analysis_dict = result.model_dump() if result else None
            return {"post_analysis": analysis_dict}
            
        except Exception as e:
            logger.error(f"Error in analyze_post: {e}")
            return {"post_analysis": None}

    async def _categorize_replies(self, state: XPostState):
        logger.info("--- CATEGORIZING REPLIES ---")
        focal_tweet = state.get("focal_tweet", "")
        post_analysis = state.get("post_analysis", {})
        
        # If there's no replies or content is too short, we can skip or return empty
        
        system_prompt = "You are an expert community manager. Read the X (Twitter) thread and categorize the replies."
        user_template = "Context Post Summary: {summary}\n\nThread Content:\n{content}\n\nCategorize the prevailing sentiments in the replies."

        db_prompt = await self._get_db_prompt("x_reply_categorizer")
        
        if db_prompt:
            prompt = ChatPromptTemplate.from_template(db_prompt)
        else:
            prompt = ChatPromptTemplate.from_messages([
                ("system", system_prompt),
                ("user", user_template)
            ])
            
        try:
            lf_handler = get_langfuse_handler()
            callbacks = [lf_handler] if lf_handler else []

            chain = prompt | self.categorizer_llm
            summary = post_analysis.get("summary", "") if post_analysis else ""
            
            result = await chain.ainvoke(
                {"summary": summary, "content": focal_tweet},
                config={"callbacks": callbacks}
            )
            
            categories_dict = result.model_dump() if result else None
            return {"reply_categories": categories_dict}
            
        except Exception as e:
            logger.error(f"Error in categorize_replies: {e}")
            return {"reply_categories": None}

    async def _generate_final_response(self, state: XPostState):
        logger.info("--- GENERATING FINAL EXTRACTION ---")
        
        post_analysis = state.get("post_analysis") or {}
        reply_categories = state.get("reply_categories") or {}
        image_descriptions = state.get("image_descriptions", [])
        title = state.get("title", "X Post")
        url = state.get("url", "")
        
        # Build image context for final synthesis
        image_section = ""
        if image_descriptions:
            image_section = "\nImage Descriptions:\n"
            for i, desc in enumerate(image_descriptions, 1):
                image_section += f"  Image {i}: {desc}\n"
        
        system_prompt = "You are a master content synthesizer. Create the final structured JSON object matching the LLMContentExtraction schema."
        user_template = """
        Analyze the following context regarding an X post:
        
        Post Analysis: {post_analysis}
        Reply Categories: {reply_categories}
        {image_section}
        
        Synthesize this into a cohesive summary. Ensure the markdown_content captures both the focal tweet's point and the community's reaction in a detailed markdown format. 
        If images are present, include a description of the visual content and how it relates to the tweet's message.
        
        CRITICAL: Do not include boilerplate headers in the markdown_content like "Content Extraction Report", "Content Synthesis", "Source Type", "Title", or "URL". Just output the actual synthesized analysis directly.
        """

        db_prompt = await self._get_db_prompt("x_final_compiler")
        if db_prompt:
            prompt = ChatPromptTemplate.from_template(db_prompt)
        else:
            prompt = ChatPromptTemplate.from_messages([
                ("system", system_prompt),
                ("user", user_template)
            ])

        try:
            lf_handler = get_langfuse_handler()
            callbacks = [lf_handler] if lf_handler else []

            chain = prompt | self.final_llm
            result = await chain.ainvoke(
                {
                    "title": title,
                    "url": url,
                    "post_analysis": json.dumps(post_analysis),
                    "reply_categories": json.dumps(reply_categories),
                    "image_section": image_section
                },
                config={"callbacks": callbacks}
            )
            
            return {"extraction": result}
            
        except Exception as e:
            logger.error(f"Error in generate_final_response: {e}")
            return {"extraction": None}

    # --- Graph Construction ---

    def _build_graph(self) -> Any:
        workflow = StateGraph(XPostState)

        # Add nodes
        workflow.add_node("parse_content", self._parse_content)
        workflow.add_node("analyze_images", self._analyze_images)
        workflow.add_node("analyze_post", self._analyze_post)
        workflow.add_node("categorize_replies", self._categorize_replies)
        workflow.add_node("generate_final_response", self._generate_final_response)

        # Set edges - images analyzed in parallel with post parsing
        workflow.set_entry_point("parse_content")
        workflow.add_edge("parse_content", "analyze_images")
        workflow.add_edge("analyze_images", "analyze_post")
        workflow.add_edge("analyze_post", "categorize_replies")
        workflow.add_edge("categorize_replies", "generate_final_response")
        workflow.add_edge("generate_final_response", END)

        return workflow.compile()

    # --- Public API ---

    async def analyze_x_post(self, content: str, title: Optional[str] = None, url: Optional[str] = None, image_urls: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Main entry point for processing an X post.
        Returns a dictionary compatible with the DspyContentService output format.
        """
        logger.info(f"Starting LangGraph X Post analysis for: {url}")
        
        initial_state = {
            "content": content,
            "title": title,
            "url": url,
            "image_urls": image_urls or [],
            "image_descriptions": []
        }
        
        try:
            # Run the graph
            final_state = await self.app.ainvoke(initial_state)
            extraction: Optional[LLMContentExtraction] = final_state.get("extraction")
            
            if not extraction:
                logger.error("Failed to generate X Post extraction")
                raise ValueError("Extraction yielded None")
                
            post_analysis = final_state.get("post_analysis", {})
                
            result = {
                'summary': None,
                'markdown_content': extraction.markdown_content,
                'extracted_content': {
                    'title': title,
                    'source_type': "Social Media Post",
                    'summary': None,
                    'markdown_content': extraction.markdown_content,
                    'analysis': {
                        'objectivity': post_analysis.get('objectivity', 'Unknown') if post_analysis else "Unknown",
                        'tone': "Unknown",
                        'intent': post_analysis.get('agenda', 'Unknown') if post_analysis else "Unknown"
                    },
                    'access_notes': "Public X post string extraction.",
                    'extraction_timestamp': datetime.utcnow().isoformat(),
                    'model': self.llm_model_name
                },
                'analysis_timestamp': datetime.utcnow(),
                'content_length': len(content),
                'title': title,
                'url': url
            }
            
            logger.info(f"X Post analysis completed successfully for: {url}")
            return result
            
        except Exception as e:
            logger.error(f"Error executing X Post LangGraph: {e}")
            raise

# Global service instance
_x_post_processing_service: Optional[XPostProcessingService] = None

def get_x_post_processing_service() -> XPostProcessingService:
    """Get the global XPostProcessingService instance"""
    global _x_post_processing_service
    if _x_post_processing_service is None:
        _x_post_processing_service = XPostProcessingService()
    return _x_post_processing_service
