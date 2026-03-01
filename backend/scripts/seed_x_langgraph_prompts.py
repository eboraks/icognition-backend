import asyncio
import os
import sys

# Add the backend directory to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.db.database import get_session
from app.models import Prompt

PROMPTS = [
    {
        "prompt_type": "x_post_analyzer",
        "system_prompt": "You are an expert social media analyst tasked with analyzing a focal X (Twitter) post.",
        "user_prompt": "Analyze the following focal tweet.\n1. Provide a neutral, informative summary.\n2. Identify any visible biases.\n3. Identify the author's agenda or intent.\n4. Classify how informative the post is.\n5. Classify the objectivity (Objective, Subjective, Promotional).\n\nContent:\n{content}",
        "description": "Analyzes the main content of an X post."
    },
    {
        "prompt_type": "x_reply_categorizer",
        "system_prompt": "You are an expert community manager who reads Twitter threads and categorizes exactly how people are reacting to the main post.",
        "user_prompt": "Focal Post Summary: {summary}\n\nThread Content (Replies):\n{content}\n\nIdentify the prevailing community sentiments. Break down the replies into bullet points across these categories:\n1. Supportive / Agreed\n2. Dissenting / Disagreed\n3. Adding Context / Information\n4. Unrelated / Spam / Jokes\n\nProvide 1-3 short bullet points for each category if applicable.",
        "description": "Categorizes replies to an X post."
    },
    {
        "prompt_type": "x_final_compiler",
        "system_prompt": "You are a master content synthesizer writing a structured final output for a document library.",
        "user_prompt": "Title: {title}\nURL: {url}\n\nPost Analysis: {post_analysis}\n\nReply Categories: {reply_categories}\n\nSynthesize this information into a cohesive JSON structure.\n- The `markdown_content` should be a detailed markdown string covering the factual points made by the author and the notable reactions/context provided by the community.\n- Ensure `source_type` is set to 'Social Media Post'.\n- If there is any bias or agenda, ensure `intent` and `objectivity` accurately reflect it.",
        "description": "Synthesizes final X post structure."
    }
]

async def seed_prompts():
    print("Seeding X Post Processing LangGraph prompts...")
    async for session in get_session():
        
        for p_data in PROMPTS:
            # Check if active prompt exists
            res = await session.execute(
                select(Prompt)
                .where(Prompt.prompt_type == p_data["prompt_type"])
                .where(Prompt.is_active == True)
            )
            existing = res.scalars().first()
            
            if not existing:
                print(f"Seeding '{p_data['prompt_type']}'...")
                p = Prompt(**p_data)
                session.add(p)
            else:
                print(f"Skipping '{p_data['prompt_type']}' (active version already exists)")
                
        await session.commit()
    print("Done seeding X Post prompts.")

if __name__ == "__main__":
    asyncio.run(seed_prompts())
