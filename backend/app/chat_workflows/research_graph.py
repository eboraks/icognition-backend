"""
Chat agent graph (Agent_Architecture_May_24).

Simplified from the prior "Reflective Research Agent" — no intent_node, no
auto-research dispatch, reflection is opt-in per skill, web search is Tavily.

Flow:
    START
      ├─ skill.research == True (only the "research" skill) → dispatch_research_node → END
      └─ else → generate_node ──► tools? ──► reflect (if skill.reflect) ──► END
"""

from typing import Annotated, Any, Dict, List, Optional, TypedDict

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.core.config import settings
from app.chat_workflows.tools import create_fetch_social_post_tool
from app.chat_workflows.tavily_tools import get_tavily_search_tool, get_tavily_extract_tool
from app.services.prompt_service import get_prompt, get_all_skills, get_skill, get_default_skill
from app.services.prompt_utils import PromptType
from app.utils.logging import get_logger
from app.utils.langfuse_worker import get_langfuse_handler

logger = get_logger(__name__)


# --- State Definition ---


class AgentState(TypedDict):
    messages: Annotated[List[BaseMessage], add_messages]
    skill: str
    latest_query: str
    extracted_entities: List[str]
    kg_context: str
    context_entity_ids: List[int]
    context_document_ids: List[int]
    reflection_count: int
    is_satisfactory: bool


class ReflectionOutput(TypedDict):
    critique: str
    needs_search: bool
    search_query: str
    is_satisfactory: bool


# --- Lightweight entity extraction (replaces intent_node's key_entities) ---


_STOP_WORDS = {
    "the", "a", "an", "is", "are", "was", "were", "what", "who", "where", "when",
    "why", "how", "this", "that", "these", "those", "and", "or", "but", "of", "in",
    "on", "at", "to", "for", "with", "from", "by", "about", "as", "it", "its",
    "my", "your", "our", "their", "his", "her", "do", "does", "did", "can", "could",
    "would", "should", "will", "shall", "may", "might", "be", "been", "being",
    "have", "has", "had", "you", "i", "we", "they", "he", "she",
}


def _extract_query_entities(text_in: str, max_entities: int = 5) -> List[str]:
    """
    Cheap, dependency-free entity extraction for KG enrichment.

    Pulls capitalized multi-word phrases and quoted strings out of the user
    message. This replaces the LLM-based key_entities field that intent_node
    used to produce. Good enough for fuzzy-matching against kg_node.label.
    """
    import re

    if not text_in:
        return []
    # Strip HTML wrappers from chat input (frontend wraps messages in <p>).
    text_in = re.sub(r"<[^>]+>", " ", text_in)

    # Quoted phrases — high signal.
    quoted = re.findall(r'"([^"]{2,80})"|\'([^\']{2,80})\'', text_in)
    found: List[str] = []
    for a, b in quoted:
        phrase = (a or b).strip()
        if phrase and phrase not in found:
            found.append(phrase)

    # Capitalized runs — second pass.
    for match in re.findall(r"\b[A-Z][\w\-]+(?:\s+[A-Z][\w\-]+){0,4}\b", text_in):
        phrase = match.strip()
        # Reject single short capitalized words that are usually sentence starters.
        if len(phrase.split()) == 1 and phrase.lower() in _STOP_WORDS:
            continue
        if phrase and phrase not in found:
            found.append(phrase)

    return found[:max_entities]


# --- Knowledge Graph Entity Resolution ---


