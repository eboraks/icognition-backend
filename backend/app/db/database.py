"""
Database connection and session management for iCognition Backend
"""

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import text
from typing import AsyncGenerator
import os

from app.core.config import settings
from app.utils.logging import get_logger

logger = get_logger(__name__)


def get_database_url() -> str:
    """Get the async database URL"""
    if settings.DATABASE_URL:
        # Convert any postgresql URL to asyncpg format
        if settings.DATABASE_URL.startswith("postgresql://"):
            return settings.DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)
        elif settings.DATABASE_URL.startswith("postgresql+pg8000://"):
            return settings.DATABASE_URL.replace("postgresql+pg8000://", "postgresql+asyncpg://", 1)
        return settings.DATABASE_URL
    
    # Build URL from individual components
    return f"postgresql+asyncpg://{settings.DB_USER}:{settings.DB_PASSWORD}@{settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_NAME}"


# Create async engine with connection pooling
engine = create_async_engine(
    get_database_url(),
    echo=False,  # Set to True for SQL query logging
    future=True,
    pool_size=5,
    max_overflow=10,
    pool_timeout=30,
    pool_recycle=1800,  # Recycle connections after 30 minutes
    pool_pre_ping=True,  # Verify connections before use
)

# Create async session factory
async_session = async_sessionmaker(
    engine, 
    class_=AsyncSession, 
    expire_on_commit=False
)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency to get database session
    Used with FastAPI's Depends()
    """
    async with async_session() as session:
        try:
            yield session
        except Exception as e:
            logger.error(f"Database session error: {e}")
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_database():
    """Initialize database connection and verify pgvector extension"""
    try:
        async with engine.begin() as conn:
            # Test connection
            result = await conn.execute(text("SELECT 1"))
            logger.info("✅ Database connection successful")
            
            # Verify pgvector extension
            result = await conn.execute(text("SELECT * FROM pg_extension WHERE extname = 'vector'"))
            extension = result.fetchone()
            
            if extension:
                logger.info(f"✅ pgvector extension found: {extension}")
            else:
                logger.warning("⚠️ pgvector extension not found, attempting to install...")
                await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
                logger.info("✅ pgvector extension installed")
                
    except Exception as e:
        logger.error(f"❌ Database initialization failed: {e}")
        raise


async def close_database():
    """Close database connections"""
    try:
        await engine.dispose()
        logger.info("✅ Database connections closed")
    except Exception as e:
        logger.error(f"❌ Error closing database connections: {e}")


# Test database connection
async def test_connection():
    """Test database connection and pgvector functionality"""
    try:
        async with async_session() as session:
            # Test basic connection
            result = await session.execute(text("SELECT version()"))
            version = result.fetchone()[0]
            logger.info(f"📊 PostgreSQL version: {version}")
            
            # Test pgvector functionality
            await session.execute(text("""
                CREATE TABLE IF NOT EXISTS test_vector (
                    id SERIAL PRIMARY KEY,
                    embedding VECTOR(3)
                )
            """))
            
            await session.execute(text("""
                INSERT INTO test_vector (embedding) VALUES ('[1,2,3]'::vector)
                ON CONFLICT DO NOTHING
            """))
            
            result = await session.execute(text("""
                SELECT embedding <-> '[1,2,3]'::vector AS distance 
                FROM test_vector 
                LIMIT 1
            """))
            
            distance = result.fetchone()[0]
            logger.info(f"🔍 Vector similarity test: distance = {distance}")
            
            # Clean up test table
            await session.execute(text("DROP TABLE IF EXISTS test_vector"))
            await session.commit()
            
            logger.info("✅ Database connection test completed successfully")
            return True
            
    except Exception as e:
        logger.error(f"❌ Database connection test failed: {e}")
        return False