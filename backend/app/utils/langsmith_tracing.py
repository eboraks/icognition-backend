"""Utility helpers for LangSmith tracing integration."""

from __future__ import annotations

import os
from typing import Final

from app.core.config import settings
from app.utils.logging import get_logger

logger = get_logger(__name__)

_DEFAULT_ENDPOINT: Final[str] = "https://api.smith.langchain.com"


def enable_langsmith_tracing() -> None:
    """Enable LangSmith tracing when configured.

    The LangChain ecosystem reads configuration exclusively from environment
    variables. This helper mirrors the relevant settings so that tracing works
    even when the process is started without exporting the LangChain-specific
    variables ahead of time.
    """

    if not settings.LANGSMITH_TRACING:
        return

    if not settings.LANGSMITH_API_KEY:
        logger.warning(
            "LangSmith tracing requested but LANGSMITH_API_KEY is not set. "
            "Tracing will remain disabled."
        )
        return

    os.environ.setdefault("LANGSMITH_TRACING", "true")
    os.environ.setdefault("LANGSMITH_API_KEY", settings.LANGSMITH_API_KEY)

    endpoint = settings.LANGSMITH_ENDPOINT or _DEFAULT_ENDPOINT
    os.environ.setdefault("LANGSMITH_ENDPOINT", endpoint)

    if settings.LANGSMITH_PROJECT:
        os.environ.setdefault("LANGSMITH_PROJECT", settings.LANGSMITH_PROJECT)

    # LangChain still relies on the legacy variable names.
    os.environ.setdefault("LANGCHAIN_TRACING_V2", "true")
    os.environ.setdefault("LANGCHAIN_API_KEY", settings.LANGSMITH_API_KEY)
    os.environ.setdefault("LANGCHAIN_ENDPOINT", endpoint)

    if settings.LANGSMITH_PROJECT:
        os.environ.setdefault("LANGCHAIN_PROJECT", settings.LANGSMITH_PROJECT)

    logger.info(
        "LangSmith tracing enabled%s",
        f" for project '{settings.LANGSMITH_PROJECT}'"
        if settings.LANGSMITH_PROJECT
        else "",
    )

