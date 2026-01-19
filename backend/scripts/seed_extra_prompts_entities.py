import asyncio
import os
import sys

# Add backend to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.database import get_session
from app.models import Prompt
from sqlalchemy import select

PROMPTS = [
    {
        "prompt_type": "DSPy: Entity Extraction",
        "system_prompt": "You are an expert entity extraction engine. Your task is to extract the MOST IMPORTANT entities from the provided text.",
        "user_prompt": "### Guidelines:\n1. Extract 1-10 MOST IMPORTANT entities (People, Organizations, Locations, Products, etc.).\n2. Do NOT extract common nouns or non-essential details.\n3. Return a valid JSON array of objects with 'name' and 'type'.\n\nContent: {content}",
        "description": "Instructions for DSPy entity extraction signature"
    }
]

async def seed_extras():
    async for session in get_session():
        for p_data in PROMPTS:
            res = await session.execute(select(Prompt).where(Prompt.prompt_type == p_data["prompt_type"]))
            if not res.scalar_one_or_none():
                print(f"Seeding '{p_data['prompt_type']}'...")
                p = Prompt(**p_data)
                session.add(p)
        
        await session.commit()
        print("Seeding extras completed.")
        break

if __name__ == "__main__":
    asyncio.run(seed_extras())
