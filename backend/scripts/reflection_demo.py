import asyncio
import os
from typing import Annotated, List, Sequence

from dotenv import load_dotenv
from typing_extensions import TypedDict

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages

# Load environment variables
load_dotenv("backend/.env")

# --- Define the missing chains (Generate and Reflect) ---

# 1. Initialize the LLM
llm = ChatGoogleGenerativeAI(
    model=os.getenv("GEMINI_FLASH_MODEL"),
    google_api_key=os.getenv("GOOGLE_API_KEY"),
    convert_system_message_to_human=True, # Optional, depending on library version
)

# 2. Define the Generation Prompt and Chain
# The generator writes an essay and revises it based on feedback.
generation_prompt = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You are an essay assistant tasked with writing excellent 5-paragraph essays. "
            "Generate the best essay possible for the user's request. "
            "If the user provides critique, respond with a revised version of your previous attempts.",
        ),
        MessagesPlaceholder(variable_name="messages"),
    ]
)
generate = generation_prompt | llm

# 3. Define the Reflection Prompt and Chain
# The reflector acts as a teacher grading the essay.
reflection_prompt = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You are a teacher grading an essay submission. "
            "Generate critique and recommendations for the user's submission. "
            "Provide detailed recommendations, including requests for length, depth, style, etc.",
        ),
        MessagesPlaceholder(variable_name="messages"),
    ]
)
reflect = reflection_prompt | llm


# --- Replicate the Graph Definition (User's Snippet) ---


class State(TypedDict):
    messages: Annotated[list, add_messages]


async def generation_node(state: State) -> State:
    return {"messages": [await generate.ainvoke(state["messages"])]}


async def reflection_node(state: State) -> State:
    # Other messages we need to adjust
    cls_map = {"ai": HumanMessage, "human": AIMessage}
    # First message is the original user request. We hold it the same for all nodes
    translated = [state["messages"][0]] + [
        cls_map[msg.type](content=msg.content) for msg in state["messages"][1:]
    ]
    res = await reflect.ainvoke(translated)
    # We treat the output of this as human feedback for the generator
    return {"messages": [HumanMessage(content=res.content)]}


builder = StateGraph(State)
builder.add_node("generate", generation_node)
builder.add_node("reflect", reflection_node)
builder.add_edge(START, "generate")


def should_continue(state: State):
    if len(state["messages"]) > 6:
        # End after 3 iterations
        return END
    return "reflect"


builder.add_conditional_edges("generate", should_continue)
builder.add_edge("reflect", "generate")
memory = InMemorySaver()
graph = builder.compile(checkpointer=memory)


# --- Execution Script ---

async def main():
    print("Starting Reflection Demo with Gemini...")
    config = {"configurable": {"thread_id": "1"}}
    async for event in graph.astream(
        {
            "messages": [
                HumanMessage(
                    content="Generate an essay on the topicality of The Little Prince and its message in modern life"
                )
            ],
        },
        config,
    ):
        print(event)
        print("---")

if __name__ == "__main__":
    asyncio.run(main())
