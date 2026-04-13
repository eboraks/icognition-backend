import re
from typing import Annotated, Any, Dict, List, Optional, TypedDict

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.core.config import settings
from app.chat_workflows.tools import get_google_search_tool, create_retrieve_documents_tool, create_fetch_social_post_tool, create_world_context_tool
from app.services.prompt_service import get_prompt, get_all_skills, get_skill, get_default_skill, match_skill
from app.services.prompt_utils import PromptType
from app.utils.logging import get_logger

logger = get_logger(__name__)

# --- State Definition ---

class AgentState(TypedDict):
    messages: Annotated[List[BaseMessage], add_messages]
    intent_description: str
    reflection_count: int
    latest_query: str
    is_satisfactory: bool
    skill: str
    extracted_entities: List[str]
    kg_context: str
    context_entity_ids: List[int]
    context_document_ids: List[int]
    requires_research: bool

# --- Structured Outputs ---

class IntentClassification(TypedDict):
    describe_the_user_message_intent: str
    refined_query: str
    reasoning: str
    key_entities: List[str]
    requires_research: bool

class ReflectionOutput(TypedDict):
    critique: str
    needs_search: bool
    search_query: str
    is_satisfactory: bool


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

    all_entity_ids = []
    entity_map: Dict[int, dict] = {}

    for name in entity_names[:5]:  # cap at 5 to avoid slow queries
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

    # Fetch edges between/involving matched nodes
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

    # Fetch documents linked to these nodes
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

    # Format the context
    parts = ["[Knowledge Graph Context]"]

    parts.append("Entities found in your library:")
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

# Type alias: maps prompt_type strings to SimpleNamespace objects.
GraphPrompts = Dict[str, Any]


