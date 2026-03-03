from typing import Annotated, Any, Dict, List, Optional, TypedDict, Union, Literal

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages

from app.core.config import settings
from app.chat_workflows.tools import get_google_search_tool, create_retrieve_documents_tool, create_fetch_social_post_tool, create_world_context_tool
from app.services.prompt_service import PromptService
from app.services.prompt_utils import PromptType

# --- State Definition ---

class AgentState(TypedDict):
    messages: Annotated[List[BaseMessage], add_messages]
    intent_description: str
    reflection_count: int
    search_needed: bool
    latest_query: str
    is_satisfactory: bool
    is_social_writing: bool

# --- Structured Outputs ---

class IntentClassification(TypedDict):
    describe_the_user_message_intent: str
    refined_query: str
    reasoning: str
    is_social_writing: bool

class ReflectionOutput(TypedDict):
    critique: str
    needs_search: bool
    search_query: str
    is_satisfactory: bool

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
        PromptType.CHAT_AGENT_SYSTEM,
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

    # Optional: social writer prompt (falls back to hardcoded if not in DB)
    social_prompt = await prompt_service.get_latest_prompt(PromptType.CHAT_SOCIAL_WRITER.value)
    if social_prompt is not None:
        prompts[PromptType.CHAT_SOCIAL_WRITER.value] = social_prompt

    return prompts


