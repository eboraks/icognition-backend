import re
from dataclasses import dataclass
from typing import Annotated, Any, Dict, List, Optional, TypedDict, Union, Literal

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.core.config import settings
from app.chat_workflows.tools import get_google_search_tool, create_retrieve_documents_tool, create_fetch_social_post_tool, create_world_context_tool
from app.services.prompt_service import PromptService
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

# --- Structured Outputs ---

class IntentClassification(TypedDict):
    describe_the_user_message_intent: str
    refined_query: str
    reasoning: str
    skill: Annotated[str, "One of: qa, social_post, email_draft, summary, fact_check"]
    key_entities: List[str]

# --- Skill Registry ---

@dataclass
class SkillConfig:
    prompt_type: PromptType
    node_name: str
    description: str
    fallback_prompt: Optional[str] = None

class ReflectionOutput(TypedDict):
    critique: str
    needs_search: bool
    search_query: str
    is_satisfactory: bool

_SOCIAL_WRITER_FALLBACK = (
    "You are an expert social media comment writer. Your task is to write thoughtful, "
    "engaging comments for social media posts and articles.\n\n"
    "The post content is provided in the CURRENT CONTEXT above under 'Document Content'. "
    "Use it directly — do not re-fetch the URL unless the content is missing or incomplete.\n"
    "If 'Document Content' is absent from the context but a URL is available, "
    "call `fetch_social_post_tool` with that URL to retrieve the content.\n\n"
    "CURRENT EVENTS ENRICHMENT:\n"
    "If the post touches on current events, geopolitics, breaking news, ongoing conflicts, "
    "elections, economic policy, or any time-sensitive topic, call `world_context_tool` "
    "with the main subject of the post (e.g. 'Israel Iran war', 'US tariffs 2026', "
    "'OpenAI GPT-5'). Use the returned headlines and snippets to make your comments "
    "specific and timely — reference what is actually happening in the world right now.\n\n"
    "When writing comments:\n"
    "1. Match the tone and style of the platform (professional for LinkedIn, "
    "conversational for Twitter/X, community-focused for Reddit)\n"
    "2. Reference specific points, arguments, or details from the post content\n"
    "3. Be authentic, concise, and add genuine value to the conversation\n"
    "4. If the user has relevant documents in their library, incorporate insights from them\n\n"
    "Provide 3 different comment options:\n"
    "- **Option A – Engaging**: Adds value and invites follow-up discussion\n"
    "- **Option B – Insightful**: Shares a related perspective, data point, or nuance\n"
    "- **Option C – Conversational**: Friendly tone that builds genuine connection\n\n"
    "Keep each option under 3 sentences unless the platform and content call for more depth."
)

_EMAIL_DRAFT_FALLBACK = (
    "You are a professional email drafting assistant. Your task is to write clear, "
    "well-structured emails based on the user's request.\n\n"
    "When drafting emails:\n"
    "1. Use an appropriate tone (formal, semi-formal, or casual) based on context\n"
    "2. Include a clear subject line suggestion\n"
    "3. Structure with greeting, body paragraphs, and sign-off\n"
    "4. If the user has relevant documents in their library, incorporate key points\n"
    "5. Keep it concise and action-oriented\n\n"
    "Provide 2 versions:\n"
    "- **Version A – Concise**: Straight to the point\n"
    "- **Version B – Detailed**: More context and nuance\n"
)

_SUMMARY_FALLBACK = (
    "You are a summarization expert. Your task is to create clear, comprehensive "
    "summaries of documents and topics from the user's knowledge library.\n\n"
    "When summarizing:\n"
    "1. Identify the core thesis or main points\n"
    "2. Preserve key facts, data, and arguments\n"
    "3. Use bullet points for clarity when appropriate\n"
    "4. Note any connections to other documents in the user's library\n"
    "5. Keep the summary to 20-30% of the original length\n"
)