def fetch_graph_prompts() -> GraphPrompts:
    """
    Load all prompts required by the research graph from YAML files.

    No database session needed — reads from the YAML-backed prompt service.
    Raises ValueError if any required prompt is missing.
    """
    required = [
        PromptType.CHAT_INTENT_CLASSIFICATION,
        PromptType.CHAT_REFLECTION,
    ]
    prompts: GraphPrompts = {}
    for pt in required:
        prompt = get_prompt(pt.value)
        if prompt is None:
            raise ValueError(
                f"CRITICAL: Missing prompt '{pt.value}' in YAML files. "
                "Cannot build research graph."
            )
        prompts[pt.value] = prompt

    # Load all skill prompts (skills with prompt_text survive missing YAML entries)
    skills = get_all_skills()
    for skill_key, skill_config in skills.items():
        pt = skill_config.prompt_type
        if pt not in prompts:
            skill_prompt = get_prompt(pt)
            if skill_prompt is not None:
                prompts[pt] = skill_prompt
            elif not skill_config.prompt_text:
                raise ValueError(
                    f"CRITICAL: Missing prompt '{pt}' in YAML files "
                    f"and skill '{skill_key}' has no prompt_text. "
                    "Cannot build research graph."
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
):
    """
    Builds the compiled StateGraph for the Reflective Research Agent.

    Args:
        checkpointer: LangGraph checkpointer (e.g. AsyncPostgresSaver)
        retrieve_tool: LangChain tool for KB retrieval
        prompts: Pre-fetched prompt dict from fetch_graph_prompts().
        db_session: AsyncSession for KG entity resolution (optional).
        user_id: User ID for scoping KG queries (optional).
    """
    if prompts is None:
        raise ValueError(
            "build_research_graph() requires a 'prompts' dict. "
            "Call fetch_graph_prompts() first."
        )

    # Load skills from YAML
    skills = get_all_skills()
    default_skill = get_default_skill()

    # 1. Initialize LLMs
    llm = ChatGoogleGenerativeAI(
        model=settings.GEMINI_FLASH_MODEL,
        google_api_key=settings.GOOGLE_API_KEY,
        temperature=0.1
    )

    # Tools
    google_tool = get_google_search_tool()
    fetch_tool = create_fetch_social_post_tool()
    world_tool = create_world_context_tool()
    tools = [retrieve_tool] if retrieve_tool else []
    tools.append(fetch_tool)
    if world_tool:
        tools.append(world_tool)
    if kg_tool:
        tools.append(kg_tool)
    if google_tool:
        tools.append(google_tool)

    llm_with_tools = llm.bind_tools(tools)

    # 2. Nodes

    async def intent_node(state: AgentState):
        """Classifies the user's intent and matches the best skill via embedding similarity."""
        messages = state["messages"]
        last_message = messages[-1].content

        try:
            intent_prompt = prompts.get(PromptType.CHAT_INTENT_CLASSIFICATION.value)
            if not intent_prompt:
                logger.warning("Intent classification prompt not found — using defaults")
                raise ValueError("Missing intent prompt")

            system_prompt = intent_prompt.system_prompt
            user_template = intent_prompt.user_prompt or "{input}"

            prompt = ChatPromptTemplate.from_messages([
                ("system", system_prompt),
                ("human", user_template),
            ])

            classifier = prompt | llm.with_structured_output(IntentClassification)
            result = await classifier.ainvoke(
                {"input": last_message},
                config={"run_name": PromptType.CHAT_INTENT_CLASSIFICATION.value}
            )
        except Exception as e:
            logger.error(f"Intent classification failed: {e}", exc_info=True)
            result = {
                "refined_query": str(last_message),
                "describe_the_user_message_intent": "",
                "key_entities": [],
                "requires_research": False,
            }

        # Skill selection: slash command override > embedding similarity match
        if skill_override and skill_override in skills:
            skill = skill_override
            logger.info(f"Using skill override: '{skill}'")
        else:
            skill = await match_skill(str(last_message))

        requires_research = bool(result.get("requires_research", False))
        if requires_research:
            logger.info(f"Intent flagged as research: {result['refined_query'][:80]}")

        return {
            "latest_query": result["refined_query"],
            "intent_description": result["describe_the_user_message_intent"],
            "skill": skill,
            "extracted_entities": result.get("key_entities", []),
            "requires_research": requires_research,
            # Reset per-turn state so previous turn's values don't carry over
            "is_satisfactory": False,
            "reflection_count": 0,
        }

    async def _enrich_kg(state: AgentState) -> tuple:
        """Resolve extracted entities against the knowledge graph. Returns (kg_context, entity_ids)."""
        entities = state.get("extracted_entities", [])
        if not entities or not db_session or not user_id:
            return ("", [])

        try:
            kg_context, entity_ids = await resolve_entities_from_query(
                entity_names=entities,
                user_id=user_id,
                db_session=db_session,
            )
            if kg_context:
                logger.info(f"KG enrichment found context for entities: {entities} (IDs: {entity_ids})")
            return (kg_context, entity_ids)
        except Exception as e:
            logger.warning(f"KG enrichment failed (non-fatal): {e}")
            return ("", [])

    async def _run_generate(state: AgentState, system_msg: str, run_name: str) -> dict:
        """Shared generation logic: injects intent + KG context and calls the LLM with tools."""
        messages = state["messages"]
        intent_desc = state.get("intent_description")
        refined_query = state.get("latest_query")
        kg_context = state.get("kg_context", "")
        skill = state.get("skill", default_skill)

        prompt_msgs = list(messages)

        # When a skill_override is active (slash command like /fact_check), check if the
        # user message is essentially just the slash command with no real content.
        # If so, replace it with a clear instruction the LLM can act on.
        skip_intent = bool(skill_override)
        if skip_intent:
            last_msg = prompt_msgs[-1]
            if isinstance(last_msg, HumanMessage):
                # Strip HTML tags and whitespace to check if there's real content beyond the command
                clean_text = re.sub(r'<[^>]*>', '', str(last_msg.content)).strip()
                # Remove the slash command itself to see if there's additional user text
                remaining = re.sub(r'^/\w+\s*', '', clean_text).strip()
                skill_cfg = get_skill(skill)
                slash_instruction = skill_cfg.slash_instruction if skill_cfg else ""
                if not remaining and slash_instruction:
                    # User sent just the slash command — replace with clear instruction
                    instruction = slash_instruction
                    if kg_context:
                        instruction += f"\n\n{kg_context}"
                    prompt_msgs[-1] = HumanMessage(content=instruction)
                elif kg_context:
                    prompt_msgs[-1] = HumanMessage(content=str(last_msg.content) + f"\n\n{kg_context}")
        elif (intent_desc or refined_query) or kg_context:
            last_msg = prompt_msgs[-1]
            if isinstance(last_msg, HumanMessage):
                context_block = "\n\n[Analysis Context]"
                if intent_desc:
                    context_block += f"\nIntent: {intent_desc}"
                if refined_query:
                    context_block += f"\nRefined Query: {refined_query}"
                if kg_context:
                    context_block += f"\n\n{kg_context}"
                prompt_msgs[-1] = HumanMessage(content=str(last_msg.content) + context_block)

        # Append a tool-usage reminder so the LLM doesn't skip tools when it should use them
        tool_names = [t.name for t in tools]
        tool_reminder = (
            "\n\nIMPORTANT — Available tools: " + ", ".join(tool_names) + ". "
            "If the user's question is NOT fully answerable from the CURRENT CONTEXT above, "
            "you MUST call the appropriate tool before answering. "
            "Use retrieve_documents_tool to search the user's library. "
            "Use google_search_tool to find information not in the library or document context."
        )
        system_msg += tool_reminder

        prompt_msgs = [SystemMessage(content=system_msg)] + prompt_msgs

        try:
            response = await llm_with_tools.ainvoke(prompt_msgs, config={"run_name": run_name})

            # Handle MALFORMED_FUNCTION_CALL: Gemini sometimes generates a tool call
            # that doesn't match the schema, returning empty content. Retry once without tools.
            finish_reason = response.response_metadata.get("finish_reason", "")
            if finish_reason == "MALFORMED_FUNCTION_CALL" or (not response.content and not response.tool_calls):
                logger.warning(f"Malformed LLM response (finish_reason={finish_reason}), retrying without tools")
                response = await llm.ainvoke(prompt_msgs, config={"run_name": f"{run_name}_retry"})
        except Exception as e:
            logger.error(f"LLM call failed in _run_generate ({run_name}): {e}", exc_info=True)
            # Return an error message as AIMessage so the graph doesn't crash silently
            response = AIMessage(content=f"I'm sorry, I encountered an error while processing your request. Please try again. (Error: {type(e).__name__})")

        return {"messages": [response]}

    async def generate_node(state: AgentState):
        """Unified generation: enriches KG context, resolves skill prompt, calls LLM."""
        # --- Phase 1: KG Enrichment (runs once per turn) ---
        kg_context = state.get("kg_context", "")
        context_entity_ids = state.get("context_entity_ids", [])

        # Only run KG enrichment on the first pass (kg_context still empty and entities exist)
        entities = state.get("extracted_entities", [])
        if entities and not kg_context:
            kg_context, context_entity_ids = await _enrich_kg(state)

        # --- Phase 2: Resolve skill prompt ---
        skill_key = state.get("skill", default_skill)
        skill_config = skills.get(skill_key, skills[default_skill])

        yaml_prompt = prompts.get(skill_config.prompt_type)
        if yaml_prompt:
            system_msg = yaml_prompt.system_prompt or ""
            if yaml_prompt.user_prompt:
                system_msg += f"\n\n{yaml_prompt.user_prompt}"
        elif skill_config.prompt_text:
            system_msg = skill_config.prompt_text
        else:
            logger.error(f"No prompt available for skill '{skill_key}' — returning error message")
            return {
                "messages": [AIMessage(content=f"I'm sorry, the '{skill_key}' skill is not properly configured. Please contact support.")],
                "kg_context": kg_context,
                "context_entity_ids": context_entity_ids,
            }

        # --- Phase 3: Call LLM (pass enriched state so _run_generate sees KG context) ---
        enriched_state = {**state, "kg_context": kg_context}
        result = await _run_generate(enriched_state, system_msg, run_name=skill_config.prompt_type)
        result["kg_context"] = kg_context
        result["context_entity_ids"] = context_entity_ids
        return result

    async def reflect_node(state: AgentState):
        """Critiques the answer and decides if search is needed."""
        messages = state["messages"]
        last_ai_msg = messages[-1]

        # If the last message was a tool call (not text), we skip reflection and go back to generate
        if hasattr(last_ai_msg, 'tool_calls') and last_ai_msg.tool_calls:
             return {"reflection_count": state.get("reflection_count", 0)}

        try:
            # Extract only the latest exchange: last human question + last AI response.
            # Using the full history caused the reflector to confuse old messages
            # (e.g. a prior single-word "France" turn) with the current AI response.
            last_human_msg = None
            last_ai_response = None
            for msg in reversed(messages):
                if isinstance(msg, AIMessage) and not msg.tool_calls and last_ai_response is None:
                    # Extract text content, handling both str and list-of-blocks formats
                    content = msg.content
                    if isinstance(content, list):
                        content = " ".join(
                            block.get("text", "") if isinstance(block, dict) else str(block)
                            for block in content
                        )
                    last_ai_response = content
                elif isinstance(msg, HumanMessage) and last_human_msg is None and last_ai_response is not None:
                    content = msg.content
                    if isinstance(content, list):
                        content = " ".join(
                            block.get("text", "") if isinstance(block, dict) else str(block)
                            for block in content
                        )
                    last_human_msg = content
                    break

            if not last_ai_response:
                logger.warning("reflect_node: no AI response found to evaluate — accepting as-is")
                return {
                            "reflection_count": state.get("reflection_count", 0) + 1,
                    "is_satisfactory": True,
                }

            # Role Swapping: Frame the conversation so the Reflector thinks the AI's answer is a Human submission
            # This helps the Reflector act as a "Teacher" grading a "Student"
            translated_messages = []
            if last_human_msg:
                translated_messages.append(AIMessage(content=last_human_msg))
            translated_messages.append(HumanMessage(content=last_ai_response))

            reflect_prompt = prompts.get(PromptType.CHAT_REFLECTION.value)
            if not reflect_prompt:
                logger.warning("Reflection prompt not found — skipping reflection, accepting answer as-is")
                return {
                            "reflection_count": state.get("reflection_count", 0) + 1,
                    "is_satisfactory": True,
                }

            system_prompt = reflect_prompt.system_prompt
            user_template = reflect_prompt.user_prompt or "Student Submission:\n{messages}"

            msgs_str = "\n\n".join([f"{m.type.upper()}: {m.content}" for m in translated_messages])

            try:
                user_content = user_template.format(messages=msgs_str)
            except Exception:
                user_content = f"Student Submission:\n{msgs_str}"

            prompt = ChatPromptTemplate.from_messages([
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_content)
            ])

            chain = prompt | llm.with_structured_output(ReflectionOutput)
            result = await chain.ainvoke(
                {"messages": translated_messages},
                config={"run_name": PromptType.CHAT_REFLECTION.value}
            )
        except Exception as e:
            logger.error(f"Reflection node failed: {e}", exc_info=True)
            # On reflection failure, accept the current answer rather than crashing
            return {
                    "reflection_count": state.get("reflection_count", 0) + 1,
                "is_satisfactory": True,
            }

        return {
            "reflection_count": state.get("reflection_count", 0) + 1,
            "is_satisfactory": result["is_satisfactory"],
            "messages": [HumanMessage(content=result["critique"])] if not result["is_satisfactory"] else []
        }

    async def dispatch_research_node(state: AgentState):
        """
        Dispatch the user's brief to the research multi-agent workflow.
        Creates a ResearchSession, runs the research graph, and appends the
        final synthesized response as an AIMessage.
        """
        from app.chat_workflows.research_multiagent_graph import (
            build_research_multiagent_graph,
            DEFAULT_MAX_SUBAGENTS,
            DEFAULT_MAX_TOOL_CALLS_PER_SUBAGENT,
            DEFAULT_MAX_CRITIC_LOOPS,
        )
        from app.models import ResearchSession
        from sqlalchemy import select

        brief = state.get("latest_query") or (
            state["messages"][-1].content if state.get("messages") else ""
        )

        # Create the ResearchSession row
        research_session_id = None
        if db_session and user_id:
            try:
                rs = ResearchSession(
                    user_id=user_id,
                    brief=brief,
                    status="running",
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
                logger.info(f"Created research_session={research_session_id} for brief: {brief[:80]}")
            except Exception as e:
                logger.error(f"Failed to create research session: {e}")

        if research_session_id is None:
            return {
                "messages": [AIMessage(content="Research dispatch failed: could not create research session.")],
                "is_satisfactory": True,
            }

        # Build and invoke the research graph (no checkpointer for v1 — research runs are short-lived)
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
            # Use a unique thread_id so this run doesn't collide with anything
            run_config = {"configurable": {"thread_id": f"research_{research_session_id}"}}
            final_state = await research_graph.ainvoke(initial_state, config=run_config)
            final_response = final_state.get("final_response", "Research completed but produced no response.")
            saved_doc_ids = final_state.get("saved_doc_ids", []) or []

            # Update research_session with results
            try:
                result = await db_session.execute(
                    select(ResearchSession).where(ResearchSession.id == research_session_id)
                )
                rs = result.scalar_one_or_none()
                if rs:
                    rs.status = "completed"
                    rs.final_response = final_response
                    rs.plan = {"sub_topics": final_state.get("plan", [])}
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

    # 3. Graph Construction
    from langgraph.prebuilt import ToolNode

    graph = StateGraph(AgentState)

    graph.add_node("intent_node", intent_node)
    graph.add_node("dispatch_research_node", dispatch_research_node)
    graph.add_node("generate_node", generate_node)
    graph.add_node("reflect_node", reflect_node)

    tools_node = ToolNode(tools, handle_tool_errors=True)
    graph.add_node("tools", tools_node)

    # Edges
    graph.add_edge(START, "intent_node")

    def route_after_intent(state: AgentState) -> str:
        """Dispatch to research workflow if intent classifier flagged it, else normal generation."""
        if state.get("requires_research"):
            return "dispatch_research_node"
        return "generate_node"

    graph.add_conditional_edges(
        "intent_node",
        route_after_intent,
        {"dispatch_research_node": "dispatch_research_node", "generate_node": "generate_node"},
    )
    graph.add_edge("dispatch_research_node", END)

    def route_after_generate(state: AgentState) -> str:
        """Route to tools if tool_calls present, otherwise reflect."""
        last_msg = state["messages"][-1]
        if last_msg.tool_calls:
            return "tools"
        return "reflect_node"

    graph.add_conditional_edges("generate_node", route_after_generate)
    graph.add_edge("tools", "generate_node")

    def route_after_reflect(state: AgentState) -> str:
        """Retry generate with critique or END."""
        if state["reflection_count"] > 3:
            return END
        if state.get("is_satisfactory"):
            return END
        return "generate_node"

    graph.add_conditional_edges("reflect_node", route_after_reflect)

    return graph.compile(checkpointer=checkpointer)
