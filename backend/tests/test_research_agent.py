"""
Tests for the research multi-agent pipeline.

Runs against a live database and Tavily/Gemini APIs.
Requires: TAVILY_API_KEY, GOOGLE_API_KEY in env.

Usage:
    uv run pytest tests/test_research_agent.py -v -s
"""

import json
import pytest
from sqlalchemy import select

# conftest.py mocks Firebase before these imports
from app.db.database import async_session
from app.models import ResearchSession, Document
from app.services.prompt_service import get_prompt
from app.services.prompt_utils import PromptType

TEST_USER_ID = "HqAXhad3jrUWmPibnMf1xZczNIq2"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def create_research_session(brief: str, max_subagents: int = 2) -> int:
    """Create a ResearchSession row and return its id."""
    async with async_session() as session:
        rs = ResearchSession(
            user_id=TEST_USER_ID,
            brief=brief,
            status="running",
            budget={
                "max_subagents": max_subagents,
                "max_tool_calls_per_subagent": 3,
                "max_critic_loops": 0,
            },
        )
        session.add(rs)
        await session.commit()
        await session.refresh(rs)
        return rs.id


async def mark_research_complete(rs_id: int, final_response: str, plan: list):
    """Update a ResearchSession to completed."""
    async with async_session() as session:
        result = await session.execute(
            select(ResearchSession).where(ResearchSession.id == rs_id)
        )
        rs = result.scalar_one()
        rs.status = "completed"
        rs.final_response = final_response
        rs.plan = {"sub_topics": plan}
        await session.commit()


# ---------------------------------------------------------------------------
# 1. Prompt loading
# ---------------------------------------------------------------------------

class TestPrompts:
    def test_research_prompts_load(self):
        """All four research prompts must load from YAML."""
        for pt in [
            PromptType.CHAT_RESEARCH_PLANNER,
            PromptType.CHAT_RESEARCH_SUBAGENT,
            PromptType.CHAT_RESEARCH_COVERAGE_CRITIC,
            PromptType.CHAT_RESEARCH_WRITER,
        ]:
            prompt = get_prompt(pt.value)
            assert prompt is not None, f"Missing prompt: {pt.value}"
            assert prompt.system_prompt, f"Empty system_prompt for: {pt.value}"
            assert prompt.user_prompt, f"Empty user_prompt for: {pt.value}"

    def test_subagent_prompt_has_placeholders(self):
        """Subagent prompt must accept {sub_topic}, {brief}, {max_tool_calls}."""
        prompt = get_prompt(PromptType.CHAT_RESEARCH_SUBAGENT.value)
        text = prompt.system_prompt
        assert "{sub_topic}" in text
        assert "{brief}" in text
        assert "{max_tool_calls}" in text


# ---------------------------------------------------------------------------
# 2. Tavily tools
# ---------------------------------------------------------------------------

@pytest.mark.slow
class TestTavilyTools:
    @pytest.mark.asyncio
    async def test_tavily_search_returns_results(self):
        """Tavily search should return formatted results."""
        from app.chat_workflows.tavily_tools import get_tavily_search_tool

        tool = get_tavily_search_tool()
        if tool is None:
            pytest.skip("TAVILY_API_KEY not set")

        result = await tool.ainvoke({"query": "AI safety 2026", "topic": "general"})
        assert len(result) > 100, "Search result too short"
        assert "URL:" in result, "Should contain URLs"

    @pytest.mark.asyncio
    async def test_tavily_search_news_topic(self):
        """Tavily search with topic=news should work."""
        from app.chat_workflows.tavily_tools import get_tavily_search_tool

        tool = get_tavily_search_tool()
        if tool is None:
            pytest.skip("TAVILY_API_KEY not set")

        result = await tool.ainvoke({"query": "Iran negotiations", "topic": "news"})
        assert len(result) > 50

    @pytest.mark.asyncio
    async def test_tavily_extract_returns_content(self):
        """Tavily extract should return clean content from a URL."""
        from app.chat_workflows.tavily_tools import get_tavily_extract_tool

        tool = get_tavily_extract_tool()
        if tool is None:
            pytest.skip("TAVILY_API_KEY not set")

        result = await tool.ainvoke({"url": "https://en.wikipedia.org/wiki/Artificial_intelligence"})
        assert len(result) > 200, "Extract result too short"


# ---------------------------------------------------------------------------
# 3. Planner node
# ---------------------------------------------------------------------------

@pytest.mark.slow
class TestPlannerNode:
    @pytest.mark.asyncio
    async def test_planner_decomposes_brief(self):
        """Planner should decompose a brief into 1-3 sub-topics."""
        from app.chat_workflows.research_multiagent_graph import planner_node

        state = {
            "brief": "What are the economic consequences of the Iran-Israel conflict?",
            "budget": {"max_subagents": 3},
        }
        result = await planner_node(state)
        plan = result.get("plan", [])
        assert len(plan) >= 1, "Planner should produce at least 1 sub-topic"
        assert len(plan) <= 3, "Planner should produce at most 3 sub-topics"
        for item in plan:
            assert "topic" in item, "Each sub-topic must have a 'topic' field"

    @pytest.mark.asyncio
    async def test_planner_respects_budget(self):
        """Planner should not exceed max_subagents."""
        from app.chat_workflows.research_multiagent_graph import planner_node

        state = {
            "brief": "Comprehensive history of quantum computing, AI, and blockchain",
            "budget": {"max_subagents": 2},
        }
        result = await planner_node(state)
        plan = result.get("plan", [])
        assert len(plan) <= 2

    @pytest.mark.asyncio
    async def test_planner_simple_brief_few_topics(self):
        """A simple brief should produce few sub-topics (1-2)."""
        from app.chat_workflows.research_multiagent_graph import planner_node

        state = {
            "brief": "What is HDBSCAN?",
            "budget": {"max_subagents": 3},
        }
        result = await planner_node(state)
        plan = result.get("plan", [])
        assert 1 <= len(plan) <= 3, f"Expected 1-3 topics, got {len(plan)}"


