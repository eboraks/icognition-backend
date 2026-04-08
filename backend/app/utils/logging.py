"""
Logging configuration for iCognition Backend

Logs are written to both stderr (console) and rotating files in backend/logs/:
  - app.log     — all log output (INFO+)
  - error.log   — errors and warnings only
  - kg.log      — KG pipeline logs only (kg_pipeline, kg_adapter, schema_alignment_service)
"""

import logging
import sys
import os
from logging.handlers import RotatingFileHandler
from typing import Optional
from app.core.config import settings

# Log directory relative to backend/
LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "logs")

# KG-related module names (matched against logger name)
KG_MODULES = {"kg_pipeline", "kg_adapter", "schema_alignment_service", "wikidata_service"}

# Shared formatter
_LOG_FORMAT = '%(asctime)s - %(filename)s - %(lineno)d - %(levelname)s - %(message)s'
_LOG_DATEFMT = '%Y-%m-%d %H:%M:%S'


def _ensure_log_dir():
    os.makedirs(LOG_DIR, exist_ok=True)


def _make_formatter() -> logging.Formatter:
    return logging.Formatter(_LOG_FORMAT, datefmt=_LOG_DATEFMT)


def _get_file_handler(filename: str, level: int = logging.INFO, max_bytes: int = 10_000_000, backup_count: int = 5) -> RotatingFileHandler:
    """Create a rotating file handler."""
    _ensure_log_dir()
    handler = RotatingFileHandler(
        os.path.join(LOG_DIR, filename),
        maxBytes=max_bytes,
        backupCount=backup_count,
    )
    handler.setLevel(level)
    handler.setFormatter(_make_formatter())
    return handler


class _KGFilter(logging.Filter):
    """Only pass records from KG-related modules."""
    def filter(self, record: logging.LogRecord) -> bool:
        return any(mod in record.name for mod in KG_MODULES)


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """
    Get a logger instance with consistent formatting.
    Logs go to console + app.log + error.log.
    KG-related loggers also write to kg.log.
    """
    if name is None:
        name = "icognition"

    logger = logging.getLogger(name)

    # Only configure if not already configured
    if not logger.handlers:
        # Console handler
        console = logging.StreamHandler(sys.stderr)
        console.setLevel(logging.INFO)
        console.setFormatter(_make_formatter())
        logger.addHandler(console)

        # app.log — all output
        logger.addHandler(_get_file_handler("app.log", logging.INFO))

        # error.log — warnings and errors only
        logger.addHandler(_get_file_handler("error.log", logging.WARNING))

        # kg.log — KG modules only
        if any(mod in name for mod in KG_MODULES):
            logger.addHandler(_get_file_handler("kg.log", logging.INFO))

        logger.setLevel(logging.INFO)
        logger.propagate = False

    return logger


def configure_logging():
    """Configure root logging for the application"""
    _ensure_log_dir()

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    # Remove existing handlers to avoid duplicates
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Console
    console = logging.StreamHandler(sys.stderr)
    console.setLevel(logging.INFO)
    console.setFormatter(_make_formatter())
    root_logger.addHandler(console)

    # app.log
    root_logger.addHandler(_get_file_handler("app.log", logging.INFO))

    # error.log
    root_logger.addHandler(_get_file_handler("error.log", logging.WARNING))

    # kg.log — filtered to KG modules only
    kg_handler = _get_file_handler("kg.log", logging.INFO)
    kg_handler.addFilter(_KGFilter())
    root_logger.addHandler(kg_handler)

    logger = get_logger()
    logger.info("Logging configured successfully")

    return logger
