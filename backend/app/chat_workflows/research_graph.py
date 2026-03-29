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
from app.services.prompt_service import get_prompt, get_all_skills, get_skill, get_default_skill
from app.services.prompt_utils import PromptType
from app.utils.logging import get_logger

logger = get_logger(__name__)

# --- State Definition ---

class AgentState(TypedDict):
    messages: Annotated[List[BaseMessage], add_messages]
    intent_description: str
    reflection_count: int
    search_needed: bool
    latest_query: str
    is_satisfactory: bool
    skill: str
    extracted_entities: List[str]
    kg_context: str
    context_entity_ids: List[int]
    context_document_ids: List[int]

# --- Structured Outputs ---

class IntentClassification(TypedDict):
    describe_the_user_message_intent: str
    refined_query: str
    reasoning: str
    skill: Annotated[str, "One of: qa, write_social_media_post, write_social_media_comment, email_draft, summary, fact_check"]
    key_entities: List[str]

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
            SELECT DISTINCT ON (e.name, e.type)
                   e.id, e.name, e.type, e.description,
                   similarity(e.name, :q) AS sim
            FROM entities e
            WHERE similarity(e.name, :q) >= :threshold
              AND (e.user_id = :user_id OR e.user_id IS NULL)
            ORDER BY e.name, e.type, sim DESC
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

    # Fetch relationships between/involving matched entities
    rels_sql = text("""
        SELECT r.relationship_type,
               e1.name AS from_name, e1.type AS from_type,
               e2.name AS to_name, e2.type AS to_type
        FROM entity_relationships r
        JOIN entities e1 ON e1.id = r.from_entity_id
        JOIN entities e2 ON e2.id = r.to_entity_id
        WHERE r.from_entity_id = ANY(:ids) OR r.to_entity_id = ANY(:ids)
        LIMIT 30
    """)
    rels_result = await db_session.execute(rels_sql, {"ids": all_entity_ids})
    relationships = rels_result.mappings().all()

    # Fetch documents linked to these entities
    docs_sql = text("""
        SELECT DISTINCT e.name AS entity_name, d.title AS doc_title
        FROM entity_documents ed
        JOIN entities e ON e.id = ed.entity_id
        JOIN document d ON d.id = ed.document_id
        WHERE ed.entity_id = ANY(:ids)
        ORDER BY e.name, d.title
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
        """Classifies the user's intent from the last message."""
        messages = state["messages"]
        last_message = messages[-1].content

        try:
            intent_prompt = prompts.get(PromptType.CHAT_INTENT_CLASSIFICATION.value)
            if not intent_prompt:
                logger.warning("Intent classification prompt not found — using defaults")
                raise ValueError("Missing intent prompt")

            # Build a skill reference so the LLM knows the valid skill values
            skill_list = "\n".join(
                f'  - "{key}": {cfg.description}'
                for key, cfg in skills.items()
            )
            skill_guidance = (
                f"\n\nYou MUST classify the `skill` field as one of these exact values:\n"
                f"{skill_list}\n"
                f'If the message does not clearly match a specific skill, use "{default_skill}".'
            )

            system_prompt = intent_prompt.system_prompt + skill_guidance
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
            # Fallback: use skill_override if available, otherwise default
            result = {
                "refined_query": str(last_message),
                "describe_the_user_message_intent": "",
                "skill": skill_override or default_skill,
                "key_entities": [],
            }

        # Use skill_override if provided (from slash commands), otherwise use classified skill
        if skill_override and skill_override in skills:
            skill = skill_override
            logger.info(f"Using skill override: '{skill}'")
        else:
            raw_skill = result.get("skill", default_skill)
            skill = raw_skill if raw_skill in skills else default_skill
            if raw_skill != skill:
                logger.warning(f"Unknown skill '{raw_skill}' from intent classification, falling back to '{default_skill}'")

        return {
            "latest_query": result["refined_query"],
            "intent_description": result["describe_the_user_message_intent"],
            "skill": skill,
            "extracted_entities": result.get("key_entities", []),
            # Reset per-turn state so previous turn's values don't carry over
            "is_satisfactory": False,
            "reflection_count": 0,
            "search_needed": False,
        }

    async def enrich_kg_node(state: AgentState):
        """Resolves extracted entity names against the knowledge graph and builds context."""
        entities = state.get("extracted_entities", [])
        if not entities or not db_session or not user_id:
            return {"kg_context": "", "context_entity_ids": []}

        try:
            kg_context, entity_ids = await resolve_entities_from_query(
                entity_names=entities,
                user_id=user_id,
                db_session=db_session,
            )
            if kg_context:
                logger.info(f"KG enrichment found context for entities: {entities} (IDs: {entity_ids})")
            return {"kg_context": kg_context, "context_entity_ids": entity_ids}
        except Exception as e:
            logger.warning(f"KG enrichment failed (non-fatal): {e}")
            return {"kg_context": "", "context_entity_ids": []}

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

    def _make_skill_generate_node(skill_key: str):
        """Factory: creates a generate node for a given skill key."""
        skill_config = skills[skill_key]

        async def skill_generate_node(state: AgentState):
            # First check if there's a prompt in the YAML prompt files (via prompt_type)
            yaml_prompt = prompts.get(skill_config.prompt_type)
            if yaml_prompt:
                system_msg = yaml_prompt.system_prompt or ""
                if yaml_prompt.user_prompt:
                    system_msg += f"\n\n{yaml_prompt.user_prompt}"
            elif skill_config.prompt_text:
                # Use the inline prompt_text from skills.yaml
                system_msg = skill_config.prompt_text
            else:
                logger.error(f"No prompt available for skill '{skill_key}' — returning error message")
                return {"messages": [AIMessage(content=f"I'm sorry, the '{skill_key}' skill is not properly configured. Please contact support.")]}
            return await _run_generate(state, system_msg, run_name=skill_config.prompt_type)

        skill_generate_node.__name__ = skill_config.node_name
        skill_generate_node.__qualname__ = skill_config.node_name
        return skill_generate_node

    async def reflect_node(state: AgentState):
        """Critiques the answer and decides if search is needed."""
        messages = state["messages"]
        last_ai_msg = messages[-1]

        # If the last message was a tool call (not text), we skip reflection and go back to generate
        if hasattr(last_ai_msg, 'tool_calls') and last_ai_msg.tool_calls:
             return {"search_needed": False, "reflection_count": state.get("reflection_count", 0)}

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
                    "search_needed": False,
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
                    "search_needed": False,
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
                "search_needed": False,
                "reflection_count": state.get("reflection_count", 0) + 1,
                "is_satisfactory": True,
            }

        return {
            "search_needed": result["needs_search"],
            "latest_query": result["search_query"],
            "reflection_count": state.get("reflection_count", 0) + 1,
            "is_satisfactory": result["is_satisfactory"],
            "messages": [HumanMessage(content=result["critique"])] if not result["is_satisfactory"] else []
        }

    async def google_search_node(state: AgentState):
        """Executes Google Search."""
        query = state["latest_query"]
        if not google_tool:
            return {"messages": [AIMessage(content="Search tool not available.")]}

        try:
            res = await google_tool.ainvoke({"query": query})
        except Exception:
            # Fallback to sync if ainvoke isn't available
            import asyncio
            res = await asyncio.to_thread(google_tool.func, query) if hasattr(google_tool, 'func') else "Search failed."
        return {"messages": [HumanMessage(content=f"SYSTEM NOTE: Google Search Results for '{query}':\n{res}")]}

    # 3. Graph Construction
    from langgraph.prebuilt import ToolNode

    def route_by_skill(state: AgentState) -> str:
        """Route to the appropriate generate node based on the classified skill."""
        skill = state.get("skill", default_skill)
        skill_cfg = skills.get(skill, skills[default_skill])
        return skill_cfg.node_name

    graph = StateGraph(AgentState)

    graph.add_node("intent_node", intent_node)
    graph.add_node("enrich_kg_node", enrich_kg_node)
    graph.add_node("reflect_node", reflect_node)
    graph.add_node("google_search_node", google_search_node)

    # Register a generate node for each skill in the registry
    skill_node_names = []
    for skill_key in skills:
        node_name = skills[skill_key].node_name
        graph.add_node(node_name, _make_skill_generate_node(skill_key))
        skill_node_names.append(node_name)

    tools_node = ToolNode(tools, handle_tool_errors=True)
    graph.add_node("tools", tools_node)

    graph.add_edge(START, "intent_node")
    graph.add_edge("intent_node", "enrich_kg_node")
    graph.add_conditional_edges("enrich_kg_node", route_by_skill)

    def route_after_generate(state: AgentState) -> str:
        """Route to tools if tool_calls present, otherwise reflect."""
        last_msg = state["messages"][-1]
        if last_msg.tool_calls:
            return "tools"
        return "reflect_node"

    # Each skill generate node routes the same way after generation
    for node_name in skill_node_names:
        graph.add_conditional_edges(node_name, route_after_generate)

    # Tools loop back to the correct skill's generate node
    graph.add_conditional_edges("tools", route_by_skill)

    def route_after_reflect(state: AgentState) -> str:
        """Route to google search, retry generate, or END."""
        if state["reflection_count"] > 3:
            return END
        if state.get("is_satisfactory"):
            return END
        if state["search_needed"]:
            return "google_search_node"
        # Not satisfactory: retry via skill router
        return route_by_skill(state)

    graph.add_conditional_edges("reflect_node", route_after_reflect)
    graph.add_conditional_edges("google_search_node", route_by_skill)

    return graph.compile(checkpointer=checkpointer)
