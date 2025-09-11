"""
Logging configuration for iCognition Backend
"""

import logging
import sys
from typing import Optional
from app.core.config import settings


class LogConfig:
    """Logging configuration class"""
    
    LOGGER_NAME: str = "icognition"
    LOG_FORMAT: str = "%(levelprefix)s | %(asctime)s | %(name)s | %(message)s"
    LOG_LEVEL: str = settings.LOG_LEVEL
    
    # Logging config
    version: int = 1
    disable_existing_loggers: bool = False
    
    formatters: dict = {
        "default": {
            "()": "uvicorn.logging.DefaultFormatter",
            "fmt": LOG_FORMAT,
            "datefmt": "%Y-%m-%d %H:%M:%S",
        },
        "detailed": {
            "()": "uvicorn.logging.DefaultFormatter",
            "fmt": "%(levelprefix)s | %(asctime)s | %(name)s | %(filename)s:%(lineno)d | %(message)s",
            "datefmt": "%Y-%m-%d %H:%M:%S",
        },
    }
    
    handlers: dict = {
        "default": {
            "formatter": "default",
            "class": "logging.StreamHandler",
            "stream": sys.stderr,
        },
        "detailed": {
            "formatter": "detailed",
            "class": "logging.StreamHandler",
            "stream": sys.stderr,
        },
    }
    
    loggers: dict = {
        LOGGER_NAME: {
            "handlers": ["default"],
            "level": LOG_LEVEL,
            "propagate": False,
        },
        "uvicorn": {
            "handlers": ["default"],
            "level": "INFO",
            "propagate": False,
        },
        "uvicorn.error": {
            "handlers": ["detailed"],
            "level": "INFO",
            "propagate": False,
        },
        "uvicorn.access": {
            "handlers": ["default"],
            "level": "INFO",
            "propagate": False,
        },
    }


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """
    Get a logger instance
    
    Args:
        name: Logger name. If None, uses the default logger name
        
    Returns:
        Logger instance
    """
    if name is None:
        name = LogConfig.LOGGER_NAME
    
    # Ensure the logger name starts with our main logger name
    if not name.startswith(LogConfig.LOGGER_NAME):
        name = f"{LogConfig.LOGGER_NAME}.{name}"
    
    return logging.getLogger(name)


def configure_logging():
    """Configure logging for the application"""
    import logging.config
    
    logging.config.dictConfig(LogConfig().__dict__)
    
    # Set up additional loggers
    logger = get_logger()
    logger.info("Logging configured successfully")
    
    return logger
