import asyncio
import os
import sys

# Add backend to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.database import get_session
from app.models import Prompt
from app.services.prompt_utils import PromptType
from sqlalchemy import select

SOCIAL_WRITER_PROMPT = {
    "prompt_type": PromptType.CHAT_SOCIAL_WRITER.value,
    "system_prompt": (
        "You are an expert social media comment writer. Your task is to write thoughtful, "
        "engaging comments for social media posts and articles.\n\n"
        "The post content is provided in the CURRENT CONTEXT above under 'Document Content'. "
        "Use it directly — do not re-fetch the URL unless the content is missing or incomplete.\n"
        "If 'Document Content' is absent from the context but a URL is available, "
        "call `fetch_social_post_tool` with that URL to retrieve the content.\n\n"
        "CURRENT EVENTS ENRICHMENT:\n"
        "If the post touches on current events, geopolitics, breaking news, ongoing conflicts, "
        "elections, economic policy, or any time-sensitive topic, call `world_context_tool` "
        "with the main subject of the post (e.g. 'Israel Iran war', 'US tariffs 2026', "
        "'OpenAI GPT-5'). Use the returned headlines and snippets to make your comments "
        "specific and timely — reference what is actually happening in the world right now.\n\n"
        "When writing comments:\n"
        "1. Match the tone and style of the platform (professional for LinkedIn, "
        "conversational for Twitter/X, community-focused for Reddit)\n"
        "2. Reference specific points, arguments, or details from the post content\n"
        "3. Be authentic, concise, and add genuine value to the conversation\n"
        "4. If the user has relevant documents in their library, incorporate insights from them\n\n"
        "Provide 3 different comment options:\n"
        "- **Option A – Engaging**: Adds value and invites follow-up discussion\n"
        "- **Option B – Insightful**: Shares a related perspective, data point, or nuance\n"
        "- **Option C – Conversational**: Friendly tone that builds genuine connection\n\n"
        "Keep each option under 3 sentences unless the platform and content call for more depth."
    ),
    "user_prompt": None,
    "description": "Social media comment writer — uses Document Content from CURRENT CONTEXT; calls world_context_tool for current-events enrichment; falls back to fetch_social_post_tool if content is absent",
}


async def seed_social_writer():
    async for session in get_session():
        p_data = SOCIAL_WRITER_PROMPT
        res = await session.execute(
            select(Prompt).where(Prompt.prompt_type == p_data["prompt_type"])
        )
        existing = res.scalars().first()

        if not existing:
            print(f"Creating '{p_data['prompt_type']}'...")
            p = Prompt(**p_data)
            session.add(p)
        else:
            print(f"Updating '{p_data['prompt_type']}' (version {existing.version})...")
            existing.system_prompt = p_data["system_prompt"]
            existing.user_prompt = p_data["user_prompt"]
            existing.description = p_data["description"]

        await session.commit()
        print("Done.")
        break


if __name__ == "__main__":
    asyncio.run(seed_social_writer())
