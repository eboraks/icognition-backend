"""
Configuration settings for iCognition Backend
"""

import os
from typing import List, Optional
from pydantic_settings import BaseSettings
from pydantic import ConfigDict
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


class Settings(BaseSettings):
    """Application settings"""
    
    # API Configuration
    API_V1_STR: str = "/api/v1"
    PROJECT_NAME: str = "iCognition"
    VERSION: str = "0.1.0"
    
    # Database Configuration
    DATABASE_URL: Optional[str] = os.getenv("DATABASE_URL")
    DATABASE_URL_DOCKER: Optional[str] = os.getenv("DATABASE_URL_DOCKER")
    DEV_DATABASE_URL: Optional[str] = os.getenv("DEV_DATABASE_URL")
    STG_DATABASE_URL: Optional[str] = os.getenv("STG_DATABASE_URL")
    DB_HOST: str = os.getenv("DB_HOST", "localhost")
    DB_PORT: int = int(os.getenv("DB_PORT", "5432"))
    DB_NAME: str = os.getenv("DB_NAME", "icog_dev_db")
    DB_USER: str = os.getenv("DB_USER", "app")
    DB_PASSWORD: str = os.getenv("DB_PASSWORD", "2214")
    
    # Central Database Configuration
    CONNECTION_NAME: Optional[str] = os.getenv("CONNECTION_NAME")
    CENTRAL_DB_ICOG_USER: Optional[str] = os.getenv("CENTRAL_DB_ICOG_USER")
    CENTRAL_DB_ICOG_PASSWORD: Optional[str] = os.getenv("CENTRAL_DB_ICOG_PASSWORD")
    CENTRAL_DB_ICOG_NAME: Optional[str] = os.getenv("CENTRAL_DB_ICOG_NAME")
    
    # CORS Configuration
    BACKEND_CORS_ORIGINS: List[str] = [
        "chrome-extension://oeilkphkfimekfadiflbljknbhfmppej",
        "http://localhost:3000",
        "http://localhost:8000",
        "http://localhost:8080",
        "https://localhost:3000",
        "https://localhost:8000",
        "https://icognition.ai",
    ]
    
    # Logging Configuration
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    
    # Google AI Configuration
    GOOGLE_API_KEY: Optional[str] = os.getenv("GOOGLE_API_KEY")
    GCP_AI_KEY: Optional[str] = os.getenv("GCP_AI_KEY")
    GEMINI_FLASH_MODEL: str = os.getenv("GEMINI_FLASH_MODEL", "models/gemini-2.0-flash")
    GEMINI_PRO_MODEL: str = os.getenv("GEMINI_PRO_MODEL", "models/gemini-1.5-pro-001")
    GEMINI_EMBEDDING_MODEL: str = os.getenv("GEMINI_EMBEDDING_MODEL", "models/text-embedding-004")
    
    # Google Cloud Storage Configuration
    GCS_BUCKET_NAME: Optional[str] = os.getenv("GCS_BUCKET_NAME")
    GCS_PROJECT_ID: Optional[str] = os.getenv("GCS_PROJECT_ID")
    DOCS_BUCKET: Optional[str] = os.getenv("DOCS_BUCKET")
    
    # Hugging Face Configuration
    HF_API_TOKEN: Optional[str] = os.getenv("HF_API_TOKEN")
    
    # Security Configuration
    SECRET_KEY: str = os.getenv("SECRET_KEY", "your-secret-key-here")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
    DISABLE_AUTH: bool = os.getenv("DISABLE_AUTH", "false").lower() == "true"
    
    # Background Task Configuration
    MAX_BACKGROUND_TASKS: int = int(os.getenv("MAX_BACKGROUND_TASKS", "10"))
    
    # File Upload Configuration
    MAX_FILE_SIZE: int = int(os.getenv("MAX_FILE_SIZE", "10485760"))  # 10MB
    ALLOWED_FILE_TYPES: List[str] = ["text/html", "text/plain", "application/pdf"]
    
    # Entity and Clustering Configuration
    ENTITY_SIMILARITY_FRESHOLD: float = float(os.getenv("ENTITY_SIMILARITY_FRESHOLD", "0.6"))
    CLUSTERS_SIMILARITY_THRESHOLD: float = float(os.getenv("CLUSTERS_SIMILARITY_THRESHOLD", "0.6"))
    CLUSTERS_MIN_SIZE: int = int(os.getenv("CLUSTERS_MIN_SIZE", "4"))
    
    # User Configuration
    DUMMY_USER: Optional[str] = os.getenv("DUMMY_USER")
    
    model_config = ConfigDict(
        env_file=".env",
        case_sensitive=True,
        extra="ignore"  # Ignore extra fields instead of raising errors
    )


# Create settings instance
settings = Settings()


def get_database_url() -> str:
    """Get the complete database URL"""
    if settings.DATABASE_URL:
        return settings.DATABASE_URL
    
    return f"postgresql://{settings.DB_USER}:{settings.DB_PASSWORD}@{settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_NAME}"