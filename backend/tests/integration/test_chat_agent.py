import asyncio
import pytest

from app.services.chat_agent_service import get_chat_agent_service
from app.services.chat_session_service import ChatSessionService
from app.db.database import get_session


TEST_USER_ID = "HqAXhad3jrUWmPibnMf1xZczNIq2"
TEST_PROMPTS = [
    "What we know about Thomas Sowell",
    "Where Thomas want to school?",
]


@pytest.mark.asyncio
async def test_chat_agent_generates_responses():
    """
    Integration test to ensure the chat agent can answer questions about Thomas Sowell.
    Requires that the database contains documents for the TEST_USER_ID.
    """
    async_gen = get_session()
    db_session = await async_gen.__anext__()
    chat_session_service = ChatSessionService(db_session)

    # Create a dedicated session for the test to avoid mutating existing chats
    chat_session = await chat_session_service.create_chat_session(
        user_id=TEST_USER_ID,
        title="LangGraph Thomas Sowell QA",
        scope_type="all_library",
        scope_id=None,
    )

    chat_agent = get_chat_agent_service()

    try:
        for prompt in TEST_PROMPTS:
            await chat_session_service.save_message(chat_session.id, "user", prompt)

            response_parts = []
            async for chunk in chat_agent.get_stream(chat_session.id, prompt, TEST_USER_ID):
                response_parts.append(chunk)

            response = "".join(response_parts).strip()
            assert response, f"Chat agent returned empty response for prompt: {prompt}"

            await chat_session_service.save_message(chat_session.id, "assistant", response)
    finally:
        await db_session.close()
        try:
            await async_gen.aclose()
        except Exception:
            pass

