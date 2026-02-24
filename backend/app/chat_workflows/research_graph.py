from typing import Annotated, List, TypedDict, Union, Literal

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages

from app.core.config import settings
from app.chat_workflows.tools import get_google_search_tool, create_retrieve_documents_tool

# --- State Definition ---

class AgentState(TypedDict):
    messages: Annotated[List[BaseMessage], add_messages]
    intent_description: str
    reflection_count: int
    search_needed: bool
    latest_query: str
    is_satisfactory: bool

# --- Structured Outputs ---

class IntentClassification(TypedDict):
    describe_the_user_message_intent: str
    refined_query: str
    reasoning: str

class ReflectionOutput(TypedDict):
    critique: str
    needs_search: bool
    search_query: str
    is_satisfactory: bool

# --- Graph Builder Helper ---

def build_research_graph(checkpointer=None, retrieve_tool=None, db_session=None):
    """
    Builds the compiled StateGraph for the Reflective Research Agent.
    """
    
    # Imports inside function to avoid circular deps if needed, 
    # but we can assume PromptService is available
    from app.services.prompt_service import PromptService
    from app.services.prompt_utils import PromptType
    
    # 1. Initialize LLMs
    llm = ChatGoogleGenerativeAI(
        model=settings.GEMINI_FLASH_MODEL,
        google_api_key=settings.GOOGLE_API_KEY,
        temperature=0.1
    )
    
    # Tools
    google_tool = get_google_search_tool()
    tools = [retrieve_tool] if retrieve_tool else []
    if google_tool:
        tools.append(google_tool)
        
    llm_with_tools = llm.bind_tools(tools)

    # 2. Nodes

    async def intent_node(state: AgentState):
        """Classifies the user's intent from the last message."""
        messages = state["messages"]
        last_message = messages[-1].content
        
        # Fetch Intent Prompt from DB (STRICT)
        if not db_session:
             raise ValueError("CRITICAL: db_session is missing in intent_node. Cannot fetch prompts.")

        prompt_service = PromptService(db_session)
        db_prompt = await prompt_service.get_latest_prompt(PromptType.CHAT_INTENT_CLASSIFICATION.value)
        
        if not db_prompt:
             raise ValueError(f"CRITICAL: Missing prompt '{PromptType.CHAT_INTENT_CLASSIFICATION.value}' in database. Cannot proceed with intent classification.")

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
            "intent_description": result["describe_the_user_message_intent"]
        }

    async def generate_node(state: AgentState):
        """Generates an answer based on context and tools."""
        messages = state["messages"]
        
        # Fetch System Prompt from DB
        system_msg = "You are a helpful assistant."
        if db_session:
            try:
                prompt_service = PromptService(db_session)
                db_prompt = await prompt_service.get_latest_prompt(PromptType.CHAT_AGENT_SYSTEM.value)
                if db_prompt:
                    system_msg = db_prompt.system_prompt
                    if db_prompt.user_prompt:
                        system_msg += f"\n\n{db_prompt.user_prompt}"
            except Exception as e:
                print(f"Error fetching system prompt: {e}")

        # Append intent description and refined query to the last user message content
        # This ensures the model sees the intent as part of the immediate context
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
                
                # Create a new message with enhanced content for the prompt
                # We do this instead of modifying state directly to preserve history cleanliness if needed
                enhanced_msg = HumanMessage(content=str(last_msg.content) + context_block)
                prompt_msgs[-1] = enhanced_msg

        # We manually construct the prompt to ensure system message is first
        prompt_msgs = [SystemMessage(content=system_msg)] + prompt_msgs
        
        response = await llm_with_tools.ainvoke(
            prompt_msgs,
            config={"run_name": PromptType.CHAT_AGENT_SYSTEM.value}
        )
        return {"messages": [response]}

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

        # Fetch Reflection Prompt from DB (STRICT)
        if not db_session:
             raise ValueError("CRITICAL: db_session is missing in reflect_node. Cannot fetch prompts.")

        prompt_service = PromptService(db_session)
        db_prompt = await prompt_service.get_latest_prompt(PromptType.CHAT_REFLECTION.value)
        
        if not db_prompt:
             raise ValueError(f"CRITICAL: Missing prompt '{PromptType.CHAT_REFLECTION.value}' in database. Cannot proceed with reflection.")

        system_prompt = db_prompt.system_prompt
        # The user_prompt in DB is expected to be a template like "Student Submission:\n{messages}"
        # We need to format the messages into a string to fit this template
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
    
    graph = StateGraph(AgentState)
    
    graph.add_node("intent_node", intent_node)
    graph.add_node("generate_node", generate_node)
    graph.add_node("reflect_node", reflect_node)
    graph.add_node("google_search_node", google_search_node)
    
    # Standard tool node for retrieving documents
    tools_node = ToolNode(tools)
    graph.add_node("tools", tools_node)

    graph.add_edge(START, "intent_node")
    graph.add_edge("intent_node", "generate_node")
    
    def route_after_generate(state: AgentState):
        """Route to tools if tool_calls present, otherwise reflect."""
        last_msg = state["messages"][-1]
        if last_msg.tool_calls:
            return "tools"
        return "reflect_node"

    graph.add_conditional_edges("generate_node", route_after_generate)
    graph.add_edge("tools", "generate_node") # Loop back to generate after tool execution
    
    def route_after_reflect(state: AgentState):
        """Route to google search, generate (retry), or END."""
        # Use a safe-guard for max reflections to prevent infinite loops
        if state["reflection_count"] > 3:
            return END
            
        # If satisfactory, we are done
        if state.get("is_satisfactory"):
            return END

        if state["search_needed"]:
            return "google_search_node"
            
        # Otherwise, if not satisfactory and no search needed, we just loop back to generate (with the critique)
        return "generate_node"

    graph.add_conditional_edges("reflect_node", route_after_reflect)
    graph.add_edge("google_search_node", "generate_node")

    return graph.compile(checkpointer=checkpointer)
