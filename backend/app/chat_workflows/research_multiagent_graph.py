"""
Research multi-agent LangGraph workflow.

Plan-and-Execute + Supervisor architecture:
  planner -> supervisor (fan out via Send) -> [parallel sub-agents] -> coverage_critic -> writer

Each sub-agent is a small ReAct loop (defined in research_subagent.py) that
searches the web, extracts content, and saves documents to the user's library.
The writer synthesizes all findings into a final response with citations.
"""

import json
from typing import Annotated, Any, Dict, List, Optional, TypedDict

from langgraph.constants import Send
from langgraph.graph import END, START, StateGraph
from langchain_google_genai import ChatGoogleGenerativeAI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.chat_workflows.research_subagent import run_subagent
from app.models import Document
from app.services.prompt_service import get_prompt
from app.services.prompt_utils import PromptType
from app.utils.logging import get_logger
from app.utils.langfuse_worker import get_langfuse_handler

logger = get_logger(__name__)

# Hard caps for v1 (conservative budget)
DEFAULT_MAX_SUBAGENTS = 3
DEFAULT_MAX_TOOL_CALLS_PER_SUBAGENT = 4
DEFAULT_MAX_CRITIC_LOOPS = 1


def _create_llm(temperature: float = 0.2, max_output_tokens: int = 1024) -> ChatGoogleGenerativeAI:
    """Create a Gemini Flash LLM with optional Langfuse tracing."""
    lf_handler = get_langfuse_handler()
    kwargs = {}
    if lf_handler:
        kwargs["callbacks"] = [lf_handler]
    return ChatGoogleGenerativeAI(
        model=settings.GEMINI_FLASH_MODEL,
        google_api_key=settings.GOOGLE_API_KEY,
        temperature=temperature,
        max_output_tokens=max_output_tokens,
        **kwargs,
    )


def _list_append_reducer(left: List[Any], right: List[Any]) -> List[Any]:
    """Reducer that appends new items to a list (used for parallel sub-agent results)."""
    if left is None:
        left = []
    if right is None:
        return left
    return left + right


class ResearchState(TypedDict, total=False):
    brief: str
    user_id: str
    research_session_id: int
    plan: List[Dict[str, str]]
    subagent_results: Annotated[List[Dict[str, Any]], _list_append_reducer]
    critic_loops: int
    coverage_complete: bool
    final_response: str
    saved_doc_ids: List[int]
    budget: Dict[str, int]
    # Error-surface fields. Populated when the planner produces no usable
    # plan so the supervisor and writer can skip the LLM call instead of
    # hallucinating sources. Both fields flow through the LangGraph state
    # and show up in the Langfuse trace for diagnosis.
    planner_raw_response: str
    research_error: str


# ----------------------------------------------------------------------
# Nodes
# ----------------------------------------------------------------------


async def planner_node(state: ResearchState) -> Dict[str, Any]:
    """Decompose the brief into 1-3 sub-topics using Gemini Flash."""
    brief = state["brief"]
    budget = state.get("budget") or {}
    max_subagents = budget.get("max_subagents", DEFAULT_MAX_SUBAGENTS)

    # 4096 tokens so Gemini 2.5 Flash's extended thinking can consume its
    # reasoning budget without starving the JSON output. At 1024 we saw
    # traces where 981 reasoning tokens left only ~43 for the plan, which
    # truncated to an empty {"sub_topics": []}.
    llm = _create_llm(temperature=0.2, max_output_tokens=4096)

    prompt_obj = get_prompt(PromptType.CHAT_RESEARCH_PLANNER.value)
    if not prompt_obj:
        raise ValueError(f"Missing prompt: {PromptType.CHAT_RESEARCH_PLANNER.value}. Add it to backend/agent/prompts/research.yaml")
    system_text = prompt_obj.system_prompt
    user_text = prompt_obj.user_prompt.format(brief=brief)

    content = ""
    llm_error: Optional[str] = None
    try:
        response = await llm.ainvoke(
            [
                {"role": "system", "content": system_text},
                {"role": "user", "content": user_text},
            ]
        )
        content = response.content or ""
        plan = _parse_plan(content)
    except Exception as e:
        llm_error = str(e)
        logger.error(f"Planner LLM call failed: {e}")
        plan = []

    # Enforce hard cap
    plan = plan[:max_subagents]

    if not plan:
        # Never fall through silently — log the raw LLM response and stash it
        # into state so it surfaces in the Langfuse trace for diagnosis.
        # Without this the supervisor would route the writer with zero
        # evidence and the writer would hallucinate sources.
        logger.error(
            "Planner returned empty plan for brief=%r. llm_error=%s raw_response=%r",
            brief[:200], llm_error, content,
        )
        reason = (
            f"Planner LLM call failed: {llm_error}"
            if llm_error
            else "Planner returned no sub-topics (likely truncated output — "
                 "reasoning tokens consumed the max_output_tokens budget)."
        )
        return {
            "plan": [],
            "planner_raw_response": content,
            "research_error": reason,
        }

    logger.info(f"Planner generated {len(plan)} sub-topics for brief: {brief[:80]}")
    return {"plan": plan}


