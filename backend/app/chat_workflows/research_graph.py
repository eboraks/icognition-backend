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
    intent: str
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
        
        system_prompt = (
            "You are an expert intent classifier for a research assistant AI. "
            "Your job is to understand EXACTLY what the user wants to know. "
            "Pay close attention to potential ambiguities. "
            "For example, 'Is that statement true \"X\"?' usually means 'Verify if X is a fact', "
            "whereas 'Did person Y say \"X\"?' means 'Verify if the quote is attributed to Y'."
        )
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            ("human", "{input}"),
        ])
        
        classifier = prompt | llm.with_structured_output(IntentClassification)
        result = await classifier.ainvoke({"input": last_message})
        
        # Simple mapping to graph state intent for now, can be expanded
        # We default to document_qa unless it's clearly external or chatter
        intent_type = "document_qa"
        if "external" in result["describe_the_user_message_intent"].lower():
            intent_type = "external_research"
        elif "chat" in result["describe_the_user_message_intent"].lower():
            intent_type = "general_chat"
            
        return {"intent": intent_type, "latest_query": result["refined_query"]}

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

        # We manually construct the prompt to ensure system message is first
        prompt_msgs = [SystemMessage(content=system_msg)] + messages
        
        response = await llm_with_tools.ainvoke(prompt_msgs)
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

        prompt = ChatPromptTemplate.from_messages([
            ("system", "You are a strict teacher grading an AI's answer.\n"
                       "Check for:\n1. Hallucinations or unsupported claims.\n2. Missing critical information.\n3. Failed intent (didn't answer the question).\n"
                       "If the answer is excellent and accurate, set is_satisfactory=True.\n"
                       "If it needs improvement, set is_satisfactory=False and provide a detailed critique.\n"
                       "If external verification is needed, set needs_search=True and provide a query."),
            MessagesPlaceholder(variable_name="messages")
        ])
        
        chain = prompt | llm.with_structured_output(ReflectionOutput)
        # We pass the translated messages to the chain
        result = await chain.ainvoke({"messages": translated_messages})
        
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
