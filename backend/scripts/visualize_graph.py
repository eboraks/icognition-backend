"""
Visualize the Research Graph structure.

Usage:
    cd backend
    python -m scripts.visualize_graph

Outputs:
    - Mermaid diagram to stdout (paste into https://mermaid.live)
    - PNG file at scripts/research_graph.png (if pygraphviz is installed)
"""

import sys
import os

# Add backend to path so imports work
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from langgraph.graph import END, START, StateGraph
from app.chat_workflows.research_graph import AgentState


def build_visualization_graph():
    """
    Build a lightweight graph with the same topology as the real research graph,
    but without requiring LLMs, tools, DB sessions, or prompts.
    """
    # Placeholder async nodes (never executed — just for graph structure)
    async def intent_node(state): ...
    async def generate_node(state): ...
    async def reflect_node(state): ...
    async def tools(state): ...

    graph = StateGraph(AgentState)

    graph.add_node("intent_node", intent_node)
    graph.add_node("generate_node", generate_node)
    graph.add_node("reflect_node", reflect_node)
    graph.add_node("tools", tools)

    # Edges (same topology as real graph)
    graph.add_edge(START, "intent_node")
    graph.add_edge("intent_node", "generate_node")

    graph.add_conditional_edges(
        "generate_node",
        lambda state: "tools",  # placeholder
        {"tools": "tools", "reflect_node": "reflect_node"},
    )

    graph.add_edge("tools", "generate_node")

    graph.add_conditional_edges(
        "reflect_node",
        lambda state: END,  # placeholder
        {END: END, "generate_node": "generate_node"},
    )

    return graph.compile()


def main():
    compiled = build_visualization_graph()
    drawable = compiled.get_graph()

    # Always print Mermaid
    mermaid = drawable.draw_mermaid()
    print("=== Mermaid Diagram ===")
    print("(Paste into https://mermaid.live to visualize)\n")
    print(mermaid)

    # Try PNG output
    try:
        output_path = os.path.join(os.path.dirname(__file__), "research_graph.png")
        png_bytes = drawable.draw_mermaid_png()
        with open(output_path, "wb") as f:
            f.write(png_bytes)
        print(f"\n=== PNG saved to {output_path} ===")
    except Exception as e:
        print(f"\n(PNG generation skipped: {e})")
        print("Install pygraphviz or use the Mermaid output above.")


if __name__ == "__main__":
    main()