def _parse_plan(content: str) -> List[Dict[str, str]]:
    """Parse the planner's JSON response, handling markdown fences."""
    import re

    # Strip markdown fences
    content = content.strip()
    fence_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", content, re.DOTALL)
    if fence_match:
        content = fence_match.group(1).strip()

    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        # Try to find first {...} block
        start = content.find("{")
        end = content.rfind("}")
        if start != -1 and end != -1:
            try:
                data = json.loads(content[start : end + 1])
            except json.JSONDecodeError:
                logger.warning(f"Failed to parse planner JSON: {content[:200]}")
                return []
        else:
            return []

    if isinstance(data, dict):
        sub_topics = data.get("sub_topics", [])
    elif isinstance(data, list):
        sub_topics = data
    else:
        return []

    # Normalize each entry
    normalized = []
    for item in sub_topics:
        if isinstance(item, dict) and item.get("topic"):
            normalized.append({
                "topic": str(item["topic"])[:500],
                "rationale": str(item.get("rationale", ""))[:500],
            })
        elif isinstance(item, str):
            normalized.append({"topic": item[:500], "rationale": ""})
    return normalized


async def supervisor_node(state: ResearchState) -> Dict[str, Any]:
    """Routing anchor for the fan-out. Also surfaces any planner failure
    into state + logs so Langfuse and the operator both see it."""
    plan = state.get("plan", [])
    if not plan:
        raw = state.get("planner_raw_response", "")
        existing_error = state.get("research_error")
        reason = existing_error or "Planner returned no sub-topics."
        logger.error(
            "Supervisor: skipping sub-agents — no plan to dispatch. "
            "reason=%r raw_planner_response=%r",
            reason, raw,
        )
        # Ensure research_error is set even if planner didn't set it
        # (defensive — state should already carry it).
        return {"research_error": reason}
    return {}


def supervisor_route(state: ResearchState) -> List[Send]:
    """
    Use LangGraph Send API to fan out to N parallel sub-agents,
    one per sub-topic in the plan.
    """
    plan = state.get("plan", [])
    if not plan:
        return [Send("writer_node", state)]

    sends = []
    for sub in plan:
        sends.append(
            Send(
                "subagent_node",
                {
                    "brief": state["brief"],
                    "user_id": state["user_id"],
                    "research_session_id": state["research_session_id"],
                    "budget": state.get("budget") or {},
                    "_sub_topic": sub["topic"],  # carried into subagent_node
                },
            )
        )
    return sends


