
import json

# Read the notebook
with open('notebooks/intent_based_chat_workflow.ipynb', 'r') as f:
    nb = json.load(f)

# The content to inject
new_code_content = """class ChatIntent(BaseModel):
    \"\"\"Structured representation of the user's intent.\"\"\"
    describe_the_user_message_intent: str = Field(
        description="Describe exactly what the user wants, including any skepticism or specific constraints."
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
    final_response: Optional[str]"""

# 1. Update the ChatIntent definition cell (Cell 3, index 3)
nb['cells'][3]['source'] = new_code_content.splitlines(keepends=True)

# 2. Update the determine_intent function (Cell 7, index 7) to reflect the new field names
new_determine_intent_source = """intent_llm = llm.with_structured_output(ChatIntent)

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
    print(f"Detected Intent: {intent.describe_the_user_message_intent}")
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
        f"\\n\\nUSER INTENT: {intent.describe_the_user_message_intent}"
        f"\\nREFINED QUERY/GOAL: {intent.refined_query}"
        "\\n\\nIf the user wants to FACT CHECK something, verify the claim itself against the documents, "
        "not just who said it (unless the claim is about who said it)."
    )
    
    # Create a simplified react agent for this node
    # In production, this would use the global checkpointer and cached agent service
    tools = [mock_retrieve_documents_tool]
    agent = create_react_agent(llm, tools, state_modifier=system_prompt)
    
    # We pass the original messages, but the system prompt (modifier) now guides the interpretation
    # Alternatively, we could inject a HumanMessage at the end with the refined query
    response = await agent.ainvoke({"messages": state["messages"]})
    
    return {
        "messages": response["messages"], 
        "final_response": response["messages"][-1].content
    }"""

nb['cells'][7]['source'] = new_determine_intent_source.splitlines(keepends=True)

# Write back to file
with open('notebooks/intent_based_chat_workflow.ipynb', 'w') as f:
    json.dump(nb, f, indent=4)

print("Notebook updated successfully.")