_FACT_CHECK_FALLBACK = (
    "You are an expert fact-checker and critical analysis assistant. Your task is to "
    "evaluate claims, statements, and arguments for accuracy and reliability.\n\n"
    "IMPORTANT: The document to fact-check is provided in the CURRENT CONTEXT system message above. "
    "If the user's message is just '/fact_check' or a short command, fact-check the document "
    "from the CURRENT CONTEXT — do NOT ask for more information.\n\n"
    "MANDATORY TOOL USE:\n"
    "You MUST call `world_context_tool` and/or `google_search_tool` to verify claims. "
    "Do NOT rely solely on your training data. Always use at least one tool to check "
    "the key claims before providing your verdict.\n\n"
    "APPROACH:\n"
    "1. Identify the key claims or assertions in the content\n"
    "2. Call `world_context_tool` with the main topic to get current facts and context\n"
    "3. Call `google_search_tool` to verify specific statistics, dates, or disputed claims\n"
    "4. Cross-reference with the user's library documents using `retrieve_documents_tool` when relevant\n"
    "5. For each claim, assess whether it is supported, contested, or unsupported\n\n"
    "OUTPUT FORMAT:\n"
    "For each claim, provide:\n"
    "- **Claim**: The statement being evaluated\n"
    "- **Verdict**: Supported / Partially True / Misleading / Unsupported / False\n"
    "- **Evidence**: What supports or contradicts this claim (cite tool results)\n"
    "- **Context**: Important nuance or missing context\n\n"
    "End with an **Overall Assessment** that summarizes the reliability of the content "
    "and highlights the most important findings.\n\n"
    "Be balanced and evidence-based. Distinguish between factual errors and differences "
    "of opinion. When uncertain, say so explicitly rather than guessing."
)

SKILL_REGISTRY: Dict[str, SkillConfig] = {
    "qa": SkillConfig(
        prompt_type=PromptType.CHAT_AGENT_SYSTEM,
        node_name="generate_node",
        description="Default knowledge Q&A",
        fallback_prompt=None,  # required in DB — raises if missing
    ),
    "social_post": SkillConfig(
        prompt_type=PromptType.CHAT_SOCIAL_WRITER,
        node_name="social_generate_node",
        description="Social media comment writing",
        fallback_prompt=_SOCIAL_WRITER_FALLBACK,
    ),
    "email_draft": SkillConfig(
        prompt_type=PromptType.CHAT_SKILL_EMAIL_DRAFT,
        node_name="email_generate_node",
        description="Email drafting",
        fallback_prompt=_EMAIL_DRAFT_FALLBACK,
    ),
    "summary": SkillConfig(
        prompt_type=PromptType.CHAT_SKILL_SUMMARY,
        node_name="summary_generate_node",
        description="Document/topic summarization",
        fallback_prompt=_SUMMARY_FALLBACK,
    ),
    "fact_check": SkillConfig(
        prompt_type=PromptType.CHAT_SKILL_FACT_CHECK,
        node_name="fact_check_generate_node",
        description="Fact checking and claim verification",
        fallback_prompt=_FACT_CHECK_FALLBACK,
    ),
}

DEFAULT_SKILL = "qa"


# --- Knowledge Graph Entity Resolution ---

async def resolve_entities_from_query(
    entity_names: List[str],
    user_id: str,
    db_session: AsyncSession,
    similarity_threshold: float = 0.3,
    max_entities: int = 10,
) -> str:
    """
    Resolve a list of entity names against the knowledge graph using fuzzy matching.
    Returns a formatted string with matched entities and their relationships,
    ready to be injected into the LLM context.
    """
    if not entity_names:
        return ""

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
        return ""

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
        parts.append(f"  • [{e['type']}] {e['name']}{desc}")

    if relationships:
        parts.append("\nRelationships:")
        seen = set()
        for r in relationships:
            rel_key = (r["from_name"], r["relationship_type"], r["to_name"])
            if rel_key not in seen:
                seen.add(rel_key)
                parts.append(f"  • {r['from_name']} --[{r['relationship_type']}]--> {r['to_name']}")

    if entity_docs:
        parts.append("\nAppears in documents:")
        for ed in entity_docs:
            parts.append(f"  • {ed['entity_name']} → \"{ed['doc_title']}\"")

    return "\n".join(parts)


# --- Graph Builder Helper ---

