import asyncio
import os
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, AIMessage
from langchain_core.tools import tool

# Load env before imports
load_dotenv("backend/.env")

from app.chat_workflows.research_graph import build_research_graph
from langgraph.checkpoint.memory import InMemorySaver

@tool
def mock_retrieve_documents(query: str) -> str:
    """Mock document retrieval."""
    print(f"   [TOOL] Retrieving documents for: {query}")
    if "company" in query.lower():
        return "Internal Doc 1: The Company revenue in 2021 was $5M."
    return "No relevant documents found."

async def main():
    print("--- Starting Research Graph Test ---")
    
    memory = InMemorySaver()
    graph = build_research_graph(checkpointer=memory, retrieve_tool=mock_retrieve_documents)
    
    # Test 1: Document Question
    print("\n\n=== TEST 1: Document Question ===")
    config = {"configurable": {"thread_id": "test_thread_1"}}
    inputs = {"messages": [HumanMessage(content="What was the company revenue in 2021?")]}
    
    async for event in graph.astream(inputs, config, stream_mode="values"):
        last_msg = event["messages"][-1]
        print(f"[{type(last_msg).__name__}]: {last_msg.content[:100]}...")

    # Test 2: External Question (Should trigger Search)
    print("\n\n=== TEST 2: External Question (needs search) ===")
    config = {"configurable": {"thread_id": "test_thread_2"}}
    # We ask something that definitely requires external knowledge AND the bot might try to look up in docs first.
    inputs = {"messages": [HumanMessage(content="Who won the Super Bowl in 2024?")]}
    
    async for event in graph.astream(inputs, config, stream_mode="values"):
        last_msg = event["messages"][-1]
        print(f"[{type(last_msg).__name__}]: {last_msg.content[:100]}...")
        if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
             print(f"   (Tool Call: {last_msg.tool_calls})")

if __name__ == "__main__":
    asyncio.run(main())
