import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from app.services.chat_agent_service import ChatAgentService
from app.core.config import settings
from langchain_core.messages import AIMessage

@pytest.mark.asyncio
async def test_chat_agent_initialization_with_google_search():
    """Test that the agent initializes with Google Search tool when configuration is present."""
    
    # Mock dependencies
    with patch("app.services.chat_agent_service.settings") as mock_settings, \
         patch("app.services.chat_agent_service.ChatGoogleGenerativeAI") as mock_llm, \
         patch("app.services.chat_agent_service.create_react_agent") as mock_create_agent, \
         patch("app.services.chat_agent_service.get_session") as mock_get_session, \
         patch("app.services.chat_agent_service.ChatSessionService") as mock_session_service, \
         patch("app.services.prompt_service.PromptService") as mock_prompt_service, \
         patch("app.services.chat_agent_service.get_checkpointer") as mock_get_checkpointer, \
         patch("app.services.chat_agent_service.create_retrieve_documents_tool") as mock_create_retrieve_tool:

        # Setup mocks
        mock_settings.GOOGLE_SEARCH_API = "fake_api_key"
        mock_settings.GOOGLE_CSE_ID = "fake_cse_id"
        mock_settings.GEMINI_FLASH_MODEL = "models/gemini-2.0-flash"
        mock_settings.GOOGLE_API_KEY = "fake_google_api_key"

        mock_db_session = AsyncMock()
        mock_get_session.return_value.__anext__.return_value = mock_db_session

        mock_chat_session = MagicMock()
        mock_chat_session.scope_type = "document"
        mock_chat_session.scope_id = 1
        mock_chat_session.thread_id = "test_thread"
        
        mock_session_service_inst = MagicMock()
        mock_session_service_inst.get_session_by_id = AsyncMock(return_value=mock_chat_session)
        mock_session_service.return_value = mock_session_service_inst

        # Mock PromptService to return None (fallback to hardcoded)
        mock_prompt_service_inst = MagicMock()
        mock_prompt_service_inst.get_latest_prompt = AsyncMock(return_value=None)
        mock_prompt_service.return_value = mock_prompt_service_inst

        mock_get_checkpointer.return_value = AsyncMock()
        
        # Mock retrieve tool
        mock_retrieve_tool = MagicMock()
        mock_create_retrieve_tool.return_value = mock_retrieve_tool

        # Mock agent.astream
        mock_agent = MagicMock()
        mock_agent.astream = AsyncMock()
        mock_create_agent.return_value = mock_agent

        service = ChatAgentService()
        
        # Run stream (it's a generator)
        async for chunk in service.get_stream(session_id=1, message="test", user_id="user1"):
            pass

        # Verify create_react_agent was called
        assert mock_create_agent.called
        args, kwargs = mock_create_agent.call_args
        tools = kwargs.get("tools")
        
        assert len(tools) == 2
        tool_names = [getattr(t, "name", str(t)) for t in tools]
        assert any("google_search" in name for name in tool_names)
        
        # Verify system prompt grounding instructions are present
        system_prompt = kwargs.get("prompt")
        assert "google_search_tool" in system_prompt
        assert "GROUND" in system_prompt
        assert "augment or validate" in system_prompt

@pytest.mark.asyncio
async def test_chat_agent_no_google_search_when_missing_config():
    """Test that the agent DOES NOT initialize Google Search tool when config is missing."""
    
    # Mock settings
    with patch("app.services.chat_agent_service.settings") as mock_settings, \
         patch("app.services.chat_agent_service.ChatGoogleGenerativeAI") as mock_llm, \
         patch("app.services.chat_agent_service.create_react_agent") as mock_create_agent, \
         patch("app.services.chat_agent_service.get_session") as mock_get_session, \
         patch("app.services.chat_agent_service.ChatSessionService") as mock_session_service, \
         patch("app.services.prompt_service.PromptService") as mock_prompt_service, \
         patch("app.services.chat_agent_service.get_checkpointer") as mock_get_checkpointer, \
         patch("app.services.chat_agent_service.create_retrieve_documents_tool") as mock_create_retrieve_tool:

        # Setup mocks: NO Google Search API keys
        mock_settings.GOOGLE_SEARCH_API = None
        mock_settings.GOOGLE_CSE_ID = None
        mock_settings.GEMINI_FLASH_MODEL = "models/gemini-2.0-flash"
        mock_settings.GOOGLE_API_KEY = "fake_google_api_key"

        mock_db_session = AsyncMock()
        mock_get_session.return_value.__anext__.return_value = mock_db_session

        mock_chat_session = MagicMock()
        mock_chat_session.scope_type = "document"
        mock_chat_session.scope_id = 1
        mock_chat_session.thread_id = "test_thread"
        
        mock_session_service_inst = MagicMock()
        mock_session_service_inst.get_session_by_id = AsyncMock(return_value=mock_chat_session)
        mock_session_service.return_value = mock_session_service_inst

        mock_prompt_service_inst = MagicMock()
        mock_prompt_service_inst.get_latest_prompt = AsyncMock(return_value=None)
        mock_prompt_service.return_value = mock_prompt_service_inst

        mock_get_checkpointer.return_value = AsyncMock()
        
        mock_agent = MagicMock()
        mock_agent.astream = AsyncMock()
        mock_create_agent.return_value = mock_agent

        service = ChatAgentService()
        
        async for chunk in service.get_stream(session_id=1, message="test", user_id="user1"):
            pass

        # Verify create_react_agent was called with ONLY retrieve tool
        assert mock_create_agent.called
        args, kwargs = mock_create_agent.call_args
        tools = kwargs.get("tools")
        
        assert len(tools) == 1
        tool_names = [getattr(t, "name", str(t)) for t in tools]
        assert not any("google_search" in name for name in tool_names)