async def resolve_entities_from_query(
    entity_names: List[str],
    user_id: str,
    db_session: AsyncSession,
    similarity_threshold: float = 0.3,
    max_entities: int = 10,
) -> tuple:
    """
    Resolve a list of entity names against the knowledge graph using fuzzy matching.
    Returns (formatted_context_string, matched_entity_ids).
    """
    if not entity_names:
        return ("", [])

    all_entity_ids: List[int] = []
    entity_map: Dict[int, dict] = {}

    for name in entity_names[:5]:  # cap to avoid slow queries
        sql = text("""
            SELECT DISTINCT ON (n.label, n.raw_type)
                   n.id, n.label AS name, n.raw_type AS type, n.description,
                   similarity(n.label, :q) AS sim
            FROM kg_node n
            WHERE similarity(n.label, :q) >= :threshold
              AND n.user_id = :user_id
            ORDER BY n.label, n.raw_type, sim DESC
            LIMIT 5
        """)
        result = await db_session.execute(sql, {
            "q": name,
            "threshold": similarity_threshold,
            "user_id": user_id,
        })
        for row in result.mappings().all():
            eid = row["id"]
            if eid not in entity_map:
                entity_map[eid] = {
                    "id": eid,
                    "name": row["name"],
                    "type": row["type"],
                    "description": row["description"],
                    "similarity": round(float(row["sim"]), 3),
                }
                all_entity_ids.append(eid)

    if not all_entity_ids:
        return ("", [])

    rels_sql = text("""
        SELECT e.property_label AS relationship_type,
               n1.label AS from_name, n1.raw_type AS from_type,
               n2.label AS to_name, n2.raw_type AS to_type
        FROM kg_edge e
        JOIN kg_node n1 ON n1.id = e.from_node_id
        JOIN kg_node n2 ON n2.id = e.to_node_id
        WHERE e.from_node_id = ANY(:ids) OR e.to_node_id = ANY(:ids)
        LIMIT 30
    """)
    rels_result = await db_session.execute(rels_sql, {"ids": all_entity_ids})
    relationships = rels_result.mappings().all()

    docs_sql = text("""
        SELECT DISTINCT n.label AS entity_name, d.title AS doc_title
        FROM kg_node_document nd
        JOIN kg_node n ON n.id = nd.node_id
        JOIN document d ON d.id = nd.document_id
        WHERE nd.node_id = ANY(:ids)
        ORDER BY n.label, d.title
        LIMIT 20
    """)
    docs_result = await db_session.execute(docs_sql, {"ids": all_entity_ids})
    entity_docs = docs_result.mappings().all()

    parts = ["[Knowledge Graph Context]", "Entities found in your library:"]
    for e in entity_map.values():
        desc = f" — {e['description']}" if e["description"] else ""
        parts.append(f"  * [{e['type']}] {e['name']}{desc}")

    if relationships:
        parts.append("\nRelationships:")
        seen = set()
        for r in relationships:
            rel_key = (r["from_name"], r["relationship_type"], r["to_name"])
            if rel_key not in seen:
                seen.add(rel_key)
                parts.append(f"  * {r['from_name']} --[{r['relationship_type']}]--> {r['to_name']}")

    if entity_docs:
        parts.append("\nAppears in documents:")
        for ed in entity_docs:
            parts.append(f"  * {ed['entity_name']} -> \"{ed['doc_title']}\"")

    return ("\n".join(parts), list(all_entity_ids))


# --- Graph Builder Helper ---

GraphPrompts = Dict[str, Any]


def fetch_graph_prompts() -> GraphPrompts:
    """Load every prompt the chat graph needs from the YAML-backed prompt service."""
    required = [PromptType.CHAT_REFLECTION]
    prompts: GraphPrompts = {}
    for pt in required:
        prompt = get_prompt(pt.value)
        if prompt is None:
            raise ValueError(
                f"CRITICAL: Missing prompt '{pt.value}' in YAML files. "
                "Cannot build chat graph."
            )
        prompts[pt.value] = prompt

    # Every skill's prompt must resolve to either a YAML entry or an inline prompt_text.
    for skill_key, skill_config in get_all_skills().items():
        pt = skill_config.prompt_type
        if pt in prompts:
            continue
        skill_prompt = get_prompt(pt)
        if skill_prompt is not None:
            prompts[pt] = skill_prompt
        elif not skill_config.prompt_text:
            raise ValueError(
                f"CRITICAL: Missing prompt '{pt}' in YAML files and skill "
                f"'{skill_key}' has no prompt_text. Cannot build chat graph."
            )

    return prompts


