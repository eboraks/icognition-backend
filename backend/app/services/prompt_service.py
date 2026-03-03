"""
Service for managing prompts with versioning
"""

import time
from types import SimpleNamespace
from typing import Dict, Optional, List, Tuple, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from sqlalchemy.orm import selectinload

from app.models import Prompt
from app.utils.logging import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Module-level prompt cache
# Keys are prompt_type strings; values are (field_dict, monotonic_timestamp).
# Using SimpleNamespace so callers can do db_prompt.system_prompt etc. without
# holding a live SQLAlchemy session reference.
# ---------------------------------------------------------------------------
_prompt_cache: Dict[str, Tuple[Any, float]] = {}
_CACHE_TTL: float = 300.0  # seconds


def _cache_key(prompt_type: str) -> str:
    return prompt_type


def invalidate_prompt_cache(prompt_type: Optional[str] = None) -> None:
    """
    Invalidate cached prompt(s).
    Call with no arguments to flush the entire cache,
    or pass a prompt_type to invalidate only that entry.
    """
    if prompt_type is None:
        _prompt_cache.clear()
        logger.info("Prompt cache fully invalidated")
    else:
        _prompt_cache.pop(_cache_key(prompt_type), None)
        logger.info(f"Prompt cache invalidated for type: {prompt_type}")


