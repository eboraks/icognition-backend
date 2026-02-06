import asyncio
import os
import sys

# Add backend to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.database import get_session
from app.models import Prompt
from app.services.prompt_utils import PromptType
from sqlalchemy import select

PROMPTS = [
    {
        "prompt_type": PromptType.CHAT_AGENT_TYPE_AHEAD.value,
        "system_prompt": "You are an AI writing assistant. Continue the user's thought following the provided conversation history.",
        "user_prompt": "Conversation History:\n{history}\n\nAdditional Context: {context}\n\nUser is currently typing: '{current_text}'\n\nProvide ONLY the characters or words that complete the current thought from where it left off. Do NOT repeat any part of the input text. Do NOT explain yourself. The completion should feel natural and continue the specific sentence or phrase the user is currently typing. If no good completion is found, return nothing.",
        "description": "Ghost text completion for chat input"
    },
    {
        "prompt_type": "DSPy: Content Extraction",
        "system_prompt": "You are an expert content analysis engine. Your sole task is to analyze the provided text and return a valid JSON object that conforms to the ContentExtract Pydantic model.",
        "user_prompt": "### JSON Generation Rules:\n\n1. **Focus on Quality:** Extract accurate title, neutral summary, 4-6 key takeaways, tone, and intent.\n2. **Links and URLs:** Include full URLs in summary and bullet points.\n3. **Paywalls:** Note if content is limited.\n4. **Opinion Pieces:** Set objectivity correctly.\n5. **Social Media:** Set source_type correctly.\n6. **Multi-Topic:** Ensure key_takeaways cover all topics.\n\nContent: {content}",
        "description": "Instructions for DSPy content extraction signature"
    },
    {
        "prompt_type": PromptType.CHAT_INTENT_CLASSIFICATION.value,
        "system_prompt": "You are an expert intent classifier for a research assistant AI. Your job is to understand EXACTLY what the user wants to know. Pay close attention to potential ambiguities. For example, 'Is that statement true \"X\"?' usually means 'Verify if X is a fact', whereas 'Did person Y say \"X\"?' means 'Verify if the quote is attributed to Y'.",
        "user_prompt": "{input}",
        "description": "Classifies the user's intent to guide the research agent"
    },
    {
        "prompt_type": PromptType.CHAT_REFLECTION.value,
        "system_prompt": "You are a strict teacher grading an AI's answer.\nCheck for:\n1. Hallucinations or unsupported claims.\n2. Missing critical information.\n3. Failed intent (didn't answer the question).\nIf the answer is excellent and accurate, set is_satisfactory=True.\nIf it needs improvement, set is_satisfactory=False and provide a detailed critique.\nIf external verification is needed, set needs_search=True and provide a query.",
        "user_prompt": "Student Submission:\n{messages}",
        "description": "Critiques the agent's answer and decides if more research/refinement is needed"
    }
]

async def seed_extras():
    async for session in get_session():
        for p_data in PROMPTS:
            # Check if exists
            res = await session.execute(select(Prompt).where(Prompt.prompt_type == p_data["prompt_type"]))
            existing = res.scalars().first()
            if not existing:
                print(f"Seeding '{p_data['prompt_type']}'...")
                p = Prompt(**p_data)
                session.add(p)
            else:
                print(f"Skipping '{p_data['prompt_type']}' (already exists)")
        
        await session.commit()
        print("Seeding extras completed.")
        break

if __name__ == "__main__":
    asyncio.run(seed_extras())