def build_research_graph(
    checkpointer=None,
    retrieve_tool=None,
    kg_tool=None,
    prompts: Optional[GraphPrompts] = None,
    db_session: Optional[AsyncSession] = None,
    user_id: Optional[str] = None,
    skill_override: Optional[str] = None,
    chat_session_id: Optional[int] = None,
):
    """
    Build the compiled StateGraph for the chat agent.

    Args:
        checkpointer: LangGraph checkpointer (e.g. AsyncPostgresSaver).
        retrieve_tool: LangChain tool for KB retrieval (session-scoped).
        kg_tool: Knowledge graph tool (session-scoped).
        prompts: Pre-fetched prompt dict from fetch_graph_prompts().
        db_session: AsyncSession for KG entity resolution.
        user_id: User ID for scoping KG queries.
        skill_override: Skill key from `?skill=` query param. Defaults to default_skill.
        chat_session_id: Used to thread research sessions across turns.
    """
    if prompts is None:
        raise ValueError(
            "build_research_graph() requires a 'prompts' dict. "
            "Call fetch_graph_prompts() first."
        )

    skills = get_all_skills()
    default_skill = get_default_skill()
    initial_skill = skill_override if skill_override in skills else default_skill

    llm = ChatGoogleGenerativeAI(
        model=settings.GEMINI_FLASH_MODEL,
        google_api_key=settings.GOOGLE_API_KEY,
        temperature=0.1,
    )

    # --- Tools (Tavily replaces Google CSE) ---
    tavily_search = get_tavily_search_tool()
    tavily_extract = get_tavily_extract_tool()
    fetch_tool = create_fetch_social_post_tool()

    tools: List[Any] = []
    if retrieve_tool is not None:
        tools.append(retrieve_tool)
    tools.append(fetch_tool)
    if tavily_search is not None:
        tools.append(tavily_search)
    if tavily_extract is not None:
        tools.append(tavily_extract)
    if kg_tool is not None:
        tools.append(kg_tool)

    llm_with_tools = llm.bind_tools(tools)

    # --- Nodes ---

    async def _enrich_kg(state: AgentState) -> tuple:
        """Resolve query entities against the KG. Returns (kg_context, entity_ids)."""
        entities = state.get("extracted_entities") or []
        if not entities or not db_session or not user_id:
            return ("", [])
        try:
            return await resolve_entities_from_query(
                entity_names=entities,
                user_id=user_id,
                db_session=db_session,
            )
        except Exception as e:
            logger.warning(f"KG enrichment failed (non-fatal): {e}")
            return ("", [])

    async def generate_node(state: AgentState) -> dict:
        """Resolve the skill prompt, enrich with KG context, call the LLM with tools."""
        messages = state["messages"]
        skill_key = state.get("skill") or initial_skill
        skill_config = skills.get(skill_key) or skills[default_skill]

        # KG enrichment runs once per turn (only if not already populated).
        kg_context = state.get("kg_context") or ""
        context_entity_ids = state.get("context_entity_ids") or []
        if not kg_context and state.get("extracted_entities"):
            kg_context, context_entity_ids = await _enrich_kg(state)

        # Resolve system prompt from YAML (or skill's inline prompt_text fallback).
        yaml_prompt = prompts.get(skill_config.prompt_type)
        if yaml_prompt:
            system_msg = yaml_prompt.system_prompt or ""
            if yaml_prompt.user_prompt:
                system_msg += f"\n\n{yaml_prompt.user_prompt}"
        elif skill_config.prompt_text:
            system_msg = skill_config.prompt_text
        else:
            return {
                "messages": [AIMessage(
                    content=f"The '{skill_key}' skill is not configured. Please contact support."
                )],
                "kg_context": kg_context,
                "context_entity_ids": context_entity_ids,
                "is_satisfactory": True,
            }

        # Inject the slash_instruction when the user message is bare (e.g. just "/fact_check").
        prompt_msgs = list(messages)
        last_msg = prompt_msgs[-1] if prompt_msgs else None
        if isinstance(last_msg, HumanMessage) and skill_override:
            import re
            clean = re.sub(r"<[^>]+>", "", str(last_msg.content)).strip()
            remaining = re.sub(r"^/\w+\s*", "", clean).strip()
            if not remaining and skill_config.slash_instruction:
                instruction = skill_config.slash_instruction
                if kg_context:
                    instruction = f"{instruction}\n\n{kg_context}"
                prompt_msgs[-1] = HumanMessage(content=instruction)
            elif kg_context:
                prompt_msgs[-1] = HumanMessage(content=f"{last_msg.content}\n\n{kg_context}")
        elif isinstance(last_msg, HumanMessage) and kg_context:
            prompt_msgs[-1] = HumanMessage(content=f"{last_msg.content}\n\n{kg_context}")

        prompt_msgs = [SystemMessage(content=system_msg)] + prompt_msgs

        try:
            response = await llm_with_tools.ainvoke(
                prompt_msgs,
                config={"run_name": skill_config.prompt_type},
            )
            # Gemini occasionally emits MALFORMED_FUNCTION_CALL with empty body; retry without tools.
            finish_reason = response.response_metadata.get("finish_reason", "")
            if finish_reason == "MALFORMED_FUNCTION_CALL" or (
                not response.content and not response.tool_calls
            ):
                logger.warning(f"Malformed Gemini response (finish_reason={finish_reason}); retrying without tools")
                response = await llm.ainvoke(
                    prompt_msgs,
                    config={"run_name": f"{skill_config.prompt_type}_retry"},
                )
        except Exception as e:
            logger.error(f"LLM call failed in generate_node ({skill_key}): {e}", exc_info=True)
            response = AIMessage(
                content=f"I'm sorry, I encountered an error while processing your request. ({type(e).__name__})"
            )

        return {
            "messages": [response],
            "kg_context": kg_context,
            "context_entity_ids": context_entity_ids,
        }

    async def reflect_node(state: AgentState) -> dict:
        """Critique the latest AI response (opt-in per skill via skill.reflect)."""
        messages = state["messages"]
        if not messages:
            return {"reflection_count": state.get("reflection_count", 0) + 1, "is_satisfactory": True}

        # Pull the latest human/AI pair (avoids confusing the reflector with old turns).
        last_human, last_ai_response = None, None
        for msg in reversed(messages):
            if isinstance(msg, AIMessage) and not msg.tool_calls and last_ai_response is None:
                content = msg.content
                if isinstance(content, list):
                    content = " ".join(
                        item.get("text", "") if isinstance(item, dict) else str(item)
                        for item in content
                    )
                last_ai_response = content
            elif isinstance(msg, HumanMessage) and last_human is None and last_ai_response is not None:
                content = msg.content
                if isinstance(content, list):
                    content = " ".join(
                        item.get("text", "") if isinstance(item, dict) else str(item)
                        for item in content
                    )
                last_human = content
                break

        if not last_ai_response:
            return {"reflection_count": state.get("reflection_count", 0) + 1, "is_satisfactory": True}

        reflect_prompt = prompts.get(PromptType.CHAT_REFLECTION.value)
        if not reflect_prompt:
            return {"reflection_count": state.get("reflection_count", 0) + 1, "is_satisfactory": True}

        # Role-swap: feed AI answer as Human (student submission), question as AI.
        translated = []
        if last_human:
            translated.append(AIMessage(content=last_human))
        translated.append(HumanMessage(content=last_ai_response))
        msgs_str = "\n\n".join(f"{m.type.upper()}: {m.content}" for m in translated)

        user_template = reflect_prompt.user_prompt or "Student Submission:\n{messages}"
        try:
            user_content = user_template.format(messages=msgs_str)
        except Exception:
            user_content = f"Student Submission:\n{msgs_str}"

        chain = ChatPromptTemplate.from_messages([
            SystemMessage(content=reflect_prompt.system_prompt),
            HumanMessage(content=user_content),
        ]) | llm.with_structured_output(ReflectionOutput)

        try:
            result = await chain.ainvoke(
                {"messages": translated},
                config={"run_name": PromptType.CHAT_REFLECTION.value},
            )
        except Exception as e:
            logger.error(f"Reflection failed: {e}", exc_info=True)
            return {"reflection_count": state.get("reflection_count", 0) + 1, "is_satisfactory": True}

        return {
            "reflection_count": state.get("reflection_count", 0) + 1,
            "is_satisfactory": result["is_satisfactory"],
            "messages": [HumanMessage(content=result["critique"])] if not result["is_satisfactory"] else [],
        }

    async def dispatch_research_node(state: AgentState) -> dict:
        """Run the multi-agent research workflow. Reached only when skill == 'research'."""
        from app.chat_workflows.research_multiagent_graph import (
            build_research_multiagent_graph,
            DEFAULT_MAX_SUBAGENTS,
            DEFAULT_MAX_TOOL_CALLS_PER_SUBAGENT,
            DEFAULT_MAX_CRITIC_LOOPS,
        )
        from app.models import ResearchSession
        from sqlalchemy import select

        # The "brief" is the user's latest message — or the resolved latest_query
        # if we have one (it'll usually equal the message content here).
        brief = state.get("latest_query") or (
            state["messages"][-1].content if state.get("messages") else ""
        )
        if isinstance(brief, list):
            brief = " ".join(
                item.get("text", "") if isinstance(item, dict) else str(item)
                for item in brief
            )

        # Reuse an existing ResearchSession for this chat (so follow-ups extend it).
        research_session_id: Optional[int] = None
        extended_existing = False
        if db_session and user_id:
            try:
                existing = None
                if chat_session_id:
                    result = await db_session.execute(
                        select(ResearchSession)
                        .where(ResearchSession.chat_session_id == chat_session_id)
                        .where(ResearchSession.user_id == user_id)
                        .order_by(ResearchSession.id.desc())
                        .limit(1)
                    )
                    existing = result.scalar_one_or_none()

                if existing is not None:
                    existing.status = "running"
                    existing.final_response = None
                    await db_session.commit()
                    await db_session.refresh(existing)
                    research_session_id = existing.id
                    extended_existing = True
                else:
                    rs = ResearchSession(
                        user_id=user_id,
                        brief=brief,
                        status="running",
                        chat_session_id=chat_session_id,
                        budget={
                            "max_subagents": DEFAULT_MAX_SUBAGENTS,
                            "max_tool_calls_per_subagent": DEFAULT_MAX_TOOL_CALLS_PER_SUBAGENT,
                            "max_critic_loops": DEFAULT_MAX_CRITIC_LOOPS,
                        },
                    )
                    db_session.add(rs)
                    await db_session.commit()
                    await db_session.refresh(rs)
                    research_session_id = rs.id
            except Exception as e:
                logger.error(f"Failed to prepare research session: {e}")

        if research_session_id is None:
            return {
                "messages": [AIMessage(content="Research dispatch failed: could not create research session.")],
                "is_satisfactory": True,
            }

        try:
            research_graph = build_research_multiagent_graph(checkpointer=None)
            initial_state = {
                "brief": brief,
                "user_id": user_id,
                "research_session_id": research_session_id,
                "subagent_results": [],
                "critic_loops": 0,
                "budget": {
                    "max_subagents": DEFAULT_MAX_SUBAGENTS,
                    "max_tool_calls_per_subagent": DEFAULT_MAX_TOOL_CALLS_PER_SUBAGENT,
                    "max_critic_loops": DEFAULT_MAX_CRITIC_LOOPS,
                },
            }
            run_config: Dict[str, Any] = {"configurable": {"thread_id": f"research_{research_session_id}"}}

            lf_handler = get_langfuse_handler()
            if lf_handler:
                run_config["callbacks"] = [lf_handler]
                run_config["run_name"] = "Research Multi-Agent"
                run_config["metadata"] = {
                    "research_session_id": str(research_session_id),
                    "user_id": str(user_id),
                    "brief": brief[:200],
                }
                run_config["tags"] = ["research_agent"]

            final_state = await research_graph.ainvoke(initial_state, config=run_config)
            final_response = final_state.get("final_response", "Research completed but produced no response.")
            saved_doc_ids = final_state.get("saved_doc_ids") or []

            try:
                result = await db_session.execute(
                    select(ResearchSession).where(ResearchSession.id == research_session_id)
                )
                rs = result.scalar_one_or_none()
                if rs:
                    rs.status = "completed"
                    rs.final_response = final_response
                    new_sub_topics = final_state.get("plan") or []
                    if extended_existing:
                        existing_plan = (rs.plan or {}).get("sub_topics", []) if isinstance(rs.plan, dict) else []
                        rs.plan = {
                            "sub_topics": list(existing_plan) + list(new_sub_topics),
                            "last_follow_up_brief": brief,
                        }
                    else:
                        rs.plan = {"sub_topics": new_sub_topics}
                    await db_session.commit()
            except Exception as e:
                logger.error(f"Failed to update research session: {e}")

            return {
                "messages": [AIMessage(content=final_response)],
                "context_document_ids": saved_doc_ids,
                "is_satisfactory": True,
            }
        except Exception as e:
            logger.error(f"Research workflow failed: {e}", exc_info=True)
            try:
                result = await db_session.execute(
                    select(ResearchSession).where(ResearchSession.id == research_session_id)
                )
                rs = result.scalar_one_or_none()
                if rs:
                    rs.status = "failed"
                    await db_session.commit()
            except Exception:
                pass
            return {
                "messages": [AIMessage(content=f"Research workflow encountered an error: {e}")],
                "is_satisfactory": True,
            }

    # --- Initialize per-turn state from the entry point ---

    async def init_turn_node(state: AgentState) -> dict:
        """
        Reset per-turn state and extract entities from the new user message.

        Runs as the first node every turn. This is what intent_node used to do
        (minus the LLM classification, which is now baked into the system prompt).
        Lightweight regex-based entity extraction replaces the LLM `key_entities` field.
        """
        last_user = ""
        for msg in reversed(state.get("messages", [])):
            if isinstance(msg, HumanMessage):
                content = msg.content
                if isinstance(content, list):
                    content = " ".join(
                        item.get("text", "") if isinstance(item, dict) else str(item)
                        for item in content
                    )
                last_user = str(content)
                break

        entities = _extract_query_entities(last_user)
        skill_key = skill_override if skill_override in skills else default_skill

        return {
            "skill": skill_key,
            "latest_query": last_user,
            "extracted_entities": entities,
            # Reset per-turn state so prior turn's checkpoint values don't leak.
            "kg_context": "",
            "context_entity_ids": [],
            "is_satisfactory": False,
            "reflection_count": 0,
        }

    # --- Graph wiring ---

    graph = StateGraph(AgentState)
    graph.add_node("init_turn", init_turn_node)
    graph.add_node("generate_node", generate_node)
    graph.add_node("reflect_node", reflect_node)
    graph.add_node("dispatch_research_node", dispatch_research_node)
    graph.add_node("tools", ToolNode(tools, handle_tool_errors=True))

    graph.add_edge(START, "init_turn")

    def route_after_init(state: AgentState) -> str:
        """If skill == research, short-circuit into the multi-agent sub-graph."""
        skill_cfg = skills.get(state.get("skill") or default_skill)
        if skill_cfg and getattr(skill_cfg, "research", False):
            return "dispatch_research_node"
        return "generate_node"

    graph.add_conditional_edges(
        "init_turn",
        route_after_init,
        {"generate_node": "generate_node", "dispatch_research_node": "dispatch_research_node"},
    )
    graph.add_edge("dispatch_research_node", END)

    def route_after_generate(state: AgentState) -> str:
        """tools → loop; else: reflect only if the active skill opts in."""
        last_msg = state["messages"][-1]
        if getattr(last_msg, "tool_calls", None):
            return "tools"
        skill_cfg = skills.get(state.get("skill") or default_skill)
        if skill_cfg and getattr(skill_cfg, "reflect", False):
            return "reflect_node"
        return END

    graph.add_conditional_edges(
        "generate_node",
        route_after_generate,
        {"tools": "tools", "reflect_node": "reflect_node", END: END},
    )
    graph.add_edge("tools", "generate_node")

    def route_after_reflect(state: AgentState) -> str:
        if state.get("reflection_count", 0) > 3 or state.get("is_satisfactory"):
            return END
        return "generate_node"

    graph.add_conditional_edges(
        "reflect_node",
        route_after_reflect,
        {END: END, "generate_node": "generate_node"},
    )

    return graph.compile(checkpointer=checkpointer)