async def subagent_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Execute a single research sub-agent for one sub-topic.
    Note: this node receives a partial state via Send — only the fields we passed.
    """
    sub_topic = state.get("_sub_topic", "")
    brief = state["brief"]
    user_id = state["user_id"]
    research_session_id = state["research_session_id"]
    budget = state.get("budget") or {}
    max_tool_calls = budget.get(
        "max_tool_calls_per_subagent", DEFAULT_MAX_TOOL_CALLS_PER_SUBAGENT
    )

    # Need a fresh DB session for this sub-agent (parallel execution)
    from app.db.database import async_session

    async with async_session() as db_session:
        try:
            result = await run_subagent(
                sub_topic=sub_topic,
                brief=brief,
                user_id=user_id,
                db_session=db_session,
                research_session_id=research_session_id,
                max_tool_calls=max_tool_calls,
            )
        except Exception as e:
            logger.error(f"Sub-agent for '{sub_topic}' crashed: {e}")
            result = {
                "sub_topic": sub_topic,
                "saved_doc_ids": [],
                "findings_summary": f"Sub-agent crashed: {e}",
                "tool_calls_used": 0,
            }

    # The list_append reducer will merge this into subagent_results
    return {"subagent_results": [result]}


async def coverage_critic_node(state: ResearchState) -> Dict[str, Any]:
    """Judge whether the findings adequately cover the brief."""
    brief = state["brief"]
    findings = state.get("subagent_results", [])
    critic_loops = state.get("critic_loops", 0)

    findings_text = "\n\n".join(
        f"Sub-topic: {f.get('sub_topic', '?')}\n"
        f"Saved docs: {len(f.get('saved_doc_ids', []))}\n"
        f"Summary: {f.get('findings_summary', '')}"
        for f in findings
    )

    llm = _create_llm(temperature=0.2)

    prompt_obj = get_prompt(PromptType.CHAT_RESEARCH_COVERAGE_CRITIC.value)
    if not prompt_obj:
        raise ValueError(f"Missing prompt: {PromptType.CHAT_RESEARCH_COVERAGE_CRITIC.value}. Add it to backend/agent/prompts/research.yaml")
    system_text = prompt_obj.system_prompt
    user_text = prompt_obj.user_prompt.format(brief=brief, findings=findings_text)

    coverage_complete = True  # Default to true if parsing fails
    try:
        response = await llm.ainvoke(
            [
                {"role": "system", "content": system_text},
                {"role": "user", "content": user_text},
            ]
        )
        content = response.content or ""
        data = _parse_json_obj(content)
        coverage_complete = bool(data.get("coverage_complete", True))
        logger.info(
            f"Coverage critic: complete={coverage_complete}, "
            f"rationale={data.get('rationale', '')[:100]}"
        )
    except Exception as e:
        logger.error(f"Coverage critic LLM call failed: {e}")

    return {
        "coverage_complete": coverage_complete,
        "critic_loops": critic_loops + 1,
    }


def _parse_json_obj(content: str) -> dict:
    """Parse JSON from LLM response, handling markdown fences."""
    import re

    content = content.strip()
    fence_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", content, re.DOTALL)
    if fence_match:
        content = fence_match.group(1).strip()
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        start = content.find("{")
        end = content.rfind("}")
        if start != -1 and end != -1:
            try:
                return json.loads(content[start : end + 1])
            except json.JSONDecodeError:
                pass
    return {}


def route_after_critic(state: ResearchState) -> str:
    """If coverage incomplete and we have a budget for another loop, go back to supervisor."""
    budget = state.get("budget") or {}
    max_loops = budget.get("max_critic_loops", DEFAULT_MAX_CRITIC_LOOPS)
    if not state.get("coverage_complete") and state.get("critic_loops", 0) <= max_loops:
        return "supervisor_node"
    return "writer_node"


async def writer_node(state: ResearchState) -> Dict[str, Any]:
    """Synthesize the final response with citations."""
    brief = state["brief"]
    findings = state.get("subagent_results", [])
    research_error = state.get("research_error")

    # If research never ran (empty plan, planner failure, etc.), skip the
    # writer LLM entirely. Calling it with zero findings caused it to
    # hallucinate sources like https://www.example.com/... in production.
    if research_error and not findings:
        logger.error(
            "Writer: bypassing LLM because research_error=%r", research_error
        )
        final_response = (
            "I couldn't complete the research for this question.\n\n"
            f"**Reason:** {research_error}\n\n"
            "Please try rephrasing your question or try again in a moment."
        )
        return {"final_response": final_response, "saved_doc_ids": []}

    # Collect all saved doc IDs across sub-agents
    all_doc_ids: List[int] = []
    for f in findings:
        all_doc_ids.extend(f.get("saved_doc_ids", []))

    # Build citation map by fetching document titles + URLs
    citation_map = ""
    if all_doc_ids:
        from app.db.database import async_session

        async with async_session() as db_session:
            sql = text("""
                SELECT id, title, url FROM document WHERE id = ANY(:ids)
            """)
            result = await db_session.execute(sql, {"ids": all_doc_ids})
            doc_rows = list(result.mappings().all())

        # Order by all_doc_ids (preserve order)
        doc_by_id = {r["id"]: r for r in doc_rows}
        ordered = [doc_by_id[did] for did in all_doc_ids if did in doc_by_id]
        citation_lines = []
        for i, r in enumerate(ordered, 1):
            title = r.get("title") or "Untitled"
            url = r.get("url") or ""
            citation_lines.append(f"[{i}] {title} — {url}")
        citation_map = "\n".join(citation_lines)

    # Build rich findings text with extracted content (not just summaries)
    findings_parts = []
    for f in findings:
        part = f"### Sub-topic: {f.get('sub_topic', '?')}\n"
        part += f"**Summary:** {f.get('findings_summary', '')}\n"
        # Include extracted source content for richer synthesis
        for ec in f.get("extracted_contents", []):
            url = ec.get("url", "")
            content = ec.get("content", "")[:1500]
            if content:
                part += f"\n**Source content ({url}):**\n{content}\n"
        findings_parts.append(part)
    findings_text = "\n\n---\n\n".join(findings_parts)

    llm = _create_llm(temperature=0.4, max_output_tokens=4096)

    prompt_obj = get_prompt(PromptType.CHAT_RESEARCH_WRITER.value)
    if not prompt_obj:
        raise ValueError(f"Missing prompt: {PromptType.CHAT_RESEARCH_WRITER.value}. Add it to backend/agent/prompts/research.yaml")
    system_text = prompt_obj.system_prompt
    user_text = prompt_obj.user_prompt.format(
        brief=brief, citation_map=citation_map or "(no sources saved)", findings=findings_text
    )

    try:
        response = await llm.ainvoke(
            [
                {"role": "system", "content": system_text},
                {"role": "user", "content": user_text},
            ]
        )
        final_response = response.content or "Research completed but no response generated."
    except Exception as e:
        logger.error(f"Writer LLM call failed: {e}")
        final_response = (
            f"Research completed but the writer failed: {e}. "
            f"Saved {len(all_doc_ids)} documents."
        )

    logger.info(
        f"Writer produced {len(final_response)} chars, "
        f"citing {len(all_doc_ids)} saved documents"
    )

    return {
        "final_response": final_response,
        "saved_doc_ids": all_doc_ids,
    }


# ----------------------------------------------------------------------
# Graph builder
# ----------------------------------------------------------------------


def build_research_multiagent_graph(checkpointer=None):
    """
    Build the research multi-agent LangGraph.

    The graph is stateless w.r.t. user_id and db_session — those flow through
    the state dict so the graph can be compiled once and reused.
    """
    graph = StateGraph(ResearchState)

    graph.add_node("planner_node", planner_node)
    graph.add_node("supervisor_node", supervisor_node)
    graph.add_node("subagent_node", subagent_node)
    graph.add_node("coverage_critic_node", coverage_critic_node)
    graph.add_node("writer_node", writer_node)

    graph.add_edge(START, "planner_node")
    graph.add_edge("planner_node", "supervisor_node")
    # Supervisor fans out to N parallel sub-agents via Send
    graph.add_conditional_edges(
        "supervisor_node",
        supervisor_route,
        ["subagent_node", "writer_node"],
    )
    graph.add_edge("subagent_node", "coverage_critic_node")
    graph.add_conditional_edges(
        "coverage_critic_node",
        route_after_critic,
        {"supervisor_node": "supervisor_node", "writer_node": "writer_node"},
    )
    graph.add_edge("writer_node", END)

    return graph.compile(checkpointer=checkpointer)
