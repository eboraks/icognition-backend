"""
Research sub-agent: a small ReAct loop that researches a single sub-topic.

Each sub-agent runs in parallel as part of the research multi-agent workflow.
It uses Tavily for search and extract, and saves worthwhile findings as
Document rows linked to the parent ResearchSession.
"""

from typing import Any, Dict, List, Optional

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from langchain_google_genai import ChatGoogleGenerativeAI
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.chat_workflows.tavily_tools import get_tavily_search_tool, get_tavily_extract_tool
from app.services.document_service import DocumentService
from app.services.prompt_service import get_prompt
from app.services.prompt_utils import PromptType
from app.utils.logging import get_logger

logger = get_logger(__name__)

# Hard caps for v1
MAX_DOCS_PER_SUBAGENT = 3


def _make_save_research_document_tool(
    db_session: AsyncSession,
    user_id: str,
    research_session_id: int,
    saved_doc_ids: List[int],
):
    """
    Build a `save_research_document` tool that closes over the sub-agent's state
    so it can persist documents during the tool-call loop.
    """

    @tool
    async def save_research_document(url: str, title: str = "") -> str:
        """
        Save a worthwhile research finding as a permanent Document in the user's library.
        The document will be linked to the current research session and processed by
        the existing KG extraction and theme assignment pipelines.

        Args:
            url: The URL of the source to save.
            title: Optional title hint (will be overridden by extraction if present).

        Returns:
            Confirmation with document ID, or error message.
        """
        # Per-subagent cap
        if len(saved_doc_ids) >= MAX_DOCS_PER_SUBAGENT:
            return f"Document save limit reached ({MAX_DOCS_PER_SUBAGENT} per sub-agent)"

        try:
            doc_service = DocumentService(db_session)
            document = await doc_service.create_document_from_url(
                user_id=user_id,
                url=url,
                title=title or None,
            )
            # Link to research session
            document.research_session_id = research_session_id
            await db_session.commit()
            await db_session.refresh(document)

            saved_doc_ids.append(document.id)
            logger.info(
                f"Sub-agent saved document {document.id} for research_session={research_session_id}"
            )
            return f"Saved document {document.id}: {document.title}"
        except Exception as e:
            logger.error(f"save_research_document failed for {url}: {e}")
            return f"Error saving document: {str(e)}"

    return save_research_document


async def run_subagent(
    sub_topic: str,
    brief: str,
    user_id: str,
    db_session: AsyncSession,
    research_session_id: int,
    max_tool_calls: int = 4,
) -> Dict[str, Any]:
    """
    Run a research sub-agent for a single sub-topic.

    The sub-agent is a tool-call loop that uses Tavily search/extract and a
    save_research_document tool. It runs until either the LLM stops calling
    tools or the tool call budget is exhausted.

    Returns:
        {
            "sub_topic": str,
            "saved_doc_ids": List[int],
            "findings_summary": str,
            "tool_calls_used": int,
        }
    """
    saved_doc_ids: List[int] = []

    # Build tools (all closed over sub-agent state)
    search_tool = get_tavily_search_tool()
    extract_tool = get_tavily_extract_tool()
    save_tool = _make_save_research_document_tool(
        db_session, user_id, research_session_id, saved_doc_ids
    )

    if search_tool is None or extract_tool is None:
        logger.error("Tavily tools not available — sub-agent cannot run")
        return {
            "sub_topic": sub_topic,
            "saved_doc_ids": [],
            "findings_summary": "Tavily API not configured.",
            "tool_calls_used": 0,
        }

    tools = [search_tool, extract_tool, save_tool]
    tool_map = {t.name: t for t in tools}

    # LLM
    llm = ChatGoogleGenerativeAI(
        model=settings.GEMINI_FLASH_MODEL,
        google_api_key=settings.GOOGLE_API_KEY,
        temperature=0.2,
    )
    llm_with_tools = llm.bind_tools(tools)

    # System prompt
    prompt_obj = get_prompt(PromptType.CHAT_RESEARCH_SUBAGENT.value)
    if prompt_obj and prompt_obj.system_prompt:
        system_text = prompt_obj.system_prompt.format(
            sub_topic=sub_topic, brief=brief, max_tool_calls=max_tool_calls
        )
    else:
        # Fallback inline prompt
        system_text = (
            f"You are a research sub-agent investigating the sub-topic '{sub_topic}' "
            f"as part of a larger research brief: '{brief}'.\n\n"
            f"You have a budget of {max_tool_calls} tool calls. Your goal is to:\n"
            f"1. Use tavily_search to find 2-3 high-quality, recent sources on the sub-topic.\n"
            f"2. Use tavily_extract on the most promising results to verify their content.\n"
            f"3. Save the worthwhile sources via save_research_document.\n"
            f"4. When done, return a 2-3 sentence summary of your findings.\n\n"
            f"Be efficient — prioritize quality over quantity. Stop calling tools when you "
            f"have enough material to summarize."
        )

    messages: List[Any] = [
        SystemMessage(content=system_text),
        HumanMessage(content=f"Research the sub-topic: {sub_topic}"),
    ]

    tool_calls_used = 0
    findings_summary = ""

    # Tool-call loop
    while tool_calls_used < max_tool_calls:
        try:
            response: AIMessage = await llm_with_tools.ainvoke(messages)
        except Exception as e:
            logger.error(f"Sub-agent LLM call failed: {e}")
            break

        messages.append(response)

        # If no tool calls, the LLM is done — capture its final text as the summary
        if not response.tool_calls:
            findings_summary = response.content or ""
            break

        # Execute tool calls (sequentially to respect budget)
        for tc in response.tool_calls:
            if tool_calls_used >= max_tool_calls:
                break
            tool_name = tc["name"]
            tool_args = tc.get("args", {})
            tool_id = tc["id"]

            tool_fn = tool_map.get(tool_name)
            if tool_fn is None:
                tool_result = f"Unknown tool: {tool_name}"
            else:
                try:
                    tool_result = await tool_fn.ainvoke(tool_args)
                except Exception as e:
                    logger.error(f"Tool {tool_name} failed: {e}")
                    tool_result = f"Tool error: {str(e)}"

            messages.append(
                ToolMessage(content=str(tool_result), tool_call_id=tool_id)
            )
            tool_calls_used += 1

    # If we exited the loop due to budget exhaustion without a summary,
    # ask the LLM to summarize from what it has.
    if not findings_summary:
        try:
            messages.append(
                HumanMessage(
                    content="Tool budget exhausted. Provide a 2-3 sentence summary of what you found."
                )
            )
            final_response: AIMessage = await llm.ainvoke(messages)
            findings_summary = final_response.content or "No findings."
        except Exception as e:
            logger.error(f"Sub-agent final summary failed: {e}")
            findings_summary = f"Sub-agent encountered errors: {e}"

    logger.info(
        f"Sub-agent for '{sub_topic}' complete: "
        f"{len(saved_doc_ids)} docs saved, {tool_calls_used} tool calls used"
    )

    return {
        "sub_topic": sub_topic,
        "saved_doc_ids": saved_doc_ids,
        "findings_summary": findings_summary,
        "tool_calls_used": tool_calls_used,
    }