def build_research_graph(
    checkpointer=None,
    retrieve_tool=None,
    kg_tool=None,
    prompts: Optional[GraphPrompts] = None,
):
    """
    Builds the compiled StateGraph for the Reflective Research Agent.

    Args:
        checkpointer: LangGraph checkpointer (e.g. AsyncPostgresSaver)
        retrieve_tool: LangChain tool for KB retrieval
        prompts: Pre-fetched prompt dict from fetch_graph_prompts().
                 All three prompt types (CHAT_INTENT_CLASSIFICATION,
                 CHAT_AGENT_SYSTEM, CHAT_REFLECTION) must be present.
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

        db_prompt = prompts[PromptType.CHAT_INTENT_CLASSIFICATION.value]
        system_prompt = db_prompt.system_prompt
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
        
          
        return {
            "latest_query": result["refined_query"],
            "intent_description": result["describe_the_user_message_intent"],
            "is_social_writing": result.get("is_social_writing", False),
        }

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

    async def _run_generate(state: AgentState, system_msg: str, run_name: str) -> dict:
        """Shared generation logic: injects intent context and calls the LLM with tools."""
        messages = state["messages"]
        intent_desc = state.get("intent_description")
        refined_query = state.get("latest_query")

        prompt_msgs = list(messages)
        if intent_desc or refined_query:
            last_msg = prompt_msgs[-1]
            if isinstance(last_msg, HumanMessage):
                context_block = "\n\n[Analysis Context]"
                if intent_desc:
                    context_block += f"\nIntent: {intent_desc}"
                if refined_query:
                    context_block += f"\nRefined Query: {refined_query}"
                prompt_msgs[-1] = HumanMessage(content=str(last_msg.content) + context_block)

        prompt_msgs = [SystemMessage(content=system_msg)] + prompt_msgs
        response = await llm_with_tools.ainvoke(prompt_msgs, config={"run_name": run_name})
        return {"messages": [response]}

    async def generate_node(state: AgentState):
        """Generates an answer for normal knowledge Q&A."""
        db_prompt = prompts[PromptType.CHAT_AGENT_SYSTEM.value]
        system_msg = db_prompt.system_prompt
        if db_prompt.user_prompt:
            system_msg += f"\n\n{db_prompt.user_prompt}"
        return await _run_generate(state, system_msg, run_name=PromptType.CHAT_AGENT_SYSTEM.value)

    async def social_generate_node(state: AgentState):
        """Generates social media comment drafts."""
        social_db_prompt = prompts.get(PromptType.CHAT_SOCIAL_WRITER.value)
        if social_db_prompt:
            system_msg = social_db_prompt.system_prompt
            if social_db_prompt.user_prompt:
                system_msg += f"\n\n{social_db_prompt.user_prompt}"
        else:
            system_msg = _SOCIAL_WRITER_FALLBACK
        return await _run_generate(state, system_msg, run_name=PromptType.CHAT_SOCIAL_WRITER.value)

    async def reflect_node(state: AgentState):
        """Critiques the answer and decides if search is needed."""
        messages = state["messages"]
        last_ai_msg = messages[-1]
        
        # If the last message was a tool call (not text), we skip reflection and go back to generate
        if last_ai_msg.tool_calls:
             return {"search_needed": False, "reflection_count": state.get("reflection_count", 0)}

        # Role Swapping: Frame the conversation so the Reflector thinks the AI's answer is a Human submission
        # This helps the Reflector act as a "Teacher" grading a "Student"
        cls_map = {"ai": HumanMessage, "human": AIMessage}
        translated_messages = []
        
        for msg in messages:
            # We want to preserve the system message if we had one in the list (though usually it's implicit)
            # But for the graph history, we typically have [Human, AI, Human, AI...]
            # The last message is AI (the one we want to critique).
            # We swap it to HumanMessage.
            # We swap previous HumanMessages to AIMessages (context).
            msg_type = "ai" if isinstance(msg, AIMessage) else "human"
            if msg_type in cls_map:
                translated_messages.append(cls_map[msg_type](content=msg.content))
            else:
                # System messages or Tool messages -> keep as is or skip if confusing?
                # For simplicity, we just keep content if possible, or skip strictly tool messages 
                # that might confuse the simple reflection prompt.
                # Actually, SystemMessage should stay SystemMessage (but we inject our own teacher prompt).
                pass

        db_prompt = prompts[PromptType.CHAT_REFLECTION.value]
        system_prompt = db_prompt.system_prompt
        # The user_prompt in DB is expected to be a template like "Student Submission:\n{messages}"
        user_template = db_prompt.user_prompt or "Student Submission:\n{messages}"
        
        # Convert translated messages to a string representation for the teacher
        # We format them clearly as "Role: Content"
        msgs_str = "\n\n".join([f"{m.type.upper()}: {m.content}" for m in translated_messages])
        
        try:
            user_content = user_template.format(messages=msgs_str)
        except Exception:
            # Fallback if format fails but we must be strict about the prompt existing
            user_content = f"Student Submission:\n{msgs_str}"

        # Use Message objects directly to prevent LangChain from interpreting content as templates
        prompt = ChatPromptTemplate.from_messages([
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_content)
        ])
        
        chain = prompt | llm.with_structured_output(ReflectionOutput)
        # We pass the translated messages to the chain (though prompt is already formatted)
        # Add run_name for Langfuse
        result = await chain.ainvoke(
            {"messages": translated_messages},
            config={"run_name": PromptType.CHAT_REFLECTION.value}
        )
        
        # LOGIC:
        # If is_satisfactory is True -> we are done.
        # If is_satisfactory is False -> we pass the critique back to the Generator.
        # CRITIQUE AS HUMAN MESSAGE: The generator will see this as a user saying "Please fix X".
        
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
            
        res = google_tool.func(query)
        # return as a ToolMessage or just context in a HumanMessage "System Note" style
        # For simplicity in this custom graph, we'll inject it as a visible system note for the next generation.
        return {"messages": [HumanMessage(content=f"SYSTEM NOTE: Google Search Results for '{query}':\n{res}")]}

    # 3. Graph Construction
    from langgraph.prebuilt import ToolNode

    def route_to_generate(state: AgentState) -> str:
        """Route to the appropriate generate node based on social writing intent."""
        return "social_generate_node" if state.get("is_social_writing", False) else "generate_node"

    graph = StateGraph(AgentState)

    graph.add_node("intent_node", intent_node)
    graph.add_node("generate_node", generate_node)
    graph.add_node("social_generate_node", social_generate_node)
    graph.add_node("reflect_node", reflect_node)
    graph.add_node("google_search_node", google_search_node)

    tools_node = ToolNode(tools)
    graph.add_node("tools", tools_node)

    graph.add_edge(START, "intent_node")
    graph.add_conditional_edges("intent_node", route_to_generate)

    def route_after_generate(state: AgentState) -> str:
        """Route to tools if tool_calls present, otherwise reflect."""
        last_msg = state["messages"][-1]
        if last_msg.tool_calls:
            return "tools"
        return "reflect_node"

    graph.add_conditional_edges("generate_node", route_after_generate)
    graph.add_conditional_edges("social_generate_node", route_after_generate)
    graph.add_conditional_edges("tools", route_to_generate)  # loop back to the right generate node

    def route_after_reflect(state: AgentState) -> str:
        """Route to google search, retry generate, or END."""
        if state["reflection_count"] > 3:
            return END
        if state.get("is_satisfactory"):
            return END
        if state["search_needed"]:
            return "google_search_node"
        # Not satisfactory: retry the appropriate generate node
        return route_to_generate(state)

    graph.add_conditional_edges("reflect_node", route_after_reflect)
    graph.add_conditional_edges("google_search_node", route_to_generate)

    return graph.compile(checkpointer=checkpointer)
