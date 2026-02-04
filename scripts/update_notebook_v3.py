
import json

# Read the notebook (using the new v3 file)
with open('notebooks/intent_based_chat_workflow_v3.ipynb', 'r') as f:
    nb = json.load(f)

# 1. Update IMPORTS (Cell 1, index 1)
# We need to import create_react_agent from langgraph.prebuilt (which IS correct for 0.2+)
# BUT the user's error says "create_react_agent has been moved to langchain.agents" which suggests an older/mixed version environment
# OR they are using a very new langgraph where the signature changed.
# The error "TypeError: create_react_agent() got unexpected keyword arguments: {'state_modifier': ...}"
# suggests that the version of create_react_agent being called does NOT support state_modifier.

# Let's fix the import and the call.
# Use the generic `messages_modifier` instead of `state_modifier` if using the prebuilt agent,
# OR stick to the system prompt pattern supported by the specific version.

# Given the error, it seems we are hitting a version mismatch.
# Strategy: Use the prebuilt agent correctly. `state_modifier` was introduced in recent versions.
# If it fails, it might be an older version.
# However, the user also sees "LangGraphDeprecatedSinceV10".
# Let's try "checkpointer" or purely "messages_modifier" or just passing it as a system message in the messages list.

# SAFEST FIX: Don't rely on `state_modifier` kwarg if it's flaky in their version.
# Instead, Pre-pend the system message to the input messages.

new_agent_code = """async def run_agent(state: AgentState):
    print("--- RUNNING AGENT ---")
    intent: ChatIntent = state["intent"]
    
    # We construct a system prompt that includes the explicit intent context
    system_prompt = (
        "You are a helpful research assistant. "
        "You have access to a tool to retrieve documents from the user's library. "
        "Use the user's REFINED INTENT to guide your answer."
        f"\\n\\nUSER INTENT: {intent.describe_the_user_message_intent}"
        f"\\nREFINED QUERY/GOAL: {intent.refined_query}"
        "\\n\\nIf the user wants to FACT CHECK something, verify the claim itself against the documents, "
        "not just who said it (unless the claim is about who said it)."
    )
    
    # Create the agent
    # We use LangGraph's prebuilt agent but we pass the system prompt as a SystemMessage
    # in the input messages list, which is universally supported.
    tools = [mock_retrieve_documents_tool]
    agent = create_react_agent(llm, tools)
    
    # Prepend system prompt to messages
    messages = [SystemMessage(content=system_prompt)] + state["messages"]
    
    response = await agent.ainvoke({"messages": messages})
    
    return {
        "messages": response["messages"], 
        "final_response": response["messages"][-1].content
    }"""

nb['cells'][7]['source'] = new_agent_code.splitlines(keepends=True)

# Write back to file
with open('notebooks/intent_based_chat_workflow.ipynb', 'w') as f:
    json.dump(nb, f, indent=4)

print("Notebook updated successfully.")
