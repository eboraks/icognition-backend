import asyncio
import os
import sys

# Add backend to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.database import get_session
from app.models import Prompt
from sqlalchemy import update

MAPPING = {
    "content_summary": "Doc Analysis: Summary",
    "entity_extraction": "Doc Analysis: Entities",
    "topic_categorization": "Doc Analysis: Topics",
    "sentiment_analysis": "Doc Analysis: Sentiment",
    "language_detection": "Doc Analysis: Language",
    "content_validation": "Doc Analysis: Validation",
    "bullet_points": "Doc Analysis: Bullet Points",
    "react_agent_system": "Chat Agent: System",
    "react_agent_template": "Chat Agent: Type-ahead Prompt",
    "opening_message_latest_documents": "Doc Analysis: Opening Message",
    "news_analysis": "Doc Extract: News",
    "blog_analysis": "Doc Extract: Blog",
    "social_analysis": "Doc Extract: Social",
    "product_analysis": "Doc Extract: Product",
    "marketing_analysis": "Doc Extract: Marketing",
    "book_analysis": "Doc Extract: Book",
    "generic_analysis": "Doc Extract: Generic"
}

async def update_prompt_types():
    async for session in get_session():
        for old_type, new_type in MAPPING.items():
            print(f"Updating '{old_type}' to '{new_type}'...")
            stmt = (
                update(Prompt)
                .where(Prompt.prompt_type == old_type)
                .values(prompt_type=new_type)
            )
            await session.execute(stmt)
        
        await session.commit()
        print("Update completed.")
        break

if __name__ == "__main__":
    asyncio.run(update_prompt_types())
