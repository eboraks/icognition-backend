import os
import sys
from typing import List, Dict, TypedDict, Optional, Literal, Annotated
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage, BaseMessage
from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import StateGraph, END, START
from langgraph.graph.message import add_messages
from langgraph.prebuilt import create_react_agent
from langchain_core.tools import tool, Tool
from pydantic import BaseModel, Field
import asyncio

# Add backend to path to import models
sys.path.append(os.path.abspath('backend'))
# Mock missing imports if necessary, or ensure we run from root
# Assuming we run from project root

from app.models import LLMContentExtraction, PageType
# We might not need DB access for this mock test if we mock the tools and prompts completely, 
# but the notebook imports them so let's try to include them. 
# If they fail due to async loop issues in script vs notebook, we'll see.
# For simplicity in this script, I'll mock the DB dependencies if I can, but let's try real imports first.

# Load environment variables
if os.path.exists('backend/.env'):
    load_dotenv('backend/.env')
else:
    load_dotenv('.env')

api_key = os.getenv("GOOGLE_API_KEY")
llm_model_name = os.getenv("GEMINI_FLASH_MODEL")

if not api_key:
    print("WARNING: GOOGLE_API_KEY not found!")
    sys.exit(1)

# Initialize LLM
llm = ChatGoogleGenerativeAI(model=llm_model_name, google_api_key=api_key)

# --- 1. Define State and Schema ---

class ChatIntent(BaseModel):
    """Structured representation of the user's intent."""
    intent_type: Literal["FACT_CHECK", "SEARCH", "CHAT", "SUMMARIZATION"] = Field(
        description="The primary category of the user's request."
    )
    refined_query: str = Field(
        description="A refined, unambiguous version of the user's query that captures their true intent."
    )
    reasoning: str = Field(
        description="Brief explanation of why this intent was chosen."
    )

class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    intent: Optional[ChatIntent]
    final_response: Optional[str]

# --- 2. Mock Retrieval Tool ---

@tool
def mock_retrieve_documents_tool(query: str) -> str:
    """
    Retrieves relevant documents from the user's library.
    """
    # Simulating the specific article mentioned in the user request
    return """
    Found 1 relevant document:
    Title: Subscriptions | Substack
    URL: https://substack.com/inbox/post/184937786
    Content Chunk: Former Associated Press reporter Matti Friedman observed that AP employed more full-time journalists covering Israel than it did covering China, India, and Russia combined.
    """

# --- 3. Define Nodes ---

intent_llm = llm.with_structured_output(ChatIntent)

async def determine_intent(state: AgentState):
    print("--- DETERMINING INTENT ---")
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
        ("user", last_message)
    ])
    
    intent = await intent_llm.ainvoke(prompt.format())
    print(f"Detected Intent: {intent.intent_type}")
    print(f"Refined Query: {intent.refined_query}")
    print(f"Reasoning: {intent.reasoning}")
    
    return {"intent": intent}

async def run_agent(state: AgentState):
    print("--- RUNNING AGENT ---")
    intent: ChatIntent = state["intent"]
    
    # We construct a system prompt that includes the explicit intent context
    system_prompt = (
        "You are a helpful research assistant. "
        "You have access to a tool to retrieve documents from the user's library. "
        "Use the user's REFINED INTENT to guide your answer."
        f"\n\nUSER INTENT TYPE: {intent.intent_type}"
        f"\nREFINED QUERY/GOAL: {intent.refined_query}"
        "\n\nIf the user wants to FACT CHECK something, verify the claim itself against the documents, "
        "not just who said it (unless the claim is about who said it)."
    )
    
    # Create a simplified react agent for this node
    tools = [mock_retrieve_documents_tool]
    agent = create_react_agent(llm, tools, prompt=system_prompt)
    
    response = await agent.ainvoke({"messages": state["messages"]})
    
    return {
        "messages": response["messages"], 
        "final_response": response["messages"][-1].content
    }

# --- 4. Build Graph ---

workflow = StateGraph(AgentState)

workflow.add_node("intent_classifier", determine_intent)
workflow.add_node("agent", run_agent)

workflow.add_edge(START, "intent_classifier")
workflow.add_edge("intent_classifier", "agent")
workflow.add_edge("agent", END)

app = workflow.compile()

# --- 5. Test with User Example ---

async def main():
    user_query = 'Is that statement is true "Former Associated Press reporter Matti Friedman observed that AP employed more full-time journalists covering Israel than it did covering China, India, and Russia combined." ?'

    print("User Query:", user_query)
    print("-" * 50)

    inputs = {"messages": [HumanMessage(content=user_query)]}

    async for chunk in app.astream(inputs):
        for node_name, node_output in chunk.items():
            if node_name == "agent":
                print(f"\nFinal Answer:\n{node_output['final_response']}")

if __name__ == "__main__":
    asyncio.run(main())
