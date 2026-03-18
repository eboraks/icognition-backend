"""
Quick test for Google Search API — uses the same code path as the chat agent.
Run from backend/: python scripts/test_google_search.py
"""
import asyncio
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import settings


def test_sync():
    """Test the GoogleSearchAPIWrapper directly (sync)."""
    from langchain_google_community import GoogleSearchAPIWrapper

    print(f"GOOGLE_SEARCH_API: {'SET' if settings.GOOGLE_SEARCH_API else 'MISSING'}")
    print(f"GOOGLE_CSE_ID:     {'SET' if settings.GOOGLE_CSE_ID else 'MISSING'}")

    if not settings.GOOGLE_SEARCH_API or not settings.GOOGLE_CSE_ID:
        print("\n❌ Missing credentials — google_search_tool would be None in the app.")
        return

    search = GoogleSearchAPIWrapper(
        google_api_key=settings.GOOGLE_SEARCH_API,
        google_cse_id=settings.GOOGLE_CSE_ID,
        k=3,
    )

    query = "Zineb Riboua author biography"
    print(f"\nSearching: '{query}'")
    try:
        results = search.results(query, 3)
        print(f"✅ Got {len(results)} results:\n")
        for i, r in enumerate(results, 1):
            print(f"  [{i}] {r.get('title', 'No Title')}")
            print(f"      {r.get('link', 'No Link')}")
            print(f"      {r.get('snippet', 'No Snippet')[:120]}")
            print()
    except Exception as e:
        print(f"❌ Search failed: {type(e).__name__}: {e}")


async def test_async_tool():
    """Test the actual @tool function used by the chat agent."""
    from app.chat_workflows.tools import get_google_search_tool

    tool = get_google_search_tool()
    if tool is None:
        print("\n❌ get_google_search_tool() returned None (missing credentials)")
        return

    print(f"\nTool name: {tool.name}")
    print(f"Tool is async: {tool.coroutine is not None if hasattr(tool, 'coroutine') else 'unknown'}")

    query = "Zineb Riboua author biography"
    print(f"Invoking tool with query: '{query}'")
    try:
        result = await tool.ainvoke({"query": query})
        print(f"✅ Tool returned ({len(result)} chars):\n")
        print(result[:500])
    except Exception as e:
        print(f"❌ Tool.ainvoke failed: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    print("=" * 60)
    print("TEST 1: Direct GoogleSearchAPIWrapper (sync)")
    print("=" * 60)
    test_sync()

    print("\n" + "=" * 60)
    print("TEST 2: @tool async function (same as chat agent)")
    print("=" * 60)
    asyncio.run(test_async_tool())