# Type alias: maps PromptType.value strings to SimpleNamespace objects returned by PromptService.
GraphPrompts = Dict[str, Any]


async def fetch_graph_prompts(db_session) -> GraphPrompts:
    """
    Pre-fetch all prompts required by the research graph from the database.

    Call this once in the service layer (where a db_session already exists) and
    pass the resulting dict to build_research_graph().  This keeps the graph
    builder a pure, session-free function that is easy to unit-test.

    Raises ValueError if any required prompt is missing from the database.
    """
    prompt_service = PromptService(db_session)
    required = [
        PromptType.CHAT_INTENT_CLASSIFICATION,
        PromptType.CHAT_REFLECTION,
    ]
    prompts: GraphPrompts = {}
    for pt in required:
        prompt = await prompt_service.get_latest_prompt(pt.value)
        if prompt is None:
            raise ValueError(
                f"CRITICAL: Missing prompt '{pt.value}' in database. "
                "Cannot build research graph."
            )
        prompts[pt.value] = prompt

    # Fetch all skill prompts (optional — skills with fallback_prompt survive missing DB entries)
    for skill_key, skill_config in SKILL_REGISTRY.items():
        pt = skill_config.prompt_type
        if pt.value not in prompts:  # avoid re-fetching if already required
            skill_prompt = await prompt_service.get_latest_prompt(pt.value)
            if skill_prompt is not None:
                prompts[pt.value] = skill_prompt
            elif skill_config.fallback_prompt is None:
                raise ValueError(
                    f"CRITICAL: Missing prompt '{pt.value}' in database "
                    f"and skill '{skill_key}' has no fallback. Cannot build research graph."
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
                 All three prompt types (CHAT_INTENT_CLASSIFICATION,
                 CHAT_AGENT_SYSTEM, CHAT_REFLECTION) must be present.
        db_session: AsyncSession for KG entity resolution (optional).
        user_id: User ID for scoping KG queries (optional).
    """
    if prompts is None:
        raise ValueError(
            "build_research_graph() requires a 'prompts' dict. "
            "Call fetch_graph_prompts(db_session) first."
        )

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
            db_prompt = prompts.get(PromptType.CHAT_INTENT_CLASSIFICATION.value)
            if not db_prompt:
                logger.warning("Intent classification prompt not found in DB — using defaults")
                raise ValueError("Missing intent prompt")

            # Build a skill reference so the LLM knows the valid skill values
            skill_list = "\n".join(
                f'  - "{key}": {cfg.description}'
                for key, cfg in SKILL_REGISTRY.items()
            )
            skill_guidance = (
                f"\n\nYou MUST classify the `skill` field as one of these exact values:\n"
                f"{skill_list}\n"
                f'If the message does not clearly match a specific skill, use "qa".'
            )

            system_prompt = db_prompt.system_prompt + skill_guidance
            user_template = db_prompt.user_prompt or "{input}"

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
                "skill": skill_override or DEFAULT_SKILL,
                "key_entities": [],
            }

        # Use skill_override if provided (from slash commands), otherwise use classified skill
        if skill_override and skill_override in SKILL_REGISTRY:
            skill = skill_override
            logger.info(f"Using skill override: '{skill}'")
        else:
            raw_skill = result.get("skill", DEFAULT_SKILL)
            skill = raw_skill if raw_skill in SKILL_REGISTRY else DEFAULT_SKILL
            if raw_skill != skill:
                logger.warning(f"Unknown skill '{raw_skill}' from intent classification, falling back to '{DEFAULT_SKILL}'")

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
            return {"kg_context": ""}

        try:
            kg_context = await resolve_entities_from_query(
                entity_names=entities,
                user_id=user_id,
                db_session=db_session,
            )
            if kg_context:
                logger.info(f"KG enrichment found context for entities: {entities}")
            return {"kg_context": kg_context}
        except Exception as e:
            logger.warning(f"KG enrichment failed (non-fatal): {e}")
            return {"kg_context": ""}

    # Skill-specific instructions for when the user sends just a slash command
    # with no additional text. These replace the raw "/skill_name" with a clear
    # instruction the LLM can act on.
    # Every skill in SKILL_REGISTRY should have an entry here.
    SKILL_INSTRUCTIONS: Dict[str, str] = {
        "qa": (
            "Answer questions about the document provided in the CURRENT CONTEXT above. "
            "Use retrieve_documents_tool to find related documents in the user's library if needed."
        ),
        "fact_check": (
            "Fact-check the document provided in the CURRENT CONTEXT above. "
            "You MUST use world_context_tool and/or google_search_tool to verify the key claims. "
            "Do not rely on your training data alone."
        ),
        "summary": "Summarize the document provided in the CURRENT CONTEXT above.",
        "social_post": (
            "Write social media comments about the document provided in the CURRENT CONTEXT above. "
            "Use world_context_tool to get recent news context if the topic is time-sensitive."
        ),
        "email_draft": "Draft an email based on the document provided in the CURRENT CONTEXT above.",
    }

    # Validate that every registered skill has a corresponding instruction
    missing_instructions = set(SKILL_REGISTRY.keys()) - set(SKILL_INSTRUCTIONS.keys())
    if missing_instructions:
        logger.warning(
            f"Skills missing from SKILL_INSTRUCTIONS: {missing_instructions}. "
            "Bare slash commands for these skills will pass through as-is."
        )

    async def _run_generate(state: AgentState, system_msg: str, run_name: str) -> dict:
        """Shared generation logic: injects intent + KG context and calls the LLM with tools."""
        messages = state["messages"]
        intent_desc = state.get("intent_description")
        refined_query = state.get("latest_query")
        kg_context = state.get("kg_context", "")
        skill = state.get("skill", DEFAULT_SKILL)

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
                if not remaining and skill in SKILL_INSTRUCTIONS:
                    # User sent just the slash command — replace with clear instruction
                    instruction = SKILL_INSTRUCTIONS[skill]
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
        skill_config = SKILL_REGISTRY[skill_key]

        async def skill_generate_node(state: AgentState):
            db_prompt = prompts.get(skill_config.prompt_type.value)
            if db_prompt:
                system_msg = db_prompt.system_prompt
                if db_prompt.user_prompt:
                    system_msg += f"\n\n{db_prompt.user_prompt}"
            elif skill_config.fallback_prompt:
                system_msg = skill_config.fallback_prompt
            else:
                logger.error(f"No prompt available for skill '{skill_key}' — returning error message")
                return {"messages": [AIMessage(content=f"I'm sorry, the '{skill_key}' skill is not properly configured. Please contact support.")]}
            return await _run_generate(state, system_msg, run_name=skill_config.prompt_type.value)

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
            # Role Swapping: Frame the conversation so the Reflector thinks the AI's answer is a Human submission
            # This helps the Reflector act as a "Teacher" grading a "Student"
            cls_map = {"ai": HumanMessage, "human": AIMessage}
            translated_messages = []

            for msg in messages:
                msg_type = "ai" if isinstance(msg, AIMessage) else "human"
                if msg_type in cls_map:
                    translated_messages.append(cls_map[msg_type](content=msg.content))

            db_prompt = prompts.get(PromptType.CHAT_REFLECTION.value)
            if not db_prompt:
                logger.warning("Reflection prompt not found in DB — skipping reflection, accepting answer as-is")
                return {
                    "search_needed": False,
                    "reflection_count": state.get("reflection_count", 0) + 1,
                    "is_satisfactory": True,
                }

            system_prompt = db_prompt.system_prompt
            user_template = db_prompt.user_prompt or "Student Submission:\n{messages}"

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
        skill = state.get("skill", DEFAULT_SKILL)
        config = SKILL_REGISTRY.get(skill, SKILL_REGISTRY[DEFAULT_SKILL])
        return config.node_name

    graph = StateGraph(AgentState)

    graph.add_node("intent_node", intent_node)
    graph.add_node("enrich_kg_node", enrich_kg_node)
    graph.add_node("reflect_node", reflect_node)
    graph.add_node("google_search_node", google_search_node)

    # Register a generate node for each skill in the registry
    skill_node_names = []
    for skill_key in SKILL_REGISTRY:
        node_name = SKILL_REGISTRY[skill_key].node_name
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