# ---------------------------------------------------------------------------
# 4. Sub-agent
# ---------------------------------------------------------------------------

@pytest.mark.slow
class TestSubagent:
    @pytest.mark.asyncio
    async def test_subagent_searches_and_saves(self):
        """Sub-agent should search, extract, and save documents."""
        from app.chat_workflows.research_subagent import run_subagent

        rs_id = await create_research_session("Test subagent brief")

        async with async_session() as db_session:
            result = await run_subagent(
                sub_topic="OpenAI latest announcements April 2026",
                brief="Latest AI company news",
                user_id=TEST_USER_ID,
                db_session=db_session,
                research_session_id=rs_id,
                max_tool_calls=3,
            )

        assert result["sub_topic"] == "OpenAI latest announcements April 2026"
        assert result["tool_calls_used"] <= 3, "Should respect tool call budget"
        assert isinstance(result["findings_summary"], str)
        assert len(result["findings_summary"]) > 10, "Should produce a summary"

        # Verify docs were linked to research session
        if result["saved_doc_ids"]:
            async with async_session() as db_session:
                for doc_id in result["saved_doc_ids"]:
                    doc_result = await db_session.execute(
                        select(Document).where(Document.id == doc_id)
                    )
                    doc = doc_result.scalar_one()
                    assert doc.research_session_id == rs_id


# ---------------------------------------------------------------------------
# 5. End-to-end multi-agent graph
# ---------------------------------------------------------------------------

@pytest.mark.slow
class TestResearchGraph:
    @pytest.mark.asyncio
    async def test_full_research_pipeline(self):
        """End-to-end: planner -> sub-agents -> critic -> writer."""
        from app.chat_workflows.research_multiagent_graph import (
            build_research_multiagent_graph,
        )

        rs_id = await create_research_session(
            "What are the latest developments in AI regulation in Europe?",
            max_subagents=2,
        )

        graph = build_research_multiagent_graph(checkpointer=None)
        initial_state = {
            "brief": "What are the latest developments in AI regulation in Europe?",
            "user_id": TEST_USER_ID,
            "research_session_id": rs_id,
            "subagent_results": [],
            "critic_loops": 0,
            "budget": {
                "max_subagents": 2,
                "max_tool_calls_per_subagent": 3,
                "max_critic_loops": 0,
            },
        }

        final_state = await graph.ainvoke(
            initial_state,
            config={"configurable": {"thread_id": f"test_e2e_{rs_id}"}},
        )

        # Plan was generated
        plan = final_state.get("plan", [])
        assert len(plan) >= 1, "Should have at least 1 sub-topic"

        # Sub-agents ran
        results = final_state.get("subagent_results", [])
        assert len(results) >= 1, "Should have at least 1 sub-agent result"

        # Writer produced a response
        response = final_state.get("final_response", "")
        assert len(response) > 100, "Writer should produce a substantial response"

        # Mark complete
        await mark_research_complete(rs_id, response, plan)

        # Verify DB state
        async with async_session() as session:
            result = await session.execute(
                select(ResearchSession).where(ResearchSession.id == rs_id)
            )
            rs = result.scalar_one()
            assert rs.status == "completed"
            assert rs.final_response is not None

        print(f"\n{'='*60}")
        print(f"Research session {rs_id} completed")
        print(f"Plan: {len(plan)} sub-topics")
        print(f"Sub-agents: {len(results)} ran")
        total_docs = sum(len(r.get('saved_doc_ids', [])) for r in results)
        print(f"Documents saved: {total_docs}")
        print(f"Response length: {len(response)} chars")
        print(f"{'='*60}")
        print(f"\n{response[:500]}")


# ---------------------------------------------------------------------------
# 6. Research session DB operations
# ---------------------------------------------------------------------------

class TestResearchSessionDB:
    @pytest.mark.asyncio
    async def test_create_and_query_session(self):
        """Create a session and verify it's queryable."""
        rs_id = await create_research_session("Test DB brief")

        async with async_session() as session:
            result = await session.execute(
                select(ResearchSession).where(ResearchSession.id == rs_id)
            )
            rs = result.scalar_one()
            assert rs.brief == "Test DB brief"
            assert rs.status == "running"
            assert rs.user_id == TEST_USER_ID

    @pytest.mark.asyncio
    async def test_document_research_session_link(self):
        """Documents created by research should link back to the session."""
        rs_id = await create_research_session("Test doc link")

        async with async_session() as session:
            doc = Document(
                user_id=TEST_USER_ID,
                title="Test research doc",
                url="https://example.com/test",
                research_session_id=rs_id,
            )
            session.add(doc)
            await session.commit()
            await session.refresh(doc)

            assert doc.research_session_id == rs_id

            # Query docs by research session
            from sqlalchemy import text
            result = await session.execute(
                text("SELECT COUNT(*) FROM document WHERE research_session_id = :rs_id"),
                {"rs_id": rs_id},
            )
            count = result.scalar()
            assert count >= 1