class PromptService:
    """Service for managing prompts with versioning"""
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def get_latest_prompt(self, prompt_type: str) -> Optional[SimpleNamespace]:
        """
        Get the latest active prompt for a given prompt type.

        Returns a SimpleNamespace with the same attributes as a Prompt model row
        so all callers (db_prompt.system_prompt, .user_prompt, .version) work
        transparently whether the result came from cache or the database.

        Results are cached in-process for _CACHE_TTL seconds (default 5 min).
        The cache is invalidated automatically when a new prompt version is saved.
        """
        key = _cache_key(prompt_type)
        cached = _prompt_cache.get(key)
        if cached is not None:
            data, fetched_at = cached
            if time.monotonic() - fetched_at < _CACHE_TTL:
                logger.debug(f"Prompt cache hit for type: {prompt_type}")
                return SimpleNamespace(**data)

        try:
            stmt = (
                select(Prompt)
                .where(
                    and_(
                        Prompt.prompt_type == prompt_type,
                        Prompt.is_active == True
                    )
                )
                .order_by(Prompt.version.desc())
                .limit(1)
            )
            result = await self.session.execute(stmt)
            prompt = result.scalar_one_or_none()

            if prompt is not None:
                data = {
                    'prompt_type': prompt.prompt_type,
                    'system_prompt': prompt.system_prompt,
                    'user_prompt': prompt.user_prompt,
                    'version': prompt.version,
                    'is_active': prompt.is_active,
                }
                _prompt_cache[key] = (data, time.monotonic())
                logger.debug(f"Prompt cache populated for type: {prompt_type} (v{prompt.version})")
                return SimpleNamespace(**data)

            return None
        except Exception as e:
            logger.error(f"Error getting latest prompt for type {prompt_type}: {e}")
            return None
    
    async def get_prompt_by_version(self, prompt_type: str, version: int) -> Optional[Prompt]:
        """
        Get a specific version of a prompt
        
        Args:
            prompt_type: The type of prompt
            version: The version number
            
        Returns:
            The Prompt with the specified version, or None if not found
        """
        try:
            stmt = (
                select(Prompt)
                .where(
                    and_(
                        Prompt.prompt_type == prompt_type,
                        Prompt.version == version
                    )
                )
            )
            result = await self.session.execute(stmt)
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Error getting prompt {prompt_type} version {version}: {e}")
            return None
    
    async def get_all_prompts(
        self, 
        prompt_type: Optional[str] = None,
        include_inactive: bool = False,
        limit: Optional[int] = None,
        offset: int = 0
    ) -> List[Prompt]:
        """
        Get all prompts, optionally filtered by type
        
        Args:
            prompt_type: Optional filter by prompt type
            include_inactive: Whether to include inactive prompts
            limit: Maximum number of results
            offset: Number of results to skip
            
        Returns:
            List of Prompt objects
        """
        try:
            conditions = []
            if prompt_type:
                conditions.append(Prompt.prompt_type == prompt_type)
            if not include_inactive:
                conditions.append(Prompt.is_active == True)
            
            stmt = select(Prompt)
            if conditions:
                stmt = stmt.where(and_(*conditions))
            stmt = stmt.order_by(Prompt.prompt_type, Prompt.version.desc())
            
            if limit:
                stmt = stmt.limit(limit).offset(offset)
            
            result = await self.session.execute(stmt)
            return list(result.scalars().all())
        except Exception as e:
            logger.error(f"Error getting all prompts: {e}")
            return []
    
    async def create_prompt(
        self,
        prompt_type: str,
        user_prompt: str,
        system_prompt: Optional[str] = None,
        description: Optional[str] = None,
        user_id: Optional[str] = None
    ) -> Prompt:
        """
        Create a new version of a prompt
        
        Args:
            prompt_type: The type of prompt
            content: The prompt content
            description: Optional description of this version
            user_id: ID of the user creating the prompt
            
        Returns:
            The created Prompt object
        """
        try:
            # Get the latest active version to determine the next version number
            # and deactivate it
            latest = await self.get_latest_prompt(prompt_type)
            next_version = (latest.version + 1) if latest else 1
            
            # Deactivate ALL active versions of this prompt type
            # (handles edge cases where multiple versions might be active)
            stmt = (
                select(Prompt)
                .where(
                    and_(
                        Prompt.prompt_type == prompt_type,
                        Prompt.is_active == True
                    )
                )
            )
            result = await self.session.execute(stmt)
            active_prompts = result.scalars().all()
            
            for prompt in active_prompts:
                prompt.is_active = False
                self.session.add(prompt)
                logger.info(f"Deactivated prompt version {prompt.version} (id: {prompt.id}) for type {prompt_type}")
            
            new_prompt = Prompt(
                prompt_type=prompt_type,
                version=next_version,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                description=description,
                is_active=True,
                created_by=user_id
            )
            
            self.session.add(new_prompt)
            await self.session.commit()
            await self.session.refresh(new_prompt)

            # Invalidate cache so next read picks up the new version immediately.
            invalidate_prompt_cache(prompt_type)

            logger.info(f"Created new prompt version {next_version} for type {prompt_type}")
            return new_prompt
        except Exception as e:
            await self.session.rollback()
            logger.error(f"Error creating prompt: {e}")
            raise
    
    async def update_prompt(
        self,
        prompt_id: int,
        user_prompt: str,
        system_prompt: Optional[str] = None,
        description: Optional[str] = None
    ) -> Prompt:
        """
        Update a prompt by creating a new version (immutable versioning)
        
        Args:
            prompt_id: ID of the prompt to update
            content: New content for the prompt
            description: Optional description for the new version
            
        Returns:
            The new Prompt version
        """
        try:
            # Get the existing prompt to copy its type
            stmt = select(Prompt).where(Prompt.id == prompt_id)
            result = await self.session.execute(stmt)
            existing = result.scalar_one_or_none()
            
            if not existing:
                raise ValueError(f"Prompt with id {prompt_id} not found")
            
            # Create a new version
            return await self.create_prompt(
                prompt_type=existing.prompt_type,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                description=description or existing.description,
                user_id=existing.created_by
            )
        except Exception as e:
            logger.error(f"Error updating prompt {prompt_id}: {e}")
            raise
    
    async def get_prompt_history(self, prompt_type: str) -> List[Prompt]:
        """
        Get all versions of a prompt type, ordered by version (newest first)
        
        Args:
            prompt_type: The type of prompt
            
        Returns:
            List of all Prompt versions for the type
        """
        try:
            stmt = (
                select(Prompt)
                .where(Prompt.prompt_type == prompt_type)
                .order_by(Prompt.version.desc())
            )
            result = await self.session.execute(stmt)
            return list(result.scalars().all())
        except Exception as e:
            logger.error(f"Error getting prompt history for {prompt_type}: {e}")
            return []
    
    async def soft_delete_prompt(self, prompt_id: int) -> bool:
        """
        Soft delete a prompt by setting is_active=False
        
        Args:
            prompt_id: ID of the prompt to delete
            
        Returns:
            True if successful, False otherwise
        """
        try:
            stmt = select(Prompt).where(Prompt.id == prompt_id)
            result = await self.session.execute(stmt)
            prompt = result.scalar_one_or_none()
            
            if not prompt:
                return False
            
            prompt.is_active = False
            await self.session.commit()
            await self.session.refresh(prompt)
            
            logger.info(f"Soft deleted prompt {prompt_id}")
            return True
        except Exception as e:
            await self.session.rollback()
            logger.error(f"Error soft deleting prompt {prompt_id}: {e}")
            return False

