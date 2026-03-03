"""
Unit tests for EmbeddingService.search_embeddings() — verifies that all runtime
values are passed as named bind parameters and never string-interpolated into SQL.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from typing import List


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_embedding_result(vector: List[float]):
    """Return a mock EmbeddingResult with a successful embedding."""
    result = MagicMock()
    result.success = True
    result.embedding = vector
    return result


def _capture_sql_calls(mock_session):
    """Return the list of (stmt_text, params) pairs passed to session.execute."""
    calls = []

    async def fake_execute(stmt, params=None):
        calls.append((str(stmt), params or {}))
        # Return a mock result with no rows
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        return mock_result

    mock_session.execute = fake_execute
    return calls


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestSearchEmbeddingsParameterized:
    """Verify that search_embeddings uses bind parameters, not string interpolation."""

    @pytest.fixture
    def embedding_service(self):
        """EmbeddingService with a mocked generate_embedding call."""
        with patch("app.services.embedding_service.settings") as mock_settings:
            mock_settings.DISABLE_AUTH = False
            mock_settings.GOOGLE_API_KEY = "fake-key"
            mock_settings.GEMINI_EMBEDDING_MODEL = "text-embedding-004"

            from app.services.embedding_service import EmbeddingService
            service = EmbeddingService.__new__(EmbeddingService)
            service.embedding_dimensions = 1536
            service.generate_embedding = AsyncMock(
                return_value=_make_mock_embedding_result([0.1] * 1536)
            )
            yield service

    @pytest.mark.asyncio
    async def test_query_vector_is_bound_parameter(self, embedding_service):
        """The query vector must appear as :query_vector bind param, never as a raw literal."""
        mock_session = MagicMock()
        calls = _capture_sql_calls(mock_session)

        await embedding_service.search_embeddings(
            session=mock_session,
            query_text="test query",
            user_id="user_123",
        )

        assert calls, "session.execute was never called"
        _, params = calls[0]
        assert "query_vector" in params, "query_vector must be a named bind parameter"
        # The value must be a string in pgvector format — never a Python list
        assert isinstance(params["query_vector"], str), "query_vector must be a string"
        assert params["query_vector"].startswith("["), "query_vector must start with '['"

    @pytest.mark.asyncio
    async def test_source_types_are_bound_parameters(self, embedding_service):
        """Each source_type value must be a named bind parameter (:source_type_0, etc.)."""
        mock_session = MagicMock()
        calls = _capture_sql_calls(mock_session)

        await embedding_service.search_embeddings(
            session=mock_session,
            query_text="test",
            user_id="user_123",
            source_types=["document", "entity"],
        )

        assert calls, "session.execute was never called"
        stmt_text, params = calls[0]

        # Both source types must be bound
        assert "source_type_0" in params
        assert "source_type_1" in params
        assert params["source_type_0"] in ("document", "entity")
        assert params["source_type_1"] in ("document", "entity")

        # The raw string values must NOT appear in the SQL template
        assert "'document'" not in stmt_text, "source type value must not be interpolated"
        assert "'entity'" not in stmt_text, "source type value must not be interpolated"

        # Placeholders must appear in the SQL template
        assert ":source_type_0" in stmt_text
        assert ":source_type_1" in stmt_text

    @pytest.mark.asyncio
    async def test_single_source_type_uses_single_placeholder(self, embedding_service):
        """Single source_type list produces exactly one :source_type_0 placeholder."""
        mock_session = MagicMock()
        calls = _capture_sql_calls(mock_session)

        await embedding_service.search_embeddings(
            session=mock_session,
            query_text="test",
            user_id="user_123",
            source_types=["document"],
        )

        stmt_text, params = calls[0]
        assert "source_type_0" in params
        assert "source_type_1" not in params
        assert ":source_type_0" in stmt_text

    @pytest.mark.asyncio
    async def test_user_id_is_bound_parameter(self, embedding_service):
        """user_id must be passed as a named bind parameter, not interpolated."""
        mock_session = MagicMock()
        calls = _capture_sql_calls(mock_session)

        await embedding_service.search_embeddings(
            session=mock_session,
            query_text="test",
            user_id="secret_user_id",
        )

        _, params = calls[0]
        assert "user_id" in params
        assert params["user_id"] == "secret_user_id"

    @pytest.mark.asyncio
    async def test_source_id_filter_is_bound_parameter(self, embedding_service):
        """:source_id must be a bind parameter when provided."""
        mock_session = MagicMock()
        calls = _capture_sql_calls(mock_session)

        await embedding_service.search_embeddings(
            session=mock_session,
            query_text="test",
            user_id="user_123",
            source_id=42,
        )

        stmt_text, params = calls[0]
        assert "source_id" in params
        assert params["source_id"] == 42
        assert ":source_id" in stmt_text

    @pytest.mark.asyncio
    async def test_cast_syntax_in_sql(self, embedding_service):
        """SQL must use CAST(:query_vector AS vector) not raw vector literal."""
        mock_session = MagicMock()
        calls = _capture_sql_calls(mock_session)

        await embedding_service.search_embeddings(
            session=mock_session,
            query_text="test",
            user_id="user_123",
        )

        stmt_text, _ = calls[0]
        assert "CAST(:query_vector AS vector)" in stmt_text
