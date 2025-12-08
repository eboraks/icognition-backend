"""
Service for managing prompts with versioning
"""

from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from sqlalchemy.orm import selectinload

from app.models import Prompt
from app.utils.logging import get_logger

logger = get_logger(__name__)


class PromptService:
    """Service for managing prompts with versioning"""
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def get_latest_prompt(self, prompt_type: str) -> Optional[Prompt]:
        """
        Get the latest active prompt for a given prompt type
        
        Args:
            prompt_type: The type of prompt to retrieve
            
        Returns:
            The latest active Prompt, or None if not found
        """
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
            return result.scalar_one_or_none()
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
        content: str,
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
            # Get the latest version to determine the next version number
            latest = await self.get_latest_prompt(prompt_type)
            next_version = (latest.version + 1) if latest else 1
            
            new_prompt = Prompt(
                prompt_type=prompt_type,
                version=next_version,
                content=content,
                description=description,
                is_active=True,
                created_by=user_id
            )
            
            self.session.add(new_prompt)
            await self.session.commit()
            await self.session.refresh(new_prompt)
            
            logger.info(f"Created new prompt version {next_version} for type {prompt_type}")
            return new_prompt
        except Exception as e:
            await self.session.rollback()
            logger.error(f"Error creating prompt: {e}")
            raise
    
    async def update_prompt(
        self,
        prompt_id: int,
        content: str,
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
                content=content,
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

